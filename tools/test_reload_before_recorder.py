import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import reload_before_recorder as tool


FIXTURE = Path(__file__).resolve().parent.parent / "evidence/engineering-048/neutral-runtime-02-review/capture-02"


class Process:
    def __init__(self, identity):
        self.identity = identity
        self.created = identity["created"]
        self.closed = False

    def sample(self):
        return {"running": True}

    def close(self):
        self.closed = True


class Clock:
    def __init__(self, start):
        self.value = start

    def __call__(self):
        self.value += dt.timedelta(milliseconds=10)
        return self.value.isoformat()


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.instance, self.output = self.root / "instance", self.root / "output"
        self.instance.mkdir()
        self.output.mkdir()
        for relative in ("game-probe/native-resource-epochs.jsonl", "game-probe/native-invalid-model.jsonl", "logs/latest.log",
                         "packaged-client-plan.json", "packaged-client-launch.json"):
            path = self.instance / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((FIXTURE / relative).read_bytes())
        self.state = json.loads((FIXTURE / "final-snapshot.json").read_bytes())
        self.state_path = self.instance / "game-probe/native-observer.json"
        self.write_state()
        self.clock = Clock(tool.observer.instant(self.state["timestamp"]) + dt.timedelta(seconds=1))
        patch = mock.patch.object(tool, "now", self.clock)
        patch.start()
        self.addCleanup(patch.stop)
        self.recorder = tool.Recorder.__new__(tool.Recorder)
        value = self.recorder
        value.instance, value.output = self.instance, self.output
        value.journal = tool.Journal(self.output / "journal.jsonl")
        value.process = Process(json.loads((FIXTURE / "process.json").read_bytes()))
        value.identity = value.process.identity
        value.source_hashes, value.prefixes, value.number = {}, {}, 0
        value.session_id = "synthetic-session"
        value.plan = json.loads((FIXTURE / "packaged-client-plan.json").read_bytes())
        value.launch = json.loads((FIXTURE / "packaged-client-launch.json").read_bytes())
        value.metadata = json.loads((FIXTURE / "observer-target.json").read_bytes())
        value.review = json.loads((FIXTURE / "sources/config/native-diagnostic-review.json").read_bytes())
        value.expected = {"distinct_ids": 1091, "declarations": 1092}
        for name in ("packaged-client-plan.json", "packaged-client-launch.json"):
            (self.output / name).write_bytes((self.instance / name).read_bytes())
        value.plan_hash = tool.observer.digest(self.output / "packaged-client-plan.json")
        value.launch_hash = tool.observer.digest(self.output / "packaged-client-launch.json")
        value.context = {"session_id": value.session_id, "process": value.identity, "source_sha256": {}, "freshness_seconds": 15,
                         "plan_sha256": value.plan_hash, "launch_sha256": value.launch_hash}
        value.context_hash = tool.sha(tool.canonical(value.context))
        (self.output / "session-start.json").write_bytes(tool.canonical(value.context))
        value.journal.add("ready", session_start_sha256=value.context_hash)

    def write_state(self):
        self.state_path.write_bytes(tool.canonical(self.state))

    def receipt(self, *, succeeded=True, after=None):
        issued = after or self.clock.value + dt.timedelta(milliseconds=100)
        confirmed = issued + dt.timedelta(milliseconds=50)
        self.clock.value = confirmed + dt.timedelta(milliseconds=100)
        return {"method": "native_f3_t", "provider": "synthetic-test-only", "succeeded": succeeded,
                "issued_at": issued.isoformat(), "confirmed_at": confirmed.isoformat()}

    def rows(self):
        return tool.verify_journal((self.output / "journal.jsonl").read_bytes())

    def select(self, receipt):
        return tool.select_before(self.output, receipt, (self.output / "journal.jsonl").read_bytes())

    def confirm(self, receipt):
        path = self.root / "receipt.json"
        path.write_bytes(tool.canonical(receipt))
        return tool.confirm(self.output, path)

    def test_real_contract_fixture_publishes_only_after_both_owned_writers_close(self):
        event = self.recorder.capture()["event"]
        publication = json.loads((self.output / event["receipt"]).read_bytes())
        record = json.loads((self.output / publication["payload"]).read_bytes())
        self.assertLess(tool.observer.instant(record["capture_started_at"]), tool.observer.instant(record["capture_completed_at"]))
        self.assertLess(tool.observer.instant(record["capture_completed_at"]), tool.observer.instant(publication["payload_closed_at"]))
        self.assertLess(tool.observer.instant(publication["payload_closed_at"]), tool.observer.instant(event["receipt_closed_at"]))
        self.assertEqual(record["log_offset"], (self.instance / "logs/latest.log").stat().st_size)
        self.assertEqual(record["before"], self.state)

    def test_duplicate_source_reads_are_preserved_but_content_blobs_are_not_duplicated(self):
        self.recorder.capture()
        blobs = len(list((self.output / "blobs").iterdir()))
        self.recorder.capture()
        self.assertEqual(len(list((self.output / "blobs").iterdir())), blobs)
        self.assertEqual(len(list((self.output / "records").iterdir())), 2)

    def test_stale_snapshot_is_retained_ineligible_without_publication(self):
        self.clock.value += dt.timedelta(seconds=16)
        self.assertIsNone(self.recorder.capture())
        self.assertEqual(self.rows()[-1]["event"]["kind"], "ineligible")
        self.assertTrue((self.output / "records/00000001/raw-evidence.jsonl").exists())

    def test_game_screen_pause_counts_identity_and_native_pending_reject_before(self):
        for field, wrong in (("in_world", False), ("screen", "PauseScreen"), ("paused", True),
                             ("registered_count", 3), ("pid", 1), ("native_pending", 1)):
            with self.subTest(field=field):
                prior = self.state[field]
                self.state[field] = wrong
                self.write_state()
                self.assertIsNone(self.recorder.capture())
                self.state[field] = prior

    def test_native_callback_advancement_is_preserved_as_ineligible(self):
        original = tool.read_prefix
        calls = [0]
        def advancing(path):
            raw = original(path)
            if path.name == "native-resource-epochs.jsonl":
                calls[0] += 1
                if calls[0] == 2:
                    return raw + b"{"
            return raw
        with mock.patch.object(tool, "read_prefix", side_effect=advancing):
            self.assertIsNone(self.recorder.capture())
        self.assertIn("advanced", self.rows()[-1]["event"]["error"])

    def test_genuine_read_failure_is_not_retried_or_published(self):
        with mock.patch.object(tool, "read_prefix", side_effect=PermissionError("fixture access denied")) as reader:
            with self.assertRaises(PermissionError):
                self.recorder.capture()
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(self.rows()[-1]["event"]["kind"], "capture_failed")

    def test_review_contract_is_frozen_and_change_stops_before_reading_snapshot(self):
        self.assertIn(tool.observer.NEUTRAL_CONTRACT_FILE, tool.source_files())
        contract = self.root / "native-observer-consumer.json"
        contract.write_bytes(tool.observer.NEUTRAL_CONTRACT_FILE.read_bytes())
        self.recorder.source_hashes[str(contract)] = tool.observer.digest(contract)
        contract.write_bytes(contract.read_bytes() + b"\n")
        with mock.patch.object(tool.windows_snapshot_io, "read_snapshot_bytes") as reader:
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.recorder.capture()
        reader.assert_not_called()
        self.assertEqual(self.rows()[-1]["event"]["kind"], "capture_failed")

    def test_receipt_write_failure_retains_payload_and_never_publishes(self):
        original = tool.write_once
        def failed(path, raw):
            if path.name == "receipt.json":
                raise OSError("fixture receipt fsync failure")
            return original(path, raw)
        with mock.patch.object(tool, "write_once", side_effect=failed):
            with self.assertRaises(OSError):
                self.recorder.capture()
        self.assertTrue((self.output / "records/00000001/before.json").exists())
        self.assertEqual(self.rows()[-1]["event"]["kind"], "capture_failed")

    def test_log_truncation_cannot_become_a_new_valid_prefix(self):
        self.recorder.capture()
        path = self.instance / "logs/latest.log"
        path.write_bytes(path.read_bytes()[10:])
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.recorder.capture()

    def test_actual_process_exit_during_capture_is_terminal(self):
        with mock.patch.object(self.recorder.process, "sample", side_effect=[{"running": True}, {"running": False}]):
            with self.assertRaisesRegex(RuntimeError, "exited during"):
                self.recorder.capture()
        self.assertEqual(self.rows()[-1]["event"]["kind"], "capture_failed")

    def test_failed_initialization_closes_the_owned_process(self):
        process = Process(self.recorder.identity)
        with mock.patch.object(tool.observer, "frozen_context", return_value=(self.recorder.plan, self.recorder.launch)):
            with self.assertRaises(FileNotFoundError):
                tool.Recorder(self.instance, self.root / "failed-init", self.recorder.expected,
                              process_factory=lambda plan, launch: process)
        self.assertTrue(process.closed)
        rows = tool.verify_journal((self.root / "failed-init/journal.jsonl").read_bytes())
        self.assertEqual(rows[-1]["event"]["kind"], "initialization_failed")

    def test_selection_chooses_unique_nearest_completed_publication(self):
        self.recorder.capture()
        self.recorder.capture()
        selected, proof = self.select(self.receipt())
        self.assertEqual(selected.parent.name, "00000002")
        self.assertEqual(proof["journal_sequence"], self.rows()[-1]["sequence"])

    def test_publication_after_input_does_not_replace_real_before_evidence(self):
        self.recorder.capture()
        receipt = self.receipt()
        self.recorder.capture()
        selected, _ = self.select(receipt)
        self.assertEqual(selected.parent.name, "00000001")

    def test_selection_rejects_stale_snapshot_even_if_receipt_is_new(self):
        self.recorder.capture()
        with self.assertRaisesRegex(ValueError, "stale"):
            self.select(self.receipt(after=self.clock.value + dt.timedelta(seconds=16)))

    def test_equal_publication_times_are_ambiguous(self):
        row = self.recorder.capture()["event"]
        self.recorder.journal.add("published", **{key: row[key] for key in ("record_id", "receipt", "receipt_sha256", "receipt_closed_at")})
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.select(self.receipt())

    def test_later_ineligible_observation_prevents_fallback_to_prior_good_snapshot(self):
        self.recorder.capture()
        self.state["paused"] = True
        self.write_state()
        self.recorder.capture()
        with self.assertRaisesRegex(ValueError, "invalidates"):
            self.select(self.receipt())

    def test_tampered_raw_blob_fails_integrity(self):
        self.recorder.capture()
        record = json.loads((self.output / "records/00000001/before.json").read_bytes())
        (self.output / record["raw_files"]["native-snapshot.json"]).write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.select(self.receipt())

    def test_tampered_payload_and_publication_receipt_are_rejected(self):
        self.recorder.capture()
        path = self.output / "records/00000001/before.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "payload hash"):
            self.select(self.receipt())
        path.write_bytes(original)
        path = self.output / "records/00000001/receipt.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "receipt hash"):
            self.select(self.receipt())

    def test_missing_or_reordered_journal_records_fail_closed(self):
        self.recorder.capture()
        rows = (self.output / "journal.jsonl").read_bytes().splitlines(keepends=True)
        for broken in (b"".join(rows[1:]), b"".join(reversed(rows)), b"".join(rows) + b"{"):
            with self.assertRaises(ValueError):
                tool.verify_journal(broken)

    def test_confirm_uses_existing_api_and_retains_actual_failed_input(self):
        self.recorder.capture()
        receipt = self.receipt(succeeded=False)
        with mock.patch.object(tool.observer, "confirm_reload_input", wraps=tool.observer.confirm_reload_input) as callback:
            result = self.confirm(receipt)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(result["record_status"], "selected")
        self.assertFalse(result["input"]["succeeded"])
        self.assertEqual(tool.input_events(self.output), [result])

    def test_stale_attempt_is_included_as_rejected_not_removed_from_input_stream(self):
        self.recorder.capture()
        result = self.confirm(self.receipt(after=self.clock.value + dt.timedelta(seconds=20)))
        self.assertEqual(result["record_status"], "rejected")
        self.assertIn("stale", result["selection_error"])
        self.assertEqual(tool.input_events(self.output), [result])

    def test_one_publication_cannot_be_reused_for_multiple_inputs(self):
        self.recorder.capture()
        self.confirm(self.receipt())
        result = self.confirm(self.receipt())
        self.assertEqual(result["record_status"], "rejected")
        self.assertIn("already used", result["selection_error"])
        self.assertEqual(len(tool.input_events(self.output)), 2)

    def test_omitted_attempt_cannot_be_hidden_from_full_chain_reader(self):
        self.recorder.capture()
        self.confirm(self.receipt())
        (self.output / "inputs.jsonl").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "omits"):
            tool.input_events(self.output)

    def test_coordinated_ledger_and_result_change_cannot_replace_sealed_before(self):
        self.recorder.capture()
        event = self.confirm(self.receipt())
        event["before"]["registered_count"] = 1
        (self.output / "inputs.jsonl").write_bytes(tool.canonical(event))
        (self.output / "input-attempts" / event["attempt_id"] / "result.json").write_bytes(tool.canonical(event))
        with self.assertRaisesRegex(ValueError, "sealed before"):
            tool.input_events(self.output)

    def test_interrupted_or_locked_confirmation_remains_an_explicit_ledger_failure(self):
        self.recorder.capture()
        (self.output / "confirmation.lock").write_text("another owned writer")
        with self.assertRaises(FileExistsError):
            self.confirm(self.receipt())
        self.assertEqual(len(list((self.output / "input-attempts").glob("*/submission.json"))), 1)
        with self.assertRaisesRegex(ValueError, "omits"):
            tool.input_events(self.output)

    def test_future_external_confirmation_is_preserved_as_rejected(self):
        self.recorder.capture()
        receipt = self.receipt()
        receipt["confirmed_at"] = (self.clock.value + dt.timedelta(seconds=60)).isoformat()
        result = self.confirm(receipt)
        self.assertEqual(result["record_status"], "rejected")
        self.assertIn("future dated", result["selection_error"])


class ReaderOwnershipTest(unittest.TestCase):
    def test_completion_timestamp_is_read_only_after_writer_closed(self):
        stream = io.BytesIO()
        stream.fileno = lambda: 7
        def closed_time():
            self.assertTrue(stream.closed)
            return "completion-after-close"
        with mock.patch.object(Path, "open", return_value=stream), mock.patch.object(Path, "mkdir"), mock.patch.object(tool.os, "fsync"), mock.patch.object(tool, "now", side_effect=closed_time):
            self.assertEqual(tool.write_once(Path("fixture"), b"raw"), "completion-after-close")

    def test_prefix_read_exception_closes_owned_reader(self):
        stream = io.BytesIO(b"raw")
        stream.fileno = lambda: 7
        stream.read = mock.Mock(side_effect=OSError("fixture failed read"))
        with mock.patch.object(tool.windows_snapshot_io, "open_snapshot", return_value=stream), mock.patch.object(tool.os, "fstat", return_value=type("Stat", (), {"st_size": 3})()):
            with self.assertRaises(OSError):
                tool.read_prefix(Path("fixture"))
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()
