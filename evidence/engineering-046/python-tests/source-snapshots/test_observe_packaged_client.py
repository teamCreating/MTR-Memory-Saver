import argparse
import datetime as dt
import hashlib
import json
import math
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
        self.state = {"schema_version": 2, "timestamp": self.now.isoformat(), "pid": 999, "paused": False,
            "in_world": True, "screen": None, "game_time": 10, "registered_count": 669,
            "heap": {"used_bytes": 10, "committed_bytes": 20, "max_bytes": 30}, "native_pending": 0, "native_settled": True,
            "shared_blockbench": {"pending": 0, "outstanding": 0, "queued": 0, "failures": 0}, "active_read_permits": 0,
            "resource_epochs": {"last_completed_sequence": 1, "in_flight": 0}, "monotonic_nanos": 1000,
            "text_workspace": {"budget_bytes": 64, "used_bytes": 0, "peak_bytes": 32, "waiting": 0}}
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

    def test_schema_two_requires_complete_text_workspace(self):
        workspace = dict(self.state["text_workspace"])
        for field in workspace:
            with self.subTest(field=field):
                self.state["text_workspace"] = {key: value for key, value in workspace.items() if key != field}
                result = self.observe()
                self.assertFalse(result["verified"])
                self.assertIn("text_workspace." + field, result["missing"])
        for value in (None, [], "unknown"):
            with self.subTest(workspace=value):
                self.state["text_workspace"] = value
                self.assertIn("text_workspace", self.observe()["missing"])
        del self.state["text_workspace"]
        self.assertIn("text_workspace", self.observe()["missing"])

    def test_schema_two_text_workspace_counters_are_integers(self):
        for field in self.state["text_workspace"]:
            original = self.state["text_workspace"][field]
            for value in (False, True, 0.0, "0"):
                with self.subTest(field=field, value=value):
                    self.state["text_workspace"][field] = value
                    result = self.observe()
                    self.assertFalse(result["verified"])
                    self.assertIn("invalid_text_workspace_counter." + field, result["failures"])
            self.state["text_workspace"][field] = original

    def test_schema_two_text_workspace_budget_bounds_are_checked(self):
        original = dict(self.state["text_workspace"])
        for values in ({"budget_bytes": 0}, {"budget_bytes": -1}, {"used_bytes": -1},
                {"used_bytes": 33}, {"peak_bytes": -1}, {"peak_bytes": 65}, {"waiting": -1}):
            with self.subTest(values=values):
                self.state["text_workspace"] = {**original, **values}
                self.assertIn("invalid_text_workspace_bounds", self.observe()["failures"])
        self.state["text_workspace"] = {**original, "peak_bytes": original["budget_bytes"]}
        self.assertTrue(self.observe()["verified"])

    def test_schema_two_text_workspace_must_release_used_and_waiting(self):
        original = dict(self.state["text_workspace"])
        for values in ({"used_bytes": 1}, {"waiting": 1}):
            with self.subTest(values=values):
                self.state["text_workspace"] = {**original, **values}
                result = self.observe()
                self.assertFalse(result["verified"])
                self.assertIn("text_workspace_not_settled", result["failures"])

    def test_schema_one_retains_historical_observation_compatibility(self):
        self.state["schema_version"] = 1
        del self.state["text_workspace"]
        self.assertTrue(self.observe()["verified"])

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

    def run_observation(self, mode, interrupt=False, change_source=False, native_failure=False, motion_pattern="distributed",
            process_sample_cost=1, snapshot_period=None, auxiliary_delays=()):
        initial_time = dt.datetime.now(dt.timezone.utc)
        now = initial_time.isoformat()
        self.launch["timestamp"] = now
        self.write(self.root / "packaged-client-plan.json", self.plan)
        self.launch["plan_sha256"] = observer.digest(self.root / "packaged-client-plan.json")
        self.write(self.root / "packaged-client-launch.json", self.launch)
        output = self.root / (mode + "-observation")
        state, vehicle = self.state, self.vehicle
        state_path, vehicle_path = self.state_path, self.vehicle_path
        owner = self
        clock = [0.0]
        class SimulatedDatetime(dt.datetime):
            @classmethod
            def now(cls, timezone=None):
                result = initial_time + dt.timedelta(seconds=clock[0])
                return result.astimezone(timezone) if timezone else result.replace(tzinfo=None)
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
                sampled_elapsed = clock[0]
                clock[0] += process_sample_cost
                if interrupt:
                    raise KeyboardInterrupt()
                if change_source:
                    source.write_bytes(b"changed source after observer began")
                snapshot_clock = math.floor(clock[0]/snapshot_period)*snapshot_period if snapshot_period else clock[0]
                stamp = (initial_time + dt.timedelta(seconds=snapshot_clock)).isoformat()
                advanced = stamp != state["timestamp"]
                state["timestamp"] = stamp
                if advanced:
                    state["game_time"] += 1
                vehicle["timestamp"] = state["timestamp"]
                if advanced and motion_pattern == "changing_id":
                    vehicle["vehicles"][0]["id"] += 1
                elif advanced and (motion_pattern == "distributed" or (motion_pattern == "early_only" and sampled_elapsed < 20)):
                    vehicle["vehicles"][0]["railProgress"] += 1
                owner.write(state_path, state)
                owner.write(vehicle_path, vehicle)
                return {"running": True, "working_set": 100, "private_usage": 200}
            def close(self):
                self.closed = True
        args = SimpleNamespace(instance=self.root, output=output, state_file=state_path, vehicle_state_file=vehicle_path,
            epoch_events=None, mode=mode, require_world=mode == "route", unpaused=True, duration=60, interval=5,
            freshness_seconds=15, expected_count=669, stable_seconds=5, auxiliary_interval=60,
            route_windows=3, minimum_window_progress_displacement=0.01,
            gpu_counter=[], nmt=False, reload_events=None, require_reloads=0, expected_declarations=None)
        def advance_clock(seconds):
            clock[0] += seconds
        auxiliary_call = [0]
        def delayed_auxiliary(*unused):
            if auxiliary_call[0] < len(auxiliary_delays):
                clock[0] += auxiliary_delays[auxiliary_call[0]]
            auxiliary_call[0] += 1
            return {}
        with mock.patch.object(observer, "WindowsProcess", FakeProcess), mock.patch.object(observer, "__file__", str(source)), \
                mock.patch.object(observer.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(observer.time, "sleep", side_effect=advance_clock), \
                mock.patch.object(observer.dt, "datetime", SimulatedDatetime), \
                mock.patch.object(observer, "auxiliary", side_effect=delayed_auxiliary):
            code = observer.observe(args)
        return code, observer.read(output / "summary.json"), output

    def test_route_uses_observed_monotonic_window_and_motion_with_all_valid_states(self):
        code, summary, output = self.run_observation("route")
        self.assertEqual(code, 0)
        self.assertTrue(summary["passed"])
        self.assertGreaterEqual(summary["elapsed_seconds"], 60)
        self.assertTrue(summary["observed_vehicle_motion"])
        self.assertTrue(summary["observed_game_time_advanced"])
        self.assertEqual(summary["samples_sha256"], observer.digest(output / "samples.jsonl"))
        self.assertTrue(summary["route_window_evidence"]["passed"])
        self.assertEqual(len(summary["route_window_evidence"]["windows"]), 3)
        policy_hash = observer.digest(output / "route-window-policy.json")
        self.assertEqual(summary["policy"]["route_window_policy_sha256"], policy_hash)
        self.assertEqual(observer.read(output / "route-window-policy.json"), summary["policy"]["route_windows"])
        samples = [json.loads(line) for line in (output / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual({sample["route_window"]["index"] for sample in samples}, {0, 1, 2})
        self.assertTrue(all(sample["route_window"]["eligible"] and sample["route_window"]["policy_sha256"] == policy_hash for sample in samples))

    def test_changing_vehicle_ids_without_progress_cannot_pass_route(self):
        code, summary, _ = self.run_observation("route", motion_pattern="changing_id")
        self.assertEqual(code, 1)
        self.assertFalse(summary["observed_vehicle_motion"])
        self.assertFalse(summary["passed"])
        self.assertTrue(all(not window["motion_verified"] for window in summary["route_window_evidence"]["windows"]))

    def test_only_early_motion_cannot_pass_full_route_duration(self):
        code, summary, _ = self.run_observation("route", motion_pattern="early_only")
        self.assertEqual(code, 1)
        self.assertTrue(summary["observed_vehicle_motion"])
        self.assertFalse(summary["passed"])
        self.assertEqual([window["motion_verified"] for window in summary["route_window_evidence"]["windows"]], [True, False, False])
        self.assertIn("distributed_route_windows_unverified", summary["observed_failures"])

    def test_slow_auxiliary_skips_missed_deadlines_without_repeated_probe_samples(self):
        code, summary, output = self.run_observation("route", process_sample_cost=0.001,
            snapshot_period=1, auxiliary_delays=(12,))
        samples = [json.loads(line) for line in (output / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
        elapsed = [sample["elapsed_seconds"] for sample in samples]
        self.assertEqual(elapsed[:3], [0, 15, 20])
        self.assertTrue(all(second-first >= 5 for first, second in zip(elapsed, elapsed[1:])))
        self.assertNotIn("state_did_not_advance", summary["observed_failures"])
        self.assertEqual(summary["verified_sample_count"], len(samples))
        self.assertGreaterEqual(elapsed[-1], 60)
        self.assertEqual(code, 0)
        self.assertTrue(summary["passed"])

    def test_exact_deadline_completion_waits_for_a_future_sampling_slot(self):
        _, _, output = self.run_observation("route", process_sample_cost=0,
            snapshot_period=1, auxiliary_delays=(10,))
        samples = [json.loads(line) for line in (output / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([sample["elapsed_seconds"] for sample in samples[:3]], [0, 15, 20])

    def test_slow_auxiliary_does_not_relax_actual_gap_or_window_coverage(self):
        code, summary, output = self.run_observation("route", process_sample_cost=0.001,
            snapshot_period=1, auxiliary_delays=(25,))
        samples = [json.loads(line) for line in (output / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(samples[1]["elapsed_seconds"], 30)
        self.assertIn("observation_gap_exceeded", summary["observed_failures"])
        self.assertFalse(summary["route_window_evidence"]["windows"][0]["coverage_verified"])
        self.assertEqual(summary["policy"]["route_windows"]["maximum_sampling_gap_seconds"], 20)
        self.assertEqual(code, 1)
        self.assertFalse(summary["passed"])

    def test_auxiliary_crossing_duration_preserves_one_final_sample_and_cannot_pass(self):
        code, summary, output = self.run_observation("route", process_sample_cost=0,
            snapshot_period=1, auxiliary_delays=(62,))
        samples = [json.loads(line) for line in (output / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([sample["elapsed_seconds"] for sample in samples], [0, 62])
        self.assertEqual(summary["policy"]["duration"], 60)
        self.assertIn("observation_gap_exceeded", summary["observed_failures"])
        self.assertEqual(code, 1)
        self.assertFalse(summary["passed"])

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


class AuxiliaryTest(unittest.TestCase):
    def setUp(self):
        self.paths = [r"\GPU Process Memory(*)\Shared Usage", r"\GPU Process Memory(*)\Dedicated Usage"]
        self.plan, self.launch = {"java": "java.exe"}, {"pid": 999}

    def test_gpu_query_scopes_wildcard_instances_and_preserves_counter_names(self):
        paths = [r"\\host\custom collection(*)\本地计数器", r"\custom(pid_999_fixed)\Other"]
        self.assertEqual(observer.gpu_process_paths(paths, 999),
            [r"\\host\custom collection(pid_999_*)\本地计数器", paths[1]])

    def test_complete_process_gpu_counters_pass_and_query_only_this_pid(self):
        values = [{"Path": path, "InstanceName": "pid_999_luid_0_phys_0", "CookedValue": amount, "Status": 0}
            for path, amount in zip(self.paths, (16, 32))]
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(values), stderr="")
        with mock.patch.object(observer.subprocess, "run", return_value=completed) as run:
            result = observer.auxiliary(self.plan, self.launch, self.paths, False)["gpu"]
        self.assertTrue(result["available"])
        self.assertEqual(result["totals_by_counter"], {"Shared Usage": 16, "Dedicated Usage": 32})
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["paths"], [path.replace("(*)", "(pid_999_*)") for path in self.paths])
        self.assertEqual(result["paths"], self.paths)
        self.assertEqual(result["raw_stdout"], completed.stdout)

    def test_gpu_query_failure_retains_stdout_stderr_and_exit_status(self):
        completed = SimpleNamespace(returncode=1, stdout="partial output", stderr="native counter failure")
        with mock.patch.object(observer.subprocess, "run", return_value=completed):
            result = observer.auxiliary(self.plan, self.launch, self.paths, False)["gpu"]
        self.assertFalse(result["available"])
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["raw_stdout"], completed.stdout)
        self.assertEqual(result["raw_stderr"], completed.stderr)

    def test_missing_or_invalid_gpu_counter_still_fails(self):
        shared = {"Path": self.paths[0], "CookedValue": 16, "Status": 0}
        dedicated = {"Path": self.paths[1], "CookedValue": 32, "Status": 0}
        for values in ([shared], [shared, {**dedicated, "Status": 2}], [shared, {**dedicated, "CookedValue": float("nan")}], []):
            with self.subTest(values=values):
                completed = SimpleNamespace(returncode=0, stdout=json.dumps(values), stderr="")
                with mock.patch.object(observer.subprocess, "run", return_value=completed):
                    result = observer.auxiliary(self.plan, self.launch, self.paths, False)["gpu"]
                self.assertFalse(result["available"])


class RouteWindowsTest(unittest.TestCase):
    def make_windows(self, progress=lambda elapsed: elapsed, identifier=lambda elapsed: 7, omit=lambda elapsed: False):
        windows = observer.RouteWindows(60, 3, 0.01, 5, 1)
        records = []
        for elapsed in range(0, 61, 5):
            if not omit(elapsed):
                records.append(windows.add(elapsed, self.observation(elapsed, progress(elapsed), identifier(elapsed))))
        return windows, records

    def observation(self, elapsed, progress=0, identifier=7, verified=True):
        return {"verified": verified, "state": {"timestamp": str(elapsed), "vehicles": [{"id": identifier, "railProgress": progress}]}}

    def test_distributed_same_id_motion_passes_each_window(self):
        windows, records = self.make_windows()
        self.assertTrue(windows.summary()["passed"])
        self.assertTrue(all(window["coverage_verified"] and window["motion_verified"] for window in windows.summary()["windows"]))
        self.assertEqual(records[-1]["index"], 2)
        self.assertEqual(records[1]["same_id_progress_displacements"][0]["absolute_progress_displacement"], 5)

    def test_only_early_motion_fails_later_windows(self):
        windows, _ = self.make_windows(progress=lambda elapsed: min(elapsed, 15))
        self.assertFalse(windows.summary()["passed"])
        self.assertEqual([window["motion_verified"] for window in windows.summary()["windows"]], [True, False, False])

    def test_vehicle_id_replacement_does_not_establish_motion(self):
        windows, _ = self.make_windows(progress=lambda elapsed: 10, identifier=lambda elapsed: elapsed)
        self.assertFalse(windows.summary()["passed"])
        self.assertTrue(all(window["same_id_pair_count"] == 0 for window in windows.summary()["windows"]))

    def test_missing_middle_window_cannot_pass(self):
        windows, _ = self.make_windows(omit=lambda elapsed: 20 <= elapsed < 40)
        self.assertFalse(windows.summary()["passed"])
        self.assertEqual(windows.summary()["windows"][1]["sample_count"], 0)
        self.assertFalse(windows.summary()["windows"][1]["coverage_verified"])

    def test_motion_without_window_edge_coverage_cannot_pass(self):
        windows, _ = self.make_windows(omit=lambda elapsed: elapsed == 35)
        middle = windows.summary()["windows"][1]
        self.assertTrue(middle["motion_verified"])
        self.assertFalse(middle["coverage_verified"])
        self.assertFalse(windows.summary()["passed"])

    def test_sampling_gap_or_unverified_state_breaks_window_coverage(self):
        windows, _ = self.make_windows(omit=lambda elapsed: elapsed == 10)
        self.assertFalse(windows.summary()["passed"])
        self.assertEqual(windows.summary()["windows"][0]["maximum_observed_gap_seconds"], 10)
        windows = observer.RouteWindows(60, 3, 0.01, 5, 1)
        windows.add(0, self.observation(0))
        windows.add(5, self.observation(5, 1, verified=False))
        after = windows.add(10, self.observation(10, 2))
        self.assertEqual(after["same_id_progress_displacements"], [])
        self.assertFalse(windows.summary()["windows"][0]["coverage_verified"])

    def test_no_motion_is_paired_across_window_boundary(self):
        windows = observer.RouteWindows(60, 3, 0.01, 5, 1)
        windows.add(15, self.observation(15, 0))
        boundary = windows.add(20, self.observation(20, 10))
        self.assertEqual(boundary["same_id_progress_displacements"], [])
        self.assertEqual(windows.summary()["windows"][1]["same_id_pair_count"], 0)

    def test_invalid_or_duplicate_trajectory_is_ineligible(self):
        for vehicles in ([{"id": 7}], [{"id": 7, "railProgress": float("nan")}],
                [{"id": 7, "railProgress": float("inf")}], [{"id": False, "railProgress": 1}],
                [{"id": 7, "railProgress": True}], [{"id": 7, "railProgress": 1}, {"id": 7, "railProgress": 2}],
                [None], {"id": 7, "railProgress": 1}):
            with self.subTest(vehicles=vehicles):
                windows = observer.RouteWindows(60, 3, 0.01, 5, 1)
                record = windows.add(0, {"verified": True, "state": {"vehicles": vehicles}})
                self.assertFalse(record["eligible"])
                self.assertTrue(record["invalid_trajectory_records"])

    def test_window_policy_rejects_single_or_invalid_windows(self):
        for count in (0, 1, True, 3.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                observer.RouteWindows(60, count, 0.01, 5, 1)
        for duration, displacement, interval, freshness in ((0, 0.01, 5, 1), (60, 0, 5, 1),
                (60, float("nan"), 5, 1), (60, 0.01, float("inf"), 1), (60, 0.01, 5, 0)):
            with self.subTest(values=(duration, displacement, interval, freshness)), self.assertRaises(ValueError):
                observer.RouteWindows(duration, 3, displacement, interval, freshness)


if __name__ == "__main__":
    unittest.main()
