"""Offline controls using the real sealed fourth-reload OOM and its prior prefix."""
import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
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

    def test_zero_real_displacement_or_broken_cadence_does_not_add_stable_time(self):
        samples = [{"elapsed_seconds": time, "process": {"running": True}, "observation": {"verified": True,
            "raw_state": {"resource_epochs": {"last_completed_sequence": 2}, "capture_started_monotonic_nanos": int(time * 1e9), "monotonic_nanos": int(time * 1e9)}}} for time in (0, 5, 40)]
        stability = waiter.trailing_stability(samples, 2, 0, 20)
        self.assertEqual(stability["samples"], 1)
        self.assertEqual(stability["consumer_seconds"], 0)
        self.assertEqual(stability["native_seconds"], 0)

    def test_generic_arguments_have_no_owned_instance_defaults_or_policy_relaxation(self):
        with self.assertRaises(SystemExit):
            waiter.main([])
        with self.assertRaisesRegex(waiter.EvidenceError, "Invalid wait policy"):
            waiter.main(["--recorder", str(self.recorder), "--consumer", str(self.consumer), "--output", str(self.root / "invalid-output"),
                         "--expected-sequence", "4", "--stable-seconds", "59"])


if __name__ == "__main__":
    unittest.main()
