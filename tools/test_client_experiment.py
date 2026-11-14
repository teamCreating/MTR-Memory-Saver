"""Synthetic evidence tests only: these tests never start Minecraft or a JVM."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

import client_experiment as client
import client_experiment_analysis as analysis


def policy():
    result = client.read(client.ROOT / "config/client-experiment.json")
    result.update(startup_timeout_seconds=20, warmup_seconds=2, measurement_seconds=6,
                  sample_interval_seconds=1, maximum_sample_gap_seconds=2, snapshot_freshness_seconds=2)
    return result


def scenario():
    return {"schema": 1, "scenario_name": "Synthetic official scene", "world_name": "fixture-world",
            "expected_registration": {"declarations": 12, "distinct_ids": 11},
            "camera": {"dimension": "minecraft:overworld", "player": {"x": 0, "y": 64, "z": 0, "yaw": 0, "pitch": 0},
                       "maximum_position_error": 1, "maximum_angle_error": 2},
            "route": {"description": "Observe a fixed native route", "route_ids": [10], "vehicle_ids": [9]},
            "cache_policy": "fresh_jvm_warm_os_cache",
            "observation": {"require_world": True, "require_unpaused": True, "require_train": True, "minimum_train_displacement": 1},
            "machine_context": {"hardware": "Fixture", "windows": "Fixture OS", "power_mode": "Fixed", "background_workload": "None"},
            "warmup": {"duration_seconds": 2, "description": "Observe settled native world"}}


def evidence(mode="plain", *, pid=10, offset=0, private=100):
    created = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=offset)
    stamp = lambda seconds: (created + dt.timedelta(seconds=seconds)).isoformat()
    snapshots = []
    for seconds in range(1, 11):
        snapshot = {"schema_version": 1, "probe_kind": "official-native-observer", "pid": pid,
            "process_created": stamp(0), "observed_at": stamp(seconds), "registered_count": 11,
            "registered_declarations": 12, "native_pending": 0, "native_settled": True,
            "resource_epochs": {"in_flight": 0}, "in_world": True, "paused": False, "screen": None,
            "heap": {"used_bytes": 50, "max_bytes": 1000}, "observation_errors": 0,
            "capabilities": {name: True for name in ("native_pending", "registration_counts", "native_epochs", "heap", "world", "train_state", "cache_state")},
            "world": {"dimension": "minecraft:overworld", "player": dict(scenario()["camera"]["player"])},
            "train_state": {"available": True, "vehicles": [{"id": 9, "route_id": 10, "rail_progress": seconds}]}}
        snapshots.append({"observed_at": stamp(seconds), "os": {"running": True, "working_set": 110,
            "private_usage": private, "peak_working_set_since_process_start": 120}, "native": snapshot, "errors": [],
            "client_log_witness": {"bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()}})
    result = {"schema": 1, "status": "complete", "process": {"pid": pid, "created": stamp(0)},
              "windows": {"startup": {"start": stamp(0), "end": stamp(2)}, "warmup": {"start": stamp(2), "end": stamp(4)},
                          "steady": {"start": stamp(4), "end": stamp(10)}},
              "samples": snapshots,
              "epochs": [{"pid": pid, "process_created": stamp(0), "timestamp": stamp(seconds), "sequence": 1, "phase": phase}
                         for seconds, phase in ((.5, "start"), (1.5, "return"))],
              "jfr_events": [], "jfr_coverage": None, "cleanup": {"exited": True}}
    result.update(measurement_completed_at=stamp(10), measurement_process_running=True)
    result["client_diagnostics"] = {"scanned": True, "unreviewed_native": [], "other_errors_requiring_contextual_review": []}
    result["client_log_completeness"] = {"passed": True}
    if mode == "profile":
        result["jfr_coverage"] = {"start": stamp(0), "end": stamp(12), "readable": True}
        result["jfr_events"] = [{"type": "mtrtest.ClientFrame", "values": {"startTime": stamp(seconds / 2), "duration": "PT0S",
            "intervalMs": 16, "inWorld": True, "paused": False, "screen": "game"}} for seconds in range(8, 21)]
    return result


class PolicyAndScheduleTests(unittest.TestCase):
    def test_default_is_48_balanced_independent_jvms(self):
        config = client.read(client.ROOT / "config/client-experiment.json")
        trials = analysis.schedule(config)
        self.assertEqual(len(trials), 48)
        self.assertEqual(trials, analysis.schedule(config))
        self.assertEqual(len({trial["id"] for trial in trials}), 48)
        for comparison in ("aa", "ab"):
            for mode in analysis.MODES:
                starts = [t["arm"] for t in trials if t["comparison"] == comparison and t["instrumentation"] == mode][::2]
                self.assertEqual(starts.count("a"), 3)
                self.assertEqual(starts.count("b"), 3)
        self.assertTrue(all(t["role"] == "baseline" for t in trials if t["comparison"] == "aa"))

    def test_seed_changes_order_without_changing_design(self):
        config = policy()
        before = analysis.schedule(config)
        config["seed"] += 1
        after = analysis.schedule(config)
        self.assertNotEqual(before, after)
        self.assertEqual({t["id"] for t in before}, {t["id"] for t in after})

    def test_rejects_unbalanced_or_insufficient_pairs(self):
        for count in (1, 5, 7):
            config = policy()
            config["pairs"] = count
            with self.assertRaises(ValueError):
                analysis.validate_policy(config)

    def test_plain_cannot_claim_jfr_endpoints(self):
        config = policy()
        config["guardrails"][2]["instrumentation"] = "plain"
        with self.assertRaisesRegex(ValueError, "JFR"):
            analysis.validate_policy(config)

    def test_aa_must_cover_each_mode_and_unit(self):
        config = policy()
        config["aa_equivalence"].pop()
        with self.assertRaisesRegex(ValueError, "A/A"):
            analysis.validate_policy(config)

    def test_invalid_finite_and_duplicate_budgets_fail(self):
        for mutation in (lambda c: c.update(measurement_seconds=float("nan")),
                         lambda c: c["guardrails"].append(copy.deepcopy(c["guardrails"][0]))):
            config = policy()
            mutation(config)
            with self.assertRaises(ValueError):
                analysis.validate_policy(config)


class ObservationTests(unittest.TestCase):
    def assess(self, value, mode="plain"):
        return analysis.assess_observation(value, policy(), scenario(), mode)

    def test_plain_has_independent_metrics_and_profile_metrics_unavailable(self):
        result = self.assess(evidence())
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["metrics"]["loading_ms"], 2000)
        self.assertEqual(result["metrics"]["steady_private_bytes"], 100)
        self.assertEqual(set(result["unavailable_metrics"]), analysis.PROFILE_METRICS)

    def test_profile_without_gc_has_observed_zero_counts(self):
        result = self.assess(evidence("profile"), "profile")
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["metrics"]["frame_p99_ms"], 16)
        self.assertEqual(result["metrics"]["full_gc_count"], 0)

    def test_registration_identity_and_unsettled_work_fail(self):
        for field, value in (("pid", 99), ("process_created", None), ("registered_count", 10),
                             ("native_pending", 1), ("observation_errors", 1), ("paused", True), ("screen", "menu")):
            with self.subTest(field=field):
                record = evidence()
                record["samples"][5]["native"][field] = value
                self.assertFalse(self.assess(record)["passed"])

    def test_missing_heap_or_os_observation_cannot_be_zero_filled(self):
        for group, field in (("os", "private_usage"), ("native", "heap")):
            record = evidence()
            del record["samples"][5][group][field]
            self.assertFalse(self.assess(record)["passed"])

    def test_stale_duplicate_or_missing_sample_fails_coverage(self):
        for mutate in (lambda r: r["samples"][5]["native"].update(observed_at=r["samples"][4]["native"]["observed_at"]),
                       lambda r: r["samples"][5]["native"].update(observed_at=r["samples"][0]["native"]["observed_at"]),
                       lambda r: r["samples"].__delitem__(slice(4, 8))):
            record = evidence()
            mutate(record)
            self.assertFalse(self.assess(record)["passed"])

    def test_native_return_without_settled_anchor_cannot_pass(self):
        record = evidence()
        record["samples"][1]["native"]["observed_at"] = record["samples"][0]["observed_at"]
        self.assertFalse(self.assess(record)["passed"])

    def test_unpaired_epoch_and_unplanned_reload_fail(self):
        for mutate in (lambda r: r["epochs"].pop(), lambda r: r["epochs"].append({**r["epochs"][0], "timestamp": r["samples"][5]["observed_at"], "sequence": 2})):
            record = evidence()
            mutate(record)
            self.assertFalse(self.assess(record)["passed"])

    def test_frozen_world_camera_route_and_motion_are_observed(self):
        for mutate in (lambda s: s["world"].update(dimension="different"),
                       lambda s: s["world"]["player"].update(x=100),
                       lambda s: s["train_state"]["vehicles"][0].update(route_id=11),
                       lambda s: s["train_state"]["vehicles"][0].update(rail_progress=0)):
            record = evidence()
            for sample in record["samples"]:
                mutate(sample["native"])
            self.assertFalse(self.assess(record)["passed"])

    def test_window_duration_and_cleanup_are_required(self):
        record = evidence()
        record["cleanup"]["exited"] = False
        self.assertFalse(self.assess(record)["passed"])
        record = evidence()
        record["windows"]["steady"]["end"] = record["samples"][8]["observed_at"]
        self.assertFalse(self.assess(record)["passed"])
        record = evidence()
        record["measurement_completed_at"] = record["samples"][8]["observed_at"]
        self.assertFalse(self.assess(record)["passed"])

    def test_plain_extra_instrumentation_is_not_ignored(self):
        self.assertFalse(self.assess(evidence("profile"))["passed"])

    def test_unreviewed_native_errors_and_invalid_models_prevent_qualification(self):
        for log in ("[Render thread/ERROR] [MinecraftTransitRailway] Unknown native failure", "[MTR] Invalid model: transparent.png", "Failed to parse resource model", "OutOfMemoryError", "Mixin apply failed"):
            record = evidence()
            record["client_diagnostics"] = analysis.native_diagnostics(log)
            self.assertFalse(self.assess(record)["passed"])
            self.assertEqual(record["client_diagnostics"]["unreviewed_native"][0]["line"], 1)
        record = evidence()
        del record["client_diagnostics"]
        self.assertFalse(self.assess(record)["passed"])

    def test_other_errors_are_preserved_separately_for_contextual_review(self):
        record = evidence()
        record["client_diagnostics"] = analysis.native_diagnostics("[Render thread/ERROR] [authlib] User properties HTTP 401")
        self.assertEqual(record["client_diagnostics"]["unreviewed_native"], [])
        self.assertEqual(len(record["client_diagnostics"]["other_errors_requiring_contextual_review"]), 1)
        self.assertTrue(self.assess(record)["passed"])

    def test_log_prefix_proof_rejects_missing_startup_truncation_and_rewrites(self):
        raw = b"[main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, exact-instance]\n[INFO] Ready\n"
        samples = [{"client_log_witness": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}]
        self.assertTrue(analysis.client_log_completeness(raw, samples, "exact-instance")["passed"])
        for changed in (raw[10:], raw[:-5], raw.replace(b"Ready", b"Other")):
            self.assertFalse(analysis.client_log_completeness(changed, samples, "exact-instance")["passed"])
        self.assertFalse(analysis.client_log_completeness(raw, samples, "wrong-instance")["passed"])
        self.assertFalse(analysis.client_log_completeness(raw, [], "exact-instance")["passed"])


class JfrTests(unittest.TestCase):
    def test_truncated_recording_start_end_or_missing_frames_fails(self):
        for mutate in (lambda r: r["jfr_coverage"].update(end=r["samples"][8]["observed_at"]),
                       lambda r: r["jfr_coverage"].update(start=r["samples"][2]["observed_at"]),
                       lambda r: r["jfr_events"].clear()):
            record = evidence("profile")
            mutate(record)
            self.assertFalse(analysis.assess_observation(record, policy(), scenario(), "profile")["passed"])

    def test_full_gc_duration_uses_matching_gc_id(self):
        record = evidence("profile")
        stamp = record["samples"][5]["observed_at"]
        record["jfr_events"] += [{"type": "jdk.GarbageCollection", "values": {"startTime": stamp, "duration": "PT0.03S", "gcId": 3, "name": "G1Full"}},
                                 {"type": "jdk.GCPhasePause", "values": {"startTime": stamp, "duration": "PT0.02S", "gcId": 3}}]
        result = analysis.assess_observation(record, policy(), scenario(), "profile")
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["metrics"]["full_gc_count"], 1)
        self.assertEqual(result["metrics"]["full_gc_pause_max_ms"], 20)

    def test_orphan_pause_duplicate_gc_and_boundary_crossing_fail(self):
        record = evidence("profile")
        stamp = record["samples"][5]["observed_at"]
        gc = {"type": "jdk.GarbageCollection", "values": {"startTime": stamp, "duration": "PT0.02S", "gcId": 2, "name": "G1Full"}}
        variants = [[{"type": "jdk.GCPhasePause", "values": {"startTime": stamp, "duration": "PT0.01S", "gcId": 9}}],
                    [gc, gc], [{"type": "jdk.GarbageCollection", "values": {"startTime": record["samples"][2]["observed_at"], "duration": "PT2S", "gcId": 2, "name": "G1Full"}}]]
        for events in variants:
            changed = copy.deepcopy(record)
            changed["jfr_events"] += events
            self.assertFalse(analysis.assess_observation(changed, policy(), scenario(), "profile")["passed"])

    def test_frame_gap_or_outside_world_fails(self):
        record = evidence("profile")
        record["jfr_events"] = record["jfr_events"][:2]
        self.assertFalse(analysis.assess_observation(record, policy(), scenario(), "profile")["passed"])
        record = evidence("profile")
        record["jfr_events"][3]["values"]["screen"] = "menu"
        self.assertFalse(analysis.assess_observation(record, policy(), scenario(), "profile")["passed"])

    def test_conservative_summary_coverage_and_unreadable_input(self):
        coverage = client.summary_coverage(" Start: 2026-11-15 00:00:00 (UTC)\n Duration: 12 s\n")
        self.assertEqual(coverage["end"], "2026-11-15T00:00:12+00:00")
        self.assertEqual(coverage["end_bound"], "conservative_whole_second")
        with self.assertRaises(ValueError):
            client.summary_coverage("jcmd returned an argument error")


class IndependentDecisionTests(unittest.TestCase):
    def state(self):
        config = policy()
        scheduled = analysis.schedule(config)
        prepared = {role + "_" + mode: {"qualification_key": role + "_" + mode} for role in analysis.ROLES for mode in analysis.MODES}
        plan = {"policy": config, "schedule": scheduled, "prepared": prepared, "scenario": scenario()}
        trials = []
        for index, spec in enumerate(scheduled):
            role = spec["role"]
            trials.append({**spec, "status": "complete", "qualification_key": role + "_" + spec["instrumentation"],
                           "evidence": evidence(spec["instrumentation"], pid=index + 1, offset=index * 100, private=80 if role == "candidate" else 100)})
        return plan, {"status": "complete", "trials": trials}

    def test_complete_independent_aa_ab_and_instrumentation_gates_pass(self):
        plan, execution = self.state()
        result = analysis.analyze(plan, execution)
        self.assertEqual(result["instrumented_comparison_status"], "pass", result)
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse(result["performance_accepted"])
        self.assertEqual(result["pending_gates"], ["neutral_probe_off_calibration"])
        self.assertEqual(result["failure_denominator"]["scheduled_trials"], 48)

    def test_missing_failed_duplicate_order_and_reused_processes_fail_denominator(self):
        for mutate in (lambda s: s["trials"].pop(), lambda s: s["trials"][0].update(status="failed"),
                       lambda s: s["trials"].reverse(), lambda s: s["trials"].append(copy.deepcopy(s["trials"][0])),
                       lambda s: s["trials"][1]["evidence"].update(process=copy.deepcopy(s["trials"][0]["evidence"]["process"]))):
            plan, execution = self.state()
            mutate(execution)
            result = analysis.analyze(plan, execution)
            self.assertEqual(result["status"], "invalid")
            self.assertFalse(result["performance_accepted"])
            self.assertEqual(result["failure_denominator"]["scheduled_trials"], 48)

    def test_qualification_from_another_mode_cannot_be_borrowed(self):
        plan, execution = self.state()
        execution["trials"][0]["qualification_key"] = "other-mode"
        self.assertEqual(analysis.analyze(plan, execution)["status"], "invalid")

    def test_failure_of_aa_equivalence_prevents_ab_acceptance(self):
        plan, execution = self.state()
        for trial in execution["trials"]:
            if trial["comparison"] == "aa" and trial["arm"] == "b" and trial["instrumentation"] == "plain":
                for sample in trial["evidence"]["samples"]:
                    sample["os"]["private_usage"] = 120
        result = analysis.analyze(plan, execution)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["gates"]["aa_plain_steady_private_bytes"], "fail")

    def test_instrumentation_equivalence_is_a_required_gate(self):
        plan, execution = self.state()
        for trial in execution["trials"]:
            if trial["instrumentation"] == "profile":
                for sample in trial["evidence"]["samples"]:
                    sample["os"]["private_usage"] *= 1.2
        result = analysis.analyze(plan, execution)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["gates"]["instrumentation_baseline_steady_private_bytes"], "fail")

    def test_zero_reference_has_no_percent_ratio_but_absolute_remains_valid(self):
        pairs = [({"gc": 0}, {"gc": 0})] * 6
        relative = analysis.paired_summary(pairs, "gc", "percent", .95)
        absolute = analysis.paired_summary(pairs, "gc", "absolute", .95)
        self.assertEqual(analysis.decision(relative, 0, 6), "inconclusive")
        self.assertEqual(analysis.decision(absolute, 0, 6, equivalence=True), "pass")


class PreparationBoundaryTests(unittest.TestCase):
    def test_scenario_rejects_undeclared_or_invalid_camera_route_context(self):
        self.assertEqual(client.scenario_from_controls({"context": {"declarations": scenario()}}), scenario())
        for mutate in (lambda s: s["camera"].clear(), lambda s: s["route"].update(route_ids=[]),
                       lambda s: s.pop("machine_context"), lambda s: s["observation"].update(require_train=False)):
            value = scenario()
            mutate(value)
            with self.assertRaises(ValueError):
                client.scenario_from_controls({"context": {"declarations": value}})

    def test_mode_controls_remove_only_frozen_profiling_additions(self):
        common = {"jvm": {"arguments": ["-Xmx3G", "-XX:+UseG1GC"]}, "launcher": {"command_template": ["java", "-Xmx3G", "-XX:+UseG1GC"]}}
        profiled = copy.deepcopy(common)
        for arguments in (profiled["jvm"]["arguments"], profiled["launcher"]["command_template"]):
            arguments.extend(["-XX:StartFlightRecording=name=acceptance", "-Xlog:gc*,safepoint:file=gc.log"])
        self.assertEqual(client.mode_independent_controls(profiled), common)
        profiled["jvm"]["arguments"].append("-XX:NativeMemoryTracking=summary")
        self.assertNotEqual(client.mode_independent_controls(profiled), common)

    def test_raw_evidence_changed_or_escaped_attempt_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "samples.jsonl").write_text("{}\n", encoding="utf-8")
            files = client.raw_files(root)
            client.verify_raw_files(root, files)
            (root / "samples.jsonl").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                client.verify_raw_files(root, files)
            external = root.parent / (root.name + ".external")
            try:
                external.write_text("outside", encoding="utf-8")
                with self.assertRaises(ValueError):
                    client.verify_raw_files(root, [{"relative_path": "../" + external.name, "sha256": client.digest(external), "bytes": external.stat().st_size}])
            finally:
                external.unlink(missing_ok=True)

    def test_missing_baseline_preparation_preserves_failed_attempt_and_does_not_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "attempt"
            args = SimpleNamespace(output=output, policy=client.ROOT / "config/client-experiment.json", qualification=[],
                baseline_plain=Path(temporary) / "missing.json", baseline_profile=Path(temporary) / "missing.json",
                candidate_plain=Path(temporary) / "missing.json", candidate_profile=Path(temporary) / "missing.json", environment_notes="Fixture")
            with mock.patch.object(client, "environment", return_value={}), mock.patch.object(client.packaged, "launch") as launch:
                with self.assertRaises(FileNotFoundError):
                    client.make_plan(args)
                launch.assert_not_called()
            self.assertEqual(client.read(output / "attempt.json")["status"], "failed")
            self.assertFalse((output / "plan.json").exists())

    def test_missing_qualification_preserves_failure_without_substituting_baseline(self):
        config = policy()
        def descriptor(path, role, mode, ignored):
            return {"role": role, "instrumentation": mode, "core_jvm_arguments": ["-XX:+UseG1GC"],
                "scenario": scenario(), "artifact_sha256": "b" if role == "baseline" else "c", "controls": {"jvm": {"arguments": ["-XX:+UseG1GC"]}},
                "qualification_fields": {"target": "official-nf248", "neutral_probe_sha256": "p"}, "qualification_key": role + "_" + mode}
        with tempfile.TemporaryDirectory() as temporary:
            policy_path = Path(temporary) / "policy.json"
            client.save(policy_path, config)
            args = SimpleNamespace(output=Path(temporary) / "attempt", policy=policy_path, qualification=[], environment_notes="Fixture",
                baseline_plain=Path("a"), baseline_profile=Path("a"), candidate_plain=Path("b"), candidate_profile=Path("b"))
            with mock.patch.object(client, "environment", return_value={}), mock.patch.object(client, "prepared_descriptor", side_effect=descriptor):
                with self.assertRaisesRegex(ValueError, "Missing current exact qualification: baseline_plain"):
                    client.make_plan(args)
            result = client.read(args.output / "attempt.json")
            self.assertEqual(result["status"], "failed")
            self.assertIn("no baseline substitution", result["error"])
            self.assertFalse((args.output / "plan.json").exists())


class OwnedProcessLifecycleTests(unittest.TestCase):
    """Mock handles and clock only; no child process is actually launched."""
    def collect(self, root, *, exporter_error=False, interrupt=False):
        config, scene = policy(), scenario()
        clock = {"seconds": 1}
        base = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc)
        timestamp = lambda: (base + dt.timedelta(seconds=clock["seconds"])).isoformat()
        order = []
        process = mock.Mock(spec=subprocess.Popen)
        process.pid = 111
        process.poll.return_value = None
        process.wait.return_value = 17
        def terminate():
            order.append("terminate")
            process.poll.return_value = 17
        process.terminate.side_effect = terminate
        observer = mock.Mock()
        observer.identity = {"pid": 111, "created": base.isoformat(), "executable": "java.exe", "command": "java.exe"}
        observer.created = base.isoformat()
        def sample():
            if interrupt and clock["seconds"] >= 4:
                raise KeyboardInterrupt()
            return {"running": True, "working_set": 110, "private_usage": 100, "peak_working_set_since_process_start": 120}
        observer.sample.side_effect = sample
        instance = root / "instance"
        def write_snapshot():
            state = copy.deepcopy(evidence(pid=111)["samples"][0]["native"])
            state.update(observed_at=timestamp())
            state["train_state"]["vehicles"][0]["rail_progress"] = clock["seconds"]
            if clock["seconds"] < 3:
                state.update(in_world=False, world=None, train_state=None, screen="loading")
            client.save(instance / "game-probe/native-observer.json", state)
        def clone(descriptor, destination):
            (destination / "game-probe").mkdir(parents=True)
            (destination / "logs").mkdir()
            (destination / "logs/latest.log").write_text("[main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, " + str(destination) + "]\n", encoding="utf-8")
            (destination / "game-probe/native-resource-epochs.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in evidence(pid=111)["epochs"]), encoding="utf-8")
            write_snapshot()
            return {"instance": str(destination), "java": "java.exe", "jfr": True, "heap_mib": 3072, "smoke": False}
        def sleep(seconds):
            clock["seconds"] += seconds
            write_snapshot()
        def export(plan, child, directory, output):
            order.append("export")
            if exporter_error:
                raise ValueError("Actual export failed")
            profile = evidence("profile", pid=111)
            return profile["jfr_events"], profile["jfr_coverage"]
        descriptor = {"role": "baseline", "instrumentation": "profile", "qualification_key": "exact-group", "scenario": scene,
                      "probe_metadata": {"epochs_path": "game-probe/native-resource-epochs.jsonl", "snapshot_path": "game-probe/native-observer.json"}}
        patches = [mock.patch.object(client, "verify_descriptor"), mock.patch.object(client, "clone_prepared", side_effect=clone),
                   mock.patch.object(client.packaged, "launch", return_value=process), mock.patch.object(client, "WindowsProcess", return_value=observer),
                   mock.patch.object(client, "windows_arguments", return_value=["java.exe"]),
                   mock.patch.object(client, "read", wraps=client.read), mock.patch.object(client, "now", side_effect=timestamp),
                   mock.patch.object(client.time, "monotonic", side_effect=lambda: clock["seconds"]),
                   mock.patch.object(client.time, "sleep", side_effect=sleep), mock.patch.object(client, "export_jfr", side_effect=export)]
        for patch in patches:
            patch.start()
        try:
            # The launcher writes this in production. Simulate its raw capture.
            original_read = client.read._mock_wraps
            client.read.side_effect = lambda path: {"pid": 111, "command": ["java.exe"]} if Path(path).name == "packaged-client-launch.json" else original_read(path)
            if interrupt:
                with self.assertRaises(KeyboardInterrupt):
                    client.collect_trial(descriptor, config, root)
                result = (original_read(root / "observation.json"), original_read(root / "result.json"))
            else:
                result = client.collect_trial(descriptor, config, root)
            return result, process, observer, order
        finally:
            for patch in reversed(patches):
                patch.stop()
            client.RETAINED_PROCESSES.pop(111, None)

    def test_normal_profile_exports_before_actual_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            (record, result), child, observer, order = self.collect(Path(temporary) / "trial")
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(order, ["export", "terminate"])
            self.assertTrue(record["cleanup"]["exited"])
            observer.close.assert_called_once()
            # Native settled at t=2; world/camera ready at t=3 stays separate.
            self.assertEqual(result["metrics"]["loading_ms"], 2000)
            self.assertNotEqual(record["windows"]["startup"]["end"], record["windows"]["warmup"]["start"])

    def test_failed_profile_export_preserves_live_handle_and_stops_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "trial"
            (record, result), child, observer, order = self.collect(root, exporter_error=True)
            self.assertFalse(result["passed"])
            self.assertEqual(order, ["export", "export"])
            child.terminate.assert_not_called()
            observer.close.assert_not_called()
            self.assertFalse(record["cleanup"]["exited"])
            self.assertTrue((root / "preserved-process.json").is_file())

    def test_interrupt_preserves_verified_partial_before_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            (record, result), child, observer, order = self.collect(Path(temporary) / "trial", interrupt=True)
            self.assertFalse(result["passed"])
            self.assertEqual(record["status"], "interrupted")
            self.assertEqual(order, ["export", "terminate"])
            self.assertTrue(record["jfr_export"]["partial_observation"])

    def test_interrupt_with_failed_partial_export_never_terminates(self):
        with tempfile.TemporaryDirectory() as temporary:
            (record, result), child, observer, order = self.collect(Path(temporary) / "trial", interrupt=True, exporter_error=True)
            self.assertFalse(record["cleanup"]["exited"])
            child.terminate.assert_not_called()
            self.assertFalse(result["passed"])


class ExportHelperTests(unittest.TestCase):
    def run_export(self, root, *, missing_dump=False, bad_summary=False, summary_failure=False):
        instance = root / "instance"
        instance.mkdir()
        child = mock.Mock()
        child.pid = 123
        child.poll.return_value = None
        def helper(command, **kwargs):
            if command[2] == "JFR.dump":
                filename = next(item.split("=", 1)[1] for item in command if item.startswith("filename="))
                if not missing_dump:
                    (instance / filename).write_bytes(b"raw fixture recording")
                kwargs["stdout"].write("Command receipt\n")
                return SimpleNamespace(returncode=0)
            if command[1] == "summary":
                kwargs["stdout"].write("argument error\n" if bad_summary else "Start: 2026-11-15 00:00:00 (UTC)\nDuration: 12 s\n")
                return SimpleNamespace(returncode=1 if summary_failure else 0)
            kwargs["stdout"].write(json.dumps({"recording": {"events": []}}))
            return SimpleNamespace(returncode=0)
        with mock.patch.object(client.subprocess, "run", side_effect=helper):
            return client.export_jfr({"java": str(root / "java.exe")}, child, instance, root)

    def test_actual_helper_path_publishes_only_verified_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events, coverage = self.run_export(root)
            self.assertEqual(events, [])
            self.assertTrue(coverage["readable"])
            self.assertEqual(client.read(root / "jfr-export-attempt-01/receipt.json")["status"], "verified")
            self.assertEqual((root / "recording.jfr").read_bytes(), b"raw fixture recording")

    def test_zero_exit_without_recording_is_not_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "jfr-dump"):
                self.run_export(root, missing_dump=True)
            self.assertEqual(client.read(root / "jfr-export-attempt-01/receipt.json")["status"], "failed")
            self.assertFalse((root / "recording.jfr").exists())

    def test_invalid_or_failed_summary_preserves_partial_bytes_without_publishing(self):
        for options in ({"bad_summary": True}, {"summary_failure": True}):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.assertRaises(ValueError):
                    self.run_export(root, **options)
                self.assertEqual((root / "jfr-export-attempt-01/recording.jfr").read_bytes(), b"raw fixture recording")
                self.assertFalse((root / "recording.jfr").exists())
                self.assertEqual(client.read(root / "jfr-export-attempt-01/receipt.json")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
