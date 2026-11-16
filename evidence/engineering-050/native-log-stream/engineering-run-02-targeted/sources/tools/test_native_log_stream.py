import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import native_log_stream as logs

FIXTURE = Path(__file__).resolve().parents[1] / "evidence/engineering-050/native-log-stream/actual-inputs"


class NativeLogStreamTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.instance = self.root / "instance"
        self.directory = self.instance / "logs"
        self.directory.mkdir(parents=True)
        self.active = self.directory / "latest.log"
        self.header = ("[opaque local timestamp] [main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, "+str(self.instance)+"]\n").encode("utf-8")
        self.review = json.loads(logs.REVIEW_FILE.read_bytes())
        self.review["limits"].update(publication_attempts=2, publication_wait_seconds=0)
        self.layout = logs.Layout("logs/latest.log", "logs/%d{yyyy-MM-dd}-%i.log.gz", "min", 1, 99)
        self.context = {"instance": str(self.instance), "pid": 123, "launch_sha256": "fixture-launch"}
        self.readers = 0

    def reader(self, witness=True):
        self.readers += 1
        path = self.root / ("witness-"+str(self.readers))
        path.write_bytes(self.header)
        return logs.NativeLogStream(self.instance, self.layout, self.root / ("evidence-"+str(self.readers)),
                                    self.context, self.review, prefix_witness=path if witness else None)

    def archive(self, name, raw):
        path = self.directory / name
        path.write_bytes(gzip.compress(raw, mtime=0))
        return path

    def test_fresh_start_and_append_keep_every_raw_byte_and_prefix(self):
        self.active.write_bytes(self.header+b"original ERROR\r\n")
        reader = self.reader(witness=False)
        first = reader.read()
        self.active.write_bytes(first.data+b"later warning\n")
        second = reader.read()
        self.assertEqual(second.data, first.data+b"later warning\n")
        self.assertEqual(second.receipt["sha256"], logs.sha(second.data))
        self.assertEqual((reader.output / "anchor.bin").read_bytes(), first.data)
        self.assertEqual(logs.verify_capture(reader.output, second.receipt_path), second.data)

    def test_real_gzip_contains_the_earlier_independent_startup_prefix(self):
        archived = (FIXTURE / "2026-11-16-1.log.gz").read_bytes()
        prefix = (FIXTURE / "startup-prefix.log").read_bytes()
        decoded, trailer = logs.strict_gzip(archived, self.review["limits"]["max_segment_bytes"])
        self.assertEqual(decoded, gzip.decompress(archived))
        self.assertTrue(decoded.startswith(prefix))
        self.assertEqual(len(decoded), 28764)
        self.assertEqual(len(prefix), 27952)
        self.assertEqual(trailer["isize"], len(decoded))

    def test_midnight_rollover_preserves_anchor_and_records_original_gzip_and_latest(self):
        first = self.header+b"before midnight ERROR\n"
        self.archive("2026-11-16-1.log.gz", first)
        self.active.write_bytes(b"after midnight ERROR\n")
        reader = self.reader()
        captured = reader.read()
        self.assertEqual(captured.data, first+b"after midnight ERROR\n")
        self.assertEqual([s["name"] for s in captured.receipt["segments"]], ["2026-11-16-1.log.gz", "latest.log"])
        for segment in captured.receipt["segments"]:
            self.assertEqual(logs.sha((reader.output / segment["blob"]).read_bytes()), segment["raw_sha256"])

    def test_min_reindex_tracks_file_identity_instead_of_pinning_the_old_name(self):
        older = self.header+b"old\n"
        old_path = self.archive("2026-11-16-1.log.gz", older)
        self.active.write_bytes(b"middle\n")
        reader = self.reader()
        first = reader.read()
        old_path.rename(self.directory / "2026-11-16-2.log.gz")
        self.archive("2026-11-16-1.log.gz", b"middle\n")
        self.active.write_bytes(b"new\n")
        second = reader.read()
        self.assertEqual(second.data, first.data+b"new\n")
        self.assertEqual([s["name"] for s in second.receipt["segments"]], ["2026-11-16-2.log.gz", "2026-11-16-1.log.gz", "latest.log"])

    def test_calendar_dates_without_events_are_not_assumed_to_be_missing_archives(self):
        self.archive("2026-11-14-1.log.gz", self.header+b"older\n")
        self.archive("2026-11-16-1.log.gz", b"newer\n")
        self.active.write_bytes(b"active\n")
        self.assertEqual(self.reader().read().data, self.header+b"older\nnewer\nactive\n")

    def test_unwitnessed_midrun_attach_foreign_startup_and_sequence_gap_fail(self):
        self.archive("2026-11-16-1.log.gz", self.header)
        self.active.write_bytes(b"active\n")
        with self.assertRaisesRegex(logs.LogIntegrityError, "independent"):
            self.reader(witness=False).read()
        self.active.write_bytes(self.header)
        with self.assertRaisesRegex(logs.LogIntegrityError, "foreign|duplicate"):
            self.reader().read()
        self.active.write_bytes(b"active\n")
        self.archive("2026-11-16-3.log.gz", self.header)
        with self.assertRaisesRegex(logs.LogIntegrityError, "gap"):
            self.reader().read()

    def test_crc_corruption_truncation_and_concatenated_gzip_are_rejected(self):
        raw = gzip.compress(self.header, mtime=0)
        for corrupt in (raw[:-1], raw[:-8]+b"\x00"*8, raw+raw):
            with self.subTest(kind=len(corrupt)), self.assertRaises(logs.LogIntegrityError):
                logs.strict_gzip(corrupt, 100000)

    def test_changed_or_deleted_retired_segment_and_truncated_active_prefix_fail(self):
        path = self.archive("2026-11-16-1.log.gz", self.header)
        self.active.write_bytes(b"first\n")
        reader = self.reader()
        reader.read()
        raw = bytearray(path.read_bytes())
        raw[4] ^= 1  # A valid header-only change keeps decoded bytes identical.
        path.write_bytes(raw)
        with self.assertRaisesRegex(logs.LogIntegrityError, "retired"):
            reader.read()
        path.unlink()
        with self.assertRaises(logs.LogIntegrityError):
            reader.read()
        self.active.write_bytes(self.header+b"first\n")
        reader = self.reader()
        reader.read()
        self.active.write_bytes(self.header)
        with self.assertRaisesRegex(logs.LogIntegrityError, "prefix"):
            reader.read()

    def test_rotation_during_an_owned_read_restarts_only_the_bounded_snapshot(self):
        before = self.header+b"before\n"
        self.active.write_bytes(before)
        reader = self.reader()
        first = reader.read()
        actual = logs.windows_snapshot_io.open_snapshot
        rotated = [False]
        def open_then_roll(path):
            if Path(path) == self.active and not rotated[0]:
                rotated[0] = True
                self.archive("2026-11-16-1.log.gz", before)
                self.active.unlink()
                self.active.write_bytes(b"after\n")
            return actual(path)
        with mock.patch.object(logs.windows_snapshot_io, "open_snapshot", side_effect=open_then_roll):
            result = reader.read()
        self.assertEqual(result.data, before+b"after\n")
        self.assertEqual(len(result.receipt["publication_transitions"]), 1)

    def test_unexplained_active_replacement_and_duplicate_retired_payload_fail(self):
        self.active.write_bytes(self.header+b"original\n")
        reader = self.reader()
        reader.read()
        replacement = self.directory / "replacement.tmp"
        replacement.write_bytes(self.active.read_bytes())
        os.replace(replacement, self.active)
        with self.assertRaisesRegex(logs.LogIntegrityError, "replaced"):
            reader.read()
        self.archive("2026-11-14-1.log.gz", self.header)
        self.archive("2026-11-15-1.log.gz", b"duplicated complete segment\n")
        self.archive("2026-11-16-1.log.gz", b"duplicated complete segment\n")
        self.active.write_bytes(b"active\n")
        with self.assertRaisesRegex(logs.LogIntegrityError, "duplicates"):
            self.reader().read()

    def test_reader_and_profile_are_frozen_by_both_consumers_and_experiment(self):
        import reload_before_recorder as recorder
        import client_experiment as experiment
        for source in (Path(logs.__file__), logs.REVIEW_FILE):
            self.assertIn(source, recorder.source_files())
            self.assertIn(source, experiment.SOURCES)

    def test_incomplete_compression_is_bounded_and_permission_failure_is_not_retried(self):
        self.active.write_bytes(self.header)
        (self.directory / "2026-11-16-1.log").write_bytes(self.header)
        reader = self.reader()
        with self.assertRaisesRegex(logs.LogIntegrityError, "bounded"):
            reader.read()
        failed = json.loads((reader.output / "captures/00000001-failed.json").read_bytes())
        self.assertEqual(len(failed["publication_transitions"]), 2)
        (self.directory / "2026-11-16-1.log").unlink()
        reader = self.reader()
        with mock.patch.object(logs.windows_snapshot_io, "open_snapshot", side_effect=PermissionError("actual access failure")) as opened:
            with self.assertRaises(PermissionError):
                reader.read()
        self.assertEqual(opened.call_count, 1)

    def test_fresh_logger_absence_is_explicit_and_does_not_establish_an_anchor(self):
        reader = self.reader(witness=False)
        with self.assertRaises(logs.LogNotAvailable):
            reader.read()
        self.assertIsNone(reader.anchor)
        self.active.write_bytes(self.header)
        self.assertEqual(reader.read().data, self.header)

    def test_unreviewed_encoding_and_invalid_archive_date_are_rejected(self):
        self.active.write_bytes(self.header+b"\xff\n")
        with self.assertRaisesRegex(logs.LogIntegrityError, "UTF-8"):
            self.reader().read()
        self.archive("2026-19-16-1.log.gz", self.header)
        with self.assertRaisesRegex(logs.LogIntegrityError, "date"):
            self.reader().read()


if __name__ == "__main__":
    unittest.main()
