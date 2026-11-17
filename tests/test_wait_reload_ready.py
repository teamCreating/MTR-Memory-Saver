"""Offline controls using the real sealed fourth-reload OOM and its prior prefix."""
import copy
from contextlib import redirect_stderr
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import wait_reload_ready as waiter

SEALED = Path(__file__).resolve().parents[1] / "evidence/engineering-050/owned049d-reload-attempt03-oom/capture-01"


class WaitReloadReadyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="mtr-waiter-controls-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.recorder, cls.consumer = cls.root / "recorder", cls.root / "consumer"
        bindings = waiter.read(SEALED / "history-bindings.json")
        history = next(row for row in bindings["histories"] if row["verified_count"] == 3)
        cls.history_number = history["record_number"]
        all_inputs = [json.loads(line) for line in (SEALED / "recorder/inputs.jsonl").read_bytes().splitlines()]
        excluded = all_inputs[-1]["attempt_id"]
        def ignore(source, names):
            return {excluded} if Path(source).name == "input-attempts" else set()
        shutil.copytree(SEALED / "recorder", cls.recorder, ignore=ignore)
        cls.consumer.mkdir()
        for path in (SEALED / "observer").iterdir():
            if path.is_file() and (path.suffix == ".py" or path.name in ("observer-target.json", "native-diagnostic-review.json", "native-log-reader.json", "native-observer-consumer.json")):
                shutil.copyfile(path, cls.consumer / path.name)
        for spec in history["exact_prefixes"]:
            raw = (SEALED / spec["final_payload"]).read_bytes()[:spec["bytes"]]
            if waiter.sha(raw) != spec["sha256"]:
                raise AssertionError("Historical fixture prefix pin differs.")
            relative = Path(spec["final_payload"])
            destination = (cls.recorder if relative.parts[0] == "recorder" else cls.consumer) / Path(*relative.parts[1:])
            destination.write_bytes(raw)
        # The selected evaluator record predates its later journal read. The sealed
        # export intentionally omits those redundant later record payloads.
        journal = cls.recorder / "journal.jsonl"
        lines = journal.read_bytes().splitlines(keepends=True)
        selected = next(index for index, line in enumerate(lines) if json.loads(line)["event"].get("kind") == "published"
                        and json.loads(line)["event"]["record_id"].rsplit(":", 1)[1] == str(cls.history_number))
        journal.write_bytes(b"".join(lines[:selected + 1]))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def positive_inputs(self, producer):
        samples = producer.rec.json_lines((self.consumer / "samples.jsonl").read_bytes())
        journal = producer.rec.verify_journal((self.recorder / "journal.jsonl").read_bytes())
        capture = waiter.closed_capture(producer, journal, [])
        native = copy.deepcopy(capture["snapshot"])
        now = max(producer.observer.instant(capture["completed_at"]), producer.observer.instant(samples[-1]["timestamp"]), producer.observer.instant(native["observed_at"])) + dt.timedelta(seconds=1)
        return native, samples, capture["epochs"], journal, now

    def fake_wait_producer(self, root):
        process = SimpleNamespace(kernel=None, handle=object(), created="same", creation_time=lambda: "same", close_count=0)
        process.close = lambda: setattr(process, "close_count", process.close_count + 1)
        producer = SimpleNamespace(context={"freshness_seconds": 15, "instance": str(root)}, plan={}, launch={},
            recorder=root / "recorder", consumer=root / "consumer", metadata={"snapshot_path": "native.json", "epochs_path": "epochs.jsonl"},
            observer=SimpleNamespace(WindowsProcess=lambda *args: process), identity=SimpleNamespace(NativeApi=lambda **kwargs: SimpleNamespace(live=lambda handle: None)),
            check_sources=lambda **kwargs: None, prefix=lambda path, receipts: b'{}' if path.name == "native.json" else b'',
            rec=SimpleNamespace(json_lines=lambda raw: [], verify_journal=lambda raw: []))
        return producer, process

    def test_actual_oom_after_return_fails_without_any_eligible_publication(self):
        with waiter.FrozenProducer(SEALED / "recorder", SEALED / "observer") as producer:
            journal = producer.rec.verify_journal((producer.recorder / "journal.jsonl").read_bytes())
            capture = waiter.closed_capture(producer, journal, [])
            self.assertEqual(capture["kind"], "ineligible")
            samples = producer.rec.json_lines((producer.consumer / "samples.jsonl").read_bytes())
            # The terminal diagnostic must run before the successful-publication/reload gate.
            with patch.object(producer.observer, "neutral_reload_evidence", side_effect=AssertionError("Success replay ran before fatal diagnostics")):
                result = waiter.inspect(producer, capture["snapshot"], samples, capture["epochs"], journal, 5, producer.observer.instant(capture["completed_at"]))
            self.assertEqual(result["status"], "diagnostics_failed")
            self.assertEqual(result["capture_kind"], "ineligible")
            self.assertEqual([row["line"] for row in result["native_diagnostics"]["unreviewed_native"]], [365, 366, 395, 396])
            self.assertTrue(result["native_diagnostics"]["native_attribution"]["passed"])

    def test_pending_native_return_waits_without_inventing_completion(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            native, samples, epochs, journal, now = self.positive_inputs(producer)
            result = waiter.inspect(producer, native, samples, epochs, journal, 5, now)
            self.assertEqual(result["status"], "waiting")
            self.assertEqual(result["waiting_for"], "actual_return")

    @unittest.skipUnless(os.name == "nt", "The immutable producer input-ledger replay uses captured Windows path semantics.")
    def test_real_historical_success_requires_all_three_inputs_and_two_stable_spans(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            native, samples, epochs, journal, now = self.positive_inputs(producer)
            result = waiter.inspect(producer, native, samples, epochs, journal, 4, now)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["verified_reload_count"], 3)
            self.assertEqual(result["longest_verified_reload_run"], 3)
            self.assertTrue(all(row["verified"] for row in result["reloads"]))
            self.assertGreaterEqual(result["stability"]["consumer_seconds"], 60)
            self.assertGreaterEqual(result["stability"]["native_seconds"], 60)

    @unittest.skipUnless(os.name == "nt", "The immutable producer input-ledger replay uses captured Windows path semantics.")
    def test_native_stability_below_sixty_does_not_receive_sample_interval_credit(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            native, samples, epochs, journal, now = self.positive_inputs(producer)
            with patch.object(waiter, "trailing_stability", return_value={"samples": 14, "consumer_seconds": 65, "native_seconds": 59.999}):
                result = waiter.inspect(producer, native, samples, epochs, journal, 4, now)
            self.assertEqual(result["status"], "waiting")
            self.assertEqual(result["waiting_for"], "measured_stable_spans")

    def test_ineligible_latest_consumer_and_stale_evidence_cannot_pass(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            native, samples, epochs, journal, now = self.positive_inputs(producer)
            paused = copy.deepcopy(samples)
            paused[-1]["observation"]["verified"] = False
            paused[-1]["observation"]["failures"] = ["client_paused"]
            for actual_samples, clock in ((paused, now), (samples, now + dt.timedelta(seconds=30))):
                with self.subTest(clock=clock):
                    result = waiter.inspect(producer, native, actual_samples, epochs, journal, 4, clock)
                    self.assertEqual(result["status"], "waiting")

    @unittest.skipUnless(os.name == "nt", "The immutable producer input-ledger replay uses captured Windows path semantics.")
    def test_baseline_after_first_input_is_rejected_not_shifted(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            native, samples, epochs, journal, now = self.positive_inputs(producer)
            changed = copy.deepcopy(samples)
            first = next(row for row in changed if row["observation"]["verified"])
            first["timestamp"] = changed[-1]["timestamp"]
            with self.assertRaisesRegex(waiter.EvidenceError, "baseline does not predate"):
                waiter.inspect(producer, native, changed, epochs, journal, 4, now)

    def test_changed_source_pin_and_raw_blob_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="mtr-waiter-corrupt-") as temporary:
            root = Path(temporary).resolve()
            rec, obs = root / "recorder", root / "consumer"
            shutil.copytree(self.recorder, rec); shutil.copytree(self.consumer, obs)
            pin = obs / "native-log-reader.json"
            original = pin.read_bytes(); pin.write_bytes(original + b"\n")
            with self.assertRaisesRegex(waiter.EvidenceError, "source pin differs"):
                waiter.FrozenProducer(rec, obs)
            pin.write_bytes(original)
            with waiter.FrozenProducer(rec, obs) as producer:
                journal = producer.rec.verify_journal((rec / "journal.jsonl").read_bytes())
                record = waiter.read(rec / "records" / f"{self.history_number:08d}" / "before.json")
                blob = rec / record["raw_files"]["client-log-prefix.log"]
                blob.write_bytes(b"changed")
                with self.assertRaisesRegex(waiter.EvidenceError, "raw capture pin differs"):
                    waiter.closed_capture(producer, journal, [])

    def test_manifest_basename_uses_recorded_windows_or_posix_separators(self):
        self.assertEqual(waiter.source_name(r"C:\producer root\tools\reload_before_recorder.py"), "reload_before_recorder.py")
        self.assertEqual(waiter.source_name("/producer root/tools/reload_before_recorder.py"), "reload_before_recorder.py")

    def test_broken_cadence_does_not_add_stable_time(self):
        samples = [{"elapsed_seconds": time, "process": {"running": True}, "observation": {"verified": True,
            "raw_state": {"resource_epochs": {"last_completed_sequence": 2}, "capture_started_monotonic_nanos": int(time * 1e9), "monotonic_nanos": int(time * 1e9)}}} for time in (0, 5, 40)]
        stability = waiter.trailing_stability(samples, 2, 0, 20)
        self.assertEqual(stability["samples"], 1)
        self.assertEqual(stability["consumer_seconds"], 0)
        self.assertEqual(stability["native_seconds"], 0)

    def test_generic_arguments_have_no_owned_instance_defaults_or_policy_relaxation(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            waiter.main([])
        with self.assertRaisesRegex(waiter.EvidenceError, "Invalid wait policy"):
            waiter.main(["--recorder", str(self.recorder), "--consumer", str(self.consumer), "--output", str(self.root / "invalid-output"),
                         "--expected-sequence", "4", "--stable-seconds", "59"])

    def test_partial_append_waits_but_complete_corruption_is_not_retried(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            with self.assertRaises(waiter.PendingPublication):
                waiter.rows(producer, b'{"not_yet_closed":')
            with self.assertRaises(json.JSONDecodeError):
                waiter.rows(producer, b'not json\n')

    def test_freshness_cannot_be_relaxed_above_the_frozen_recorder_policy(self):
        with waiter.FrozenProducer(self.recorder, self.consumer) as producer:
            with self.assertRaisesRegex(waiter.EvidenceError, "freshness must not exceed"):
                waiter.wait(SimpleNamespace(freshness_seconds=producer.context["freshness_seconds"] + 1), producer, lambda value: None)

    def test_deadline_is_bounded_and_owned_process_handle_is_closed(self):
        clock = SimpleNamespace(value=0)
        with tempfile.TemporaryDirectory(prefix="mtr-waiter-deadline-") as temporary:
            root = Path(temporary)
            producer, process = self.fake_wait_producer(root)
            args = SimpleNamespace(deadline_seconds=3, expected_sequence=2, interval=5, freshness_seconds=15, stable_seconds=60)
            with patch.object(waiter, "inspect", return_value={"status": "waiting", "waiting_for": "actual_return", "read_receipts": []}):
                result, code = waiter.wait(args, producer, lambda value: None, monotonic=lambda: clock.value,
                                           sleep=lambda seconds: setattr(clock, "value", clock.value + seconds))
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "deadline_elapsed")
            self.assertEqual(clock.value, 3)
            self.assertEqual(process.close_count, 1)

    def test_ready_assessment_crossing_deadline_cannot_return_success(self):
        clock = SimpleNamespace(value=0)
        with tempfile.TemporaryDirectory(prefix="mtr-waiter-late-ready-") as temporary:
            producer, process = self.fake_wait_producer(Path(temporary))
            args = SimpleNamespace(deadline_seconds=3, expected_sequence=2, interval=5, freshness_seconds=15, stable_seconds=60)
            def late_ready(*unused, **kwargs):
                clock.value = 4
                return {"status": "ready", "read_receipts": []}
            with patch.object(waiter, "inspect", side_effect=late_ready):
                result, code = waiter.wait(args, producer, lambda value: None, monotonic=lambda: clock.value, sleep=lambda seconds: None)
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "deadline_elapsed")
            self.assertEqual(result["ready_not_granted"], "assessment_completed_after_deadline")
            self.assertEqual(process.close_count, 1)

    def test_api_and_clock_initialization_failures_close_the_owned_handle(self):
        for failure in ("api", "clock"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="mtr-waiter-init-") as temporary:
                producer, process = self.fake_wait_producer(Path(temporary))
                args = SimpleNamespace(deadline_seconds=3, expected_sequence=2, interval=5, freshness_seconds=15, stable_seconds=60)
                def broken():
                    raise RuntimeError("initialization failed")
                if failure == "api":
                    producer.identity.NativeApi = lambda **kwargs: broken()
                with self.assertRaisesRegex(RuntimeError, "initialization failed"):
                    waiter.wait(args, producer, lambda value: None, monotonic=broken if failure == "clock" else lambda: 0)
                self.assertEqual(process.close_count, 1)

    def test_output_cannot_write_into_a_producer_directory(self):
        output = self.recorder / "must-not-be-created"
        with self.assertRaisesRegex(waiter.EvidenceError, "outside producer"):
            waiter.main(["--recorder", str(self.recorder), "--consumer", str(self.consumer), "--output", str(output), "--expected-sequence", "4"])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
