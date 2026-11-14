import argparse
import datetime as dt
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

import observe_packaged_client as observer


class ObservationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.now = dt.datetime(2026, 11, 15, 1, 0, tzinfo=dt.timezone.utc)
        self.launch = {"pid": 999, "timestamp": self.now.isoformat(), "command": [str(self.root / "java.exe"), "-Xmx3g"]}
        self.plan = {"instance": str(self.root), "java": str(self.root / "java.exe"), "mods": [], "packs": []}
        self.state_path = self.root / "packaged-observer.json"
        self.state = {"schema_version": 1, "timestamp": self.now.isoformat(), "pid": 999, "paused": False,
            "in_world": True, "screen": None, "game_time": 10, "registered_count": 669,
            "heap": {"used_bytes": 10, "committed_bytes": 20, "max_bytes": 30}, "native_pending": 0, "native_settled": True,
            "shared_blockbench": {"pending": 0, "outstanding": 0, "queued": 0, "failures": 0}, "active_read_permits": 0,
            "resource_epochs": {"last_completed_sequence": 1, "in_flight": 0}, "monotonic_nanos": 1000}
        self.vehicle_path = self.root / "live.json"
        self.vehicle = {"timestamp": self.now.isoformat(), "registered_count": 669, "vehicles": [{"id": 7, "railProgress": 15.0}]}

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def observe(self, require_world=False, last_stamp=None):
        self.write(self.state_path, self.state)
        self.write(self.vehicle_path, self.vehicle)
        return observer.state_observation(self.state_path, self.now, last_stamp, 15, 669, require_world, True,
            self.vehicle_path, 999)[0]

    def test_current_native_and_vehicle_observations_are_verified(self):
        result = self.observe(require_world=True)
        self.assertTrue(result["verified"], result)
        self.assertEqual(result["state"]["runtime_counters"]["native_pending"], 0)
        self.assertEqual(result["raw_state"], self.state)
        self.assertEqual(result["raw_vehicle_state"], self.vehicle)
        self.assertEqual(result["state_sha256"], observer.digest(self.state_path))

    def test_missing_explicit_paused_state_cannot_pass(self):
        del self.state["paused"]
        result = self.observe()
        self.assertFalse(result["verified"])
        self.assertIn("paused", result["missing"])

    def test_current_game_screen_does_not_hide_pause(self):
        self.state["paused"] = True
        self.assertIn("client_paused", self.observe()["failures"])

    def test_missing_or_nonzero_native_ownership_cannot_settle(self):
        del self.state["native_pending"]
        self.assertIn("runtime_counters.native_pending", self.observe()["missing"])
        self.state["native_pending"] = 1
        self.assertIn("unsettled_counter.native_pending", self.observe()["failures"])
        self.state["native_pending"] = False
        self.assertFalse(self.observe()["verified"])

    def test_stale_repeated_and_future_observations_cannot_pass(self):
        self.state["timestamp"] = (self.now-dt.timedelta(seconds=16)).isoformat()
        self.assertIn("stale_or_future_state", self.observe()["failures"])
        self.state["timestamp"] = self.now.isoformat()
        self.assertIn("state_did_not_advance", self.observe(last_stamp=self.now.isoformat())["failures"])
        self.state["timestamp"] = (self.now+dt.timedelta(seconds=3)).isoformat()
        self.assertIn("stale_or_future_state", self.observe()["failures"])

    def test_old_vehicle_snapshot_cannot_be_combined_with_current_counters(self):
        self.vehicle["timestamp"] = (self.now-dt.timedelta(seconds=20)).isoformat()
        result = self.observe(require_world=True)
        self.assertFalse(result["verified"])
        self.assertIn("stale_or_future_vehicle_state", result["failures"])

    def test_other_process_state_cannot_pass(self):
        self.state["pid"] = 998
        self.assertIn("observer_process_identity_mismatch", self.observe()["failures"])

    def test_process_creation_and_exact_argument_identity_are_required(self):
        process = {"pid": 999, "created": self.now.isoformat(), "executable": self.plan["java"]}
        observer.verify_process_identity(self.plan, self.launch, process, self.launch["command"])
        with self.assertRaisesRegex(ValueError, "arguments"):
            observer.verify_process_identity(self.plan, self.launch, process, [self.plan["java"], "-Xmx4g"])
        process["created"] = (self.now-dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "start time"):
            observer.verify_process_identity(self.plan, self.launch, process, self.launch["command"])

    def test_modified_frozen_input_or_plan_is_rejected(self):
        (self.root / "mods").mkdir()
        jar = self.root / "mods/mod.jar"
        jar.write_bytes(b"original")
        self.plan["mods"] = [{"filename": "mod.jar", "sha256": observer.digest(jar)}]
        self.write(self.root / "packaged-client-plan.json", self.plan)
        self.launch["plan_sha256"] = observer.digest(self.root / "packaged-client-plan.json")
        self.write(self.root / "packaged-client-launch.json", self.launch)
        observer.frozen_context(self.root)
        jar.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "mod"):
            observer.frozen_context(self.root)
        jar.write_bytes(b"original")
        self.plan["instance"] = str(self.root / "other")
        self.write(self.root / "packaged-client-plan.json", self.plan)
        with self.assertRaises(ValueError):
            observer.frozen_context(self.root)

    def test_reload_in_flight_prevents_premature_settlement(self):
        self.state["resource_epochs"]["in_flight"] = 1
        self.assertIn("unsettled_counter.resource_in_flight", self.observe()["failures"])

    def run_observation(self, mode, interrupt=False, change_source=False, native_failure=False):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.launch["timestamp"] = now
        self.write(self.root / "packaged-client-plan.json", self.plan)
        self.launch["plan_sha256"] = observer.digest(self.root / "packaged-client-plan.json")
        self.write(self.root / "packaged-client-launch.json", self.launch)
        output = self.root / (mode + "-observation")
        state, vehicle = self.state, self.vehicle
        state_path, vehicle_path = self.state_path, self.vehicle_path
        owner = self
        clock = [0.0]
        source = self.root / "source.py"
        source.write_bytes(b"captured observer source")
        (self.root / "logs").mkdir()
        log = "Loaded 670 vehicles and completed door movement validation\n"
        if native_failure:
            log += "Failed to decode resource [test:valid-large.obj] as UTF-8 text\nResource text exceeds the configured limit\n"
        (self.root / "logs/latest.log").write_text(log)
        class FakeProcess:
            def __init__(self, plan, launch):
                self.identity = {"pid": 999, "created": now}
                self.created = now
                self.closed = False
            def sample(self):
                clock[0] += 0.001
                if interrupt:
                    raise KeyboardInterrupt()
                if change_source:
                    source.write_bytes(b"changed source after observer began")
                state["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()
                state["game_time"] += 1
                vehicle["timestamp"] = state["timestamp"]
                vehicle["vehicles"][0]["railProgress"] += 1
                owner.write(state_path, state)
                owner.write(vehicle_path, vehicle)
                return {"running": True, "working_set": 100, "private_usage": 200}
            def close(self):
                self.closed = True
        args = SimpleNamespace(instance=self.root, output=output, state_file=state_path, vehicle_state_file=vehicle_path,
            epoch_events=None, mode=mode, require_world=mode == "route", unpaused=True, duration=0.012, interval=0.003,
            freshness_seconds=15, expected_count=669, stable_seconds=0.001, auxiliary_interval=60,
            gpu_counter=[], nmt=False, reload_events=None, require_reloads=0, expected_declarations=None)
        def advance_clock(seconds):
            clock[0] += seconds
        with mock.patch.object(observer, "WindowsProcess", FakeProcess), mock.patch.object(observer, "__file__", str(source)), \
                mock.patch.object(observer.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(observer.time, "sleep", side_effect=advance_clock):
            code = observer.observe(args)
        return code, observer.read(output / "summary.json"), output

    def test_route_uses_observed_monotonic_window_and_motion_with_all_valid_states(self):
        code, summary, output = self.run_observation("route")
        self.assertEqual(code, 0)
        self.assertTrue(summary["passed"])
        self.assertGreaterEqual(summary["elapsed_seconds"], 0.012)
        self.assertTrue(summary["observed_vehicle_motion"])
        self.assertTrue(summary["observed_game_time_advanced"])
        self.assertEqual(summary["samples_sha256"], observer.digest(output / "samples.jsonl"))

    def test_failed_preflight_preserves_failure_instead_of_missing_run(self):
        self.write(self.root / "packaged-client-plan.json", self.plan)
        self.launch["plan_sha256"] = observer.digest(self.root / "packaged-client-plan.json")
        self.write(self.root / "packaged-client-launch.json", self.launch)
        output = self.root / "failed-preflight"
        args = SimpleNamespace(instance=self.root, output=output, mode="route")
        with mock.patch.object(observer, "WindowsProcess", side_effect=ValueError("Reused PID")):
            self.assertEqual(observer.observe(args), 1)
        summary = observer.read(output / "summary.json")
        self.assertEqual(summary["status"], "preflight_failed")
        self.assertIn("Reused PID", summary["error"])
        self.assertFalse(summary["passed"])
        self.assertTrue((output / "samples.jsonl").exists())

    def test_interruption_preserves_raw_evidence_and_cannot_pass(self):
        code, summary, output = self.run_observation("route", interrupt=True)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "interrupted")
        self.assertFalse(summary["passed"])
        self.assertTrue((output / "samples.jsonl").exists())
        self.assertEqual(summary["samples_sha256"], hashlib.sha256(b"").hexdigest())

    def epochs(self, count):
        events, observations = [], []
        for index in range(1, count+1):
            base = {"pid": 999, "sequence": index, "timestamp": (self.now+dt.timedelta(seconds=index)).isoformat(),
                    "render_thread": True, "thread_id": 7, "monotonic_nanos": index*1000}
            events.append({**base, "phase": "start"})
            events.append({**base, "phase": "return", "monotonic_nanos": index*1000+100})
            observations.append({"verified": True, "state": {"timestamp": base["timestamp"]}, "state_sha256": str(index),
                "raw_state": {"monotonic_nanos": index*1000+200, "resource_epochs": {"last_completed_sequence": index}}})
        return events, observations

    def test_twenty_distinct_settled_reloads_exclude_initial_startup(self):
        events, observations = self.epochs(21)
        result = observer.native_epoch_evidence(events, observations, 1, self.launch, self.now.isoformat())
        self.assertEqual(len(result), 20)
        self.assertTrue(all(item["verified"] for item in result))
        self.assertEqual(observer.consecutive_reloads(result), 20)

    def test_repeating_one_reload_twenty_times_cannot_pass(self):
        events, observations = self.epochs(1)
        result = observer.native_epoch_evidence(events*20, observations*20, 0, self.launch, self.now.isoformat())
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["verified"])

    def test_return_without_settlement_before_next_reload_fails(self):
        events, observations = self.epochs(2)
        observations[0]["raw_state"]["monotonic_nanos"] = 2200
        result = observer.native_epoch_evidence(events, observations, 0, self.launch, self.now.isoformat())
        self.assertFalse(result[0]["verified"])
        self.assertTrue(result[1]["verified"])
        self.assertEqual(observer.consecutive_reloads(result), 1)

    def test_missing_sequence_breaks_consecutive_reload_proof(self):
        records = [{"sequence": 2, "verified": True}, {"sequence": 4, "verified": True}]
        self.assertEqual(observer.consecutive_reloads(records), 1)

    def test_missing_return_and_foreign_process_events_do_not_count(self):
        events, observations = self.epochs(1)
        result = observer.native_epoch_evidence(events[:1], observations, 0, self.launch, self.now.isoformat())
        self.assertFalse(result[0]["verified"])
        events[0]["pid"] = 1000
        result = observer.native_epoch_evidence(events, observations, 0, self.launch, self.now.isoformat())
        self.assertFalse(result[0]["verified"])

    def test_registration_log_polling_alone_cannot_be_twenty_reloads(self):
        log = b"Reloading ResourceManager: vanilla\nLoaded 669 vehicles and completed door movement validation\nMTR memory sharing: 1 requests, 0 path hits, 1 unique parses, 0 failures, 0 pending, 0 outstanding, 0 queued\n"
        event = {"timestamp": self.now.isoformat(), "pid": 999, "process_created": self.now.isoformat(), "method": "native_f3_t", "log_offset": 0,
                 "before": {"timestamp": self.now.isoformat(), "screen": "game", "paused": False, "model_parsing_complete": True, "registered_count": 669}}
        results = observer.reload_evidence(log, [event]*20, self.launch, self.now.isoformat(), 669)
        self.assertEqual(sum(item["verified"] for item in results), 1)
        self.assertEqual(observer.consecutive_reloads(results), 1)

    def full_reload_fixture(self, count=21, declarations=670):
        epochs, observations = self.epochs(count)
        inputs, chunks, offset = [], [], 0
        for index in range(2, count+1):
            start = self.now+dt.timedelta(seconds=index)
            before_stamp = (start-dt.timedelta(seconds=0.5)).isoformat()
            event_stamp = (start-dt.timedelta(seconds=0.4)).isoformat()
            issued = (start-dt.timedelta(seconds=0.2)).isoformat()
            confirmed = (start-dt.timedelta(seconds=0.1)).isoformat()
            before = {"timestamp": before_stamp, "screen": None, "in_world": True, "paused": False,
                "native_settled": True, "registered_count": 669, "resource_epochs": {"last_completed_sequence": index-1}}
            inputs.append({"event_id": str(index), "timestamp": event_stamp, "pid": 999, "process_created": self.now.isoformat(),
                "method": "native_f3_t", "log_offset": offset, "before": before,
                "input": {"method": "native_f3_t", "provider": "@oai/sky", "succeeded": True, "issued_at": issued, "confirmed_at": confirmed}})
            chunk = ("Reloading ResourceManager: vanilla, file/full-pack.zip\nLoaded " + str(declarations) + " vehicles and completed door movement validation\nMTR memory sharing: 1 requests, 0 path hits, 1 unique parses, 0 failures, 0 pending, 0 outstanding, 0 queued\n").encode()
            chunks.append(chunk)
            offset += len(chunk)
        return b"".join(chunks), inputs, epochs, observations

    def test_full_twenty_reload_gate_cross_checks_input_log_and_settled_epochs(self):
        log, inputs, epochs, observations = self.full_reload_fixture()
        records = observer.full_reload_evidence(log, inputs, epochs, observations, 1, self.launch, self.now.isoformat(), 669, 670)
        self.assertEqual(observer.consecutive_reloads(records), 20)
        self.assertEqual(records[0]["declared_vehicle_count"], 670)
        self.assertEqual(records[0]["native_epoch"]["sequence"], 2)

    def test_native_creator_reload_cycles_cannot_pass_full_resource_gate(self):
        log, inputs, epochs, observations = self.full_reload_fixture()
        records = observer.full_reload_evidence(b"", inputs, epochs, observations, 1, self.launch, self.now.isoformat(), 669, 670)
        self.assertEqual(observer.consecutive_reloads(records), 0)
        self.assertEqual(observer.full_reload_evidence(log, [], epochs, observations, 1, self.launch, self.now.isoformat(), 669, 670), [])

    def test_unconfirmed_or_stale_input_cannot_count_as_full_reload(self):
        log, inputs, epochs, observations = self.full_reload_fixture(2)
        inputs[0]["input"]["succeeded"] = False
        records = observer.full_reload_evidence(log, inputs, epochs, observations, 1, self.launch, self.now.isoformat(), 669, 670)
        self.assertFalse(records[0]["verified"])
        inputs[0]["input"]["succeeded"] = True
        inputs[0]["before"]["timestamp"] = (self.now-dt.timedelta(seconds=20)).isoformat()
        records = observer.full_reload_evidence(log, inputs, epochs, observations, 1, self.launch, self.now.isoformat(), 669, 670)
        self.assertFalse(records[0]["verified"])

    def test_declaration_and_unique_id_count_units_are_independent(self):
        self.vehicle["registered_count"] = 670
        self.write(self.state_path, self.state)
        self.write(self.vehicle_path, self.vehicle)
        result, _ = observer.state_observation(self.state_path, self.now, None, 15, 669, True, True, self.vehicle_path, 999, 670)
        self.assertTrue(result["verified"])
        log, inputs, epochs, observations = self.full_reload_fixture(2)
        records = observer.full_reload_evidence(log, inputs, epochs, observations, 1, self.launch, self.now.isoformat(), 669, 669)
        self.assertFalse(records[0]["verified"])

    def test_native_decode_error_rejects_full_reload_even_with_zero_work_counters(self):
        log, inputs, epochs, observations = self.full_reload_fixture(2)
        log += b"Failed to decode resource [test:large.obj] as UTF-8 text\n"
        records = observer.full_reload_evidence(log, inputs, epochs, observations, 1, self.launch, self.now.isoformat(), 669, 670)
        self.assertFalse(records[0]["verified"])

    def test_native_decode_error_rejects_settlement_even_with_zero_counters(self):
        code, summary, output = self.run_observation("startup", native_failure=True)
        self.assertEqual(code, 1)
        self.assertFalse(summary["passed"])
        self.assertEqual(len(summary["native_diagnostics"]["blocking"]), 2)
        self.assertIn(b"valid-large.obj", (output / "native-log-at-completion.log").read_bytes())

    def test_source_identity_is_captured_before_sampling_and_later_change_is_explicit(self):
        code, summary, output = self.run_observation("route", change_source=True)
        self.assertEqual(code, 0)
        self.assertEqual((output / "observer-source.py").read_bytes(), b"captured observer source")
        self.assertEqual(summary["source_sha256"], hashlib.sha256(b"captured observer source").hexdigest())
        self.assertTrue(summary["source_changed_during_observation"])
        self.assertNotEqual(summary["source_sha256"], summary["current_source_sha256"])

    def test_external_input_receipt_preserves_original_and_rejects_duplicate_confirmation(self):
        _, inputs, _, _ = self.full_reload_fixture(2)
        receipt = inputs[0].pop("input")
        before_path, events_path = self.root / "before.json", self.root / "inputs.jsonl"
        self.write(before_path, inputs[0])
        original = before_path.read_bytes()
        record = observer.confirm_reload_input(before_path, events_path, receipt)
        self.assertEqual(before_path.read_bytes(), original)
        self.assertEqual(record["before_record_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(json.loads(events_path.read_text())["input"], receipt)
        with self.assertRaisesRegex(ValueError, "already been recorded"):
            observer.confirm_reload_input(before_path, events_path, receipt)

    def test_nonfinite_or_nonpositive_intervals_are_rejected(self):
        for value in ("nan", "inf", "-1", "0"):
            with self.assertRaises(argparse.ArgumentTypeError):
                observer.finite_positive(value)


if __name__ == "__main__":
    unittest.main()
