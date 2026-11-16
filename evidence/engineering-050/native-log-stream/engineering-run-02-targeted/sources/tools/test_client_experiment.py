"""Synthetic evidence tests only: these tests never start Minecraft or a JVM."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import shutil
from types import SimpleNamespace
import unittest
from unittest import mock

import client_experiment as client
import client_experiment_analysis as analysis
from test_native_diagnostic_review import fixture as diagnostic_fixture, evaluate as evaluate_diagnostics


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
    result = {"schema": 1, "status": "complete", "process": {"pid": pid, "created": stamp(0), "captured_at": stamp(.1)},
              "windows": {"startup": {"start": stamp(0), "end": stamp(2)}, "warmup": {"start": stamp(2), "end": stamp(4)},
                          "steady": {"start": stamp(4), "end": stamp(10)}},
              "samples": snapshots,
              "epochs": [{"pid": pid, "process_created": stamp(0), "timestamp": stamp(seconds), "sequence": 1, "phase": phase}
                         for seconds, phase in ((.5, "start"), (1.5, "return"))],
              "jfr_events": [], "jfr_coverage": None, "cleanup": {"exited": True}}
    result.update(measurement_completed_at=stamp(10), measurement_process_running=True)
    result.update(started_at=stamp(0), finished_at=stamp(11), qualification_key="fixture", capture_root="fixture-root",
                  launch={"timestamp": stamp(.05)}, run_start_sha256="fixture-start-sha")
    result["cleanup"]["timestamp"] = stamp(10.5)
    result["run_start"] = {"scope": "official_current_client_qualification", "root": "fixture-root", "started_at": stamp(0),
                           "trial_spec": None, "qualification_key": "fixture"}
    result["run_finish"] = {"scope": "official_current_client_qualification", "root": "fixture-root", "finished_at": stamp(11),
        "start_sha256": "fixture-start-sha", "process": {"pid": pid, "created": stamp(0)},
        "measurement_completed_at": stamp(10), "cleanup": copy.deepcopy(result["cleanup"])}
    diagnostic = diagnostic_fixture(result["process"], result["epochs"])
    result["epochs"] = diagnostic["epochs"]
    result["diagnostic_events"] = diagnostic["events"]
    result["client_diagnostics"] = evaluate_diagnostics(diagnostic)
    for sample in result["samples"]:
        sample["native"]["native_model_diagnostics"] = copy.deepcopy(diagnostic["snapshot"]["native_model_diagnostics"])
    result["client_log_completeness"] = {"passed": True}
    if mode == "profile":
        result["jfr_coverage"] = {"start": stamp(0), "end": stamp(12), "readable": True}
        result["jfr_events"] = [{"type": "mtrtest.ClientFrame", "values": {"startTime": stamp(seconds / 2), "duration": "PT0S",
            "intervalMs": 16, "inWorld": True, "paused": False, "screen": "game"}} for seconds in range(8, 21)]
    return result


def write_raw_qualification_fixture(root):
    """A complete plain raw fixture, accepted by the raw-audit layer before replay."""
    root.mkdir()
    instance = root / "instance"
    instance.mkdir()
    raw = evidence(pid=111)
    diagnostic = diagnostic_fixture(raw["process"], raw["epochs"])
    raw["capture_root"] = str(root.resolve())
    raw["run_start"]["root"] = str(root.resolve())
    raw["run_finish"]["root"] = str(root.resolve())
    java = str((root / "java.exe").resolve())
    prepared = {"instance": str(instance.resolve()), "java": java, "heap_mib": 3072, "smoke": False,
                "jfr": False, "jfr_max_size_bytes": None}
    arguments = client.packaged.jvm_arguments(prepared)
    command = [java, *arguments, "--gameDir", str(instance.resolve())]
    prepared["controls"] = {"launcher": {"command_template": client.packaged.command_template(command, instance.resolve(), java)},
                            "observer": {"target": diagnostic["metadata"]}}
    client.save(root / "prepared-plan.json", prepared)
    raw["launch"].update(pid=111, plan_sha256=client.digest(root / "prepared-plan.json"), command=command, jvm_arguments=arguments)
    raw["process"].update(executable=java, arguments=command)
    log = ("[main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, " + str(instance.resolve()) + "]\n" + diagnostic["log"] + "[INFO] Ready\n").encode()
    (root / "latest.log").write_bytes(log)
    for sample in raw["samples"]:
        sample["client_log_witness"] = {"bytes": len(log), "sha256": hashlib.sha256(log).hexdigest()}
    shutil.copyfile(client.DIAGNOSTIC_REVIEW, root / "diagnostic-review.json")
    raw["diagnostic_review_sha256"] = client.digest(root / "diagnostic-review.json")
    client.save(root / "native-observer-final.json", diagnostic["snapshot"])
    raw["client_diagnostics"] = client.assess_native_diagnostics(root, raw, diagnostic["metadata"], diagnostic["review"])
    raw["client_log_completeness"] = analysis.client_log_completeness(log, raw["samples"], instance.resolve())
    client.save(root / "run-start.json", raw["run_start"])
    raw["run_start_sha256"] = client.digest(root / "run-start.json")
    raw["run_finish"]["start_sha256"] = raw["run_start_sha256"]
    client.save(root / "run-finish.json", raw["run_finish"])
    client.save(root / "actual-process.json", raw["process"])
    client.save(root / "launch.json", raw["launch"])
    for name, items in (("samples.jsonl", raw["samples"]), ("native-resource-epochs.jsonl", raw["epochs"]),
                        ("native-invalid-model.jsonl", raw["diagnostic_events"])):
        (root / name).write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
    client.save(root / "observation.json", raw)
    return raw


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
        case = diagnostic_fixture(record["process"], record["epochs"])
        case["log"] += "[Render thread/ERROR] [authlib] User properties HTTP 401"
        record["client_diagnostics"] = evaluate_diagnostics(case)
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

    def test_full_gc_without_pause_or_duration_is_unavailable_and_failed(self):
        for missing in ("pause", "pause_duration", "gc_duration"):
            record = evidence("profile")
            stamp = record["samples"][5]["observed_at"]
            gc = {"type": "jdk.GarbageCollection", "values": {"startTime": stamp, "duration": "PT0.03S", "gcId": 99, "name": "G1Full"}}
            pause = {"type": "jdk.GCPhasePause", "values": {"startTime": stamp, "duration": "PT0.02S", "gcId": 99}}
            if missing == "gc_duration":
                del gc["values"]["duration"]
            if missing == "pause_duration":
                del pause["values"]["duration"]
            record["jfr_events"].append(gc)
            if missing != "pause":
                record["jfr_events"].append(pause)
            result = analysis.assess_observation(record, policy(), scenario(), "profile")
            self.assertFalse(result["passed"])
            self.assertIsNone(result["metrics"]["full_gc_pause_max_ms"])
            self.assertIsNone(result["metrics"]["gc_pause_total_ms"])

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
        plan = {"policy": config, "schedule": scheduled, "prepared": prepared, "scenario": scenario(),
                "qualification_processes": {key: {"pid": 1000 + index, "created": "2026-11-14T00:00:00+00:00"} for index, key in enumerate(prepared)}}
        trials = []
        for index, spec in enumerate(scheduled):
            role = spec["role"]
            raw = evidence(spec["instrumentation"], pid=index + 1, offset=index * 100, private=80 if role == "candidate" else 100)
            raw["qualification_key"] = role + "_" + spec["instrumentation"]
            raw["run_start"].update(scope="official_client_performance_trial", trial_spec=spec, qualification_key=raw["qualification_key"])
            raw["run_finish"]["scope"] = "official_client_performance_trial"
            trials.append({**spec, "status": "complete", "qualification_key": raw["qualification_key"], "evidence": raw,
                           "started_at": raw["started_at"], "finished_at": raw["finished_at"]})
        return plan, {"status": "complete", "trials": trials, "started_at": "2026-11-14T23:59:00+00:00",
                      "finished_at": "2026-11-15T02:00:00+00:00"}

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

    def test_qualifier_process_cannot_be_reused_even_with_timezone_reformatting(self):
        plan, execution = self.state()
        qualifier = copy.deepcopy(execution["trials"][0]["evidence"]["process"])
        qualifier["created"] = qualifier["created"].replace("+00:00", "Z")
        plan["qualification_processes"]["baseline_plain"] = qualifier
        result = analysis.analyze(plan, execution)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("Qualification JVM reused" in error for error in result["errors"]))

    def test_edited_summary_cannot_move_old_raw_process_into_a_new_window(self):
        plan, execution = self.state()
        trial = execution["trials"][0]
        trial["started_at"] = "2026-11-15T01:00:00+00:00"
        trial["evidence"]["run_start"]["started_at"] = trial["started_at"]
        trial["evidence"]["started_at"] = trial["started_at"]
        result = analysis.analyze(plan, execution)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("outside its raw execution window" in error for error in result["errors"]))

    def test_distinct_jvms_with_overlapping_or_reversed_windows_are_not_replicates(self):
        for reverse in (False, True):
            plan, execution = self.state()
            trial = execution["trials"][1]
            raw = evidence(trial["instrumentation"], pid=trial["evidence"]["process"]["pid"],
                           offset=-100 if reverse else 0, private=80 if trial["role"] == "candidate" else 100)
            raw["qualification_key"] = trial["qualification_key"]
            raw["run_start"].update(scope="official_client_performance_trial", trial_spec=plan["schedule"][1],
                                    qualification_key=trial["qualification_key"])
            raw["run_finish"]["scope"] = "official_client_performance_trial"
            trial.update(evidence=raw, started_at=raw["started_at"], finished_at=raw["finished_at"])
            execution["started_at"] = "2026-11-14T23:55:00+00:00"
            result = analysis.analyze(plan, execution)
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any("windows overlap or run outside" in error for error in result["errors"]))
            self.assertFalse(result["performance_accepted"])

    def test_actual_windows_must_fit_trial_and_experiment_receipts(self):
        for mutate in (lambda e: e.update(finished_at=e["started_at"]),
                       lambda e: e["trials"][0].update(finished_at=e["trials"][0]["started_at"]),
                       lambda e: e["trials"][0].pop("finished_at")):
            plan, execution = self.state()
            mutate(execution)
            result = analysis.analyze(plan, execution)
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any("execution window" in error or "chronology is unavailable" in error for error in result["errors"]))

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

    def test_raw_inventory_cannot_omit_duplicate_or_ignore_added_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "samples.jsonl").write_text("{}\n", encoding="utf-8")
            files = client.raw_files(root)
            for incomplete in ([], [*files, *files]):
                with self.assertRaisesRegex(ValueError, "inventory is incomplete, duplicated or changed"):
                    client.verify_raw_files(root, incomplete)
            (root / "jfr-export-attempt-01").mkdir()
            client.save(root / "jfr-export-attempt-01/receipt.json", {"status": "failed"})
            with self.assertRaisesRegex(ValueError, "inventory is incomplete, duplicated or changed"):
                client.verify_raw_files(root, files)
            client.verify_raw_files(root, client.raw_files(root))

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

    def test_source_change_during_capture_cannot_receive_a_new_current_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "capture.py"
            source.write_text("original capture behavior", encoding="utf-8")
            args = SimpleNamespace(output=root / "attempt", policy=client.ROOT / "config/client-experiment.json",
                                   prepared_plan=root / "prepared.json", role="baseline", instrumentation="plain")
            def collect(descriptor, frozen_policy, trial_root):
                trial_root.mkdir()
                client.save(trial_root / "observation.json", {"status": "complete"})
                source.write_text("changed while capture was running", encoding="utf-8")
                return {}, {"passed": True}
            with mock.patch.object(client, "SOURCES", (source,)), mock.patch.object(client, "environment", return_value={}), \
                 mock.patch.object(client, "prepared_descriptor", return_value={}), mock.patch.object(client, "verify_descriptor"), \
                 mock.patch.object(client, "collect_trial", side_effect=collect), mock.patch.object(client.packaged, "launch") as launch:
                with self.assertRaisesRegex(ValueError, "Frozen file changed"):
                    client.qualify(args)
                launch.assert_not_called()
            self.assertEqual(client.read(args.output / "attempt.json")["status"], "failed")
            self.assertTrue((args.output / "trial/observation.json").exists())
            self.assertFalse((args.output / "trial/qualification.json").exists())


class RawReplayTests(unittest.TestCase):
    def test_unfinished_or_transplanted_raw_diagnostic_jsonl_cannot_reuse_saved_review(self):
        for mutation in ("partial", "extra", "other-process"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "qualification"
                raw = write_raw_qualification_fixture(root)
                path = root / "native-invalid-model.jsonl"
                if mutation == "partial":
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write('{"phase":')
                else:
                    events = copy.deepcopy(raw["diagnostic_events"])
                    if mutation == "extra":
                        events.append(copy.deepcopy(events[-1]))
                    else:
                        events[1]["pid"] += 1
                    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
                with self.assertRaises(ValueError):
                    client.audit_observation(root, policy(), scenario(), "plain")

    def test_missing_final_native_snapshot_keeps_raw_native_errors_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "qualification"
            raw = write_raw_qualification_fixture(root)
            (root / "native-observer-final.json").unlink()
            metadata = client.read(root / "prepared-plan.json")["controls"]["observer"]["target"]
            review = client.read(root / "diagnostic-review.json")
            result = client.assess_native_diagnostics(root, raw, metadata, review)
            self.assertFalse(result["native_attribution"]["passed"])
            self.assertEqual(len(result["unreviewed_native"]), 1)
            self.assertIn("Invalid model", result["unreviewed_native"][0]["text"])
            with self.assertRaisesRegex(ValueError, "assessment differs"):
                client.audit_observation(root, policy(), scenario(), "plain")

    def test_complete_qualification_copied_as_trial_is_rejected_by_actual_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            qualification = Path(temporary) / "qualification"
            write_raw_qualification_fixture(qualification)
            _, original = client.audit_observation(qualification, policy(), scenario(), "plain")
            self.assertTrue(original["passed"], original["errors"])
            trial = Path(temporary) / "001-aa-plain-a"
            shutil.copytree(qualification, trial)
            with self.assertRaisesRegex(ValueError, "another actual instance/capture root"):
                client.audit_observation(trial, policy(), scenario(), "plain")

    def test_qualifier_scope_and_original_created_time_cannot_be_summary_edited(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "qualification"
            raw = write_raw_qualification_fixture(root)
            spec = analysis.schedule(policy())[0]
            with self.assertRaisesRegex(ValueError, "scope or scheduled identity"):
                client.audit_observation(root, policy(), scenario(), "plain", expected_trial=spec)
            raw["run_start"]["started_at"] = "2026-11-15T01:00:00+00:00"
            raw["started_at"] = raw["run_start"]["started_at"]
            client.save(root / "run-start.json", raw["run_start"])
            raw["run_start_sha256"] = client.digest(root / "run-start.json")
            raw["run_finish"]["start_sha256"] = raw["run_start_sha256"]
            client.save(root / "run-finish.json", raw["run_finish"])
            client.save(root / "observation.json", raw)
            with self.assertRaisesRegex(ValueError, "outside its raw execution window"):
                client.audit_observation(root, policy(), scenario(), "plain")

    def test_raw_integrity_failure_revokes_instrumented_acceptance_flag(self):
        plan, state = IndependentDecisionTests().state()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "plan.json"
            client.save(path, plan)
            state["plan_sha256"] = client.digest(path)
            client.save(root / "execution.json", state)
            client.save(root / "execution-start.json", {"schema": 1, "scope": client.SCOPE, "root": str(root),
                "plan_sha256": state["plan_sha256"], "started_at": state["started_at"]})
            with mock.patch.object(client, "verify_plan"):
                report = client.audit(path)
            self.assertEqual(report["status"], "invalid")
            self.assertFalse(report["instrumented_performance_accepted"])
            self.assertEqual(report["instrumented_comparison_status"], "invalid")


class OwnedProcessLifecycleTests(unittest.TestCase):
    """Mock handles and clock only; no child process is actually launched."""
    def setUp(self):
        from log_stream_test_support import fixture_stream
        factory = mock.patch.object(client.native_log_stream.NativeLogStream, "from_launch", side_effect=fixture_stream)
        factory.start()
        self.addCleanup(factory.stop)

    def collect(self, root, *, exporter_error=False, interrupt=False):
        config, scene = policy(), scenario()
        clock = {"seconds": 0}
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
        diagnostic = diagnostic_fixture({"pid": 111, "created": base.isoformat()})
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
            (destination / "logs/latest.log").write_text("[synthetic timestamp] [main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, " + str(destination) + "]\n" + diagnostic["log"], encoding="utf-8")
            (destination / "game-probe/native-resource-epochs.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in evidence(pid=111)["epochs"]), encoding="utf-8")
            (destination / "game-probe/native-invalid-model.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in diagnostic["events"]), encoding="utf-8")
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
                      "probe_metadata": diagnostic["metadata"], "diagnostic_review": client.fingerprint(client.DIAGNOSTIC_REVIEW)}
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
            client.read.side_effect = lambda path: {"pid": 111, "command": ["java.exe"], "timestamp": base.isoformat()} if Path(path).name == "packaged-client-launch.json" else original_read(path)
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

    def test_sealed_binary_replacement_cannot_reuse_old_parsed_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self.run_export(root)
            with mock.patch.object(client, "parse_jfr_recording", return_value=expected) as parser:
                self.assertEqual(client.audit_jfr(root, {"java": str(root / "java.exe")}), expected)
                parser.assert_called_once()
            (root / "recording.jfr").write_bytes(b"replacement sealed after the old parse")
            with mock.patch.object(client, "parse_jfr_recording") as parser:
                with self.assertRaisesRegex(ValueError, "differs from the actual verified export"):
                    client.audit_jfr(root, {"java": str(root / "java.exe")})
                parser.assert_not_called()

    def test_resealed_copies_and_edited_parse_digests_still_require_raw_reparse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.run_export(root)
            attempt = root / "jfr-export-attempt-01"
            for path in (root / "recording.jfr", attempt / "recording.jfr"):
                path.write_bytes(b"corrupt replacement with old saved JSON")
            replacement_sha = client.digest(root / "recording.jfr")
            receipt = client.read(attempt / "receipt.json")
            receipt["recording_sha256"] = replacement_sha
            client.save(attempt / "receipt.json", receipt)
            for label in ("jfr-summary", "jfr-print"):
                execution = client.read(attempt / (label + ".execution.json"))
                execution.update(input_jfr_sha256=replacement_sha, input_jfr_sha256_after=replacement_sha)
                client.save(attempt / (label + ".execution.json"), execution)
            with mock.patch.object(client, "parse_jfr_recording", side_effect=ValueError("Sealed raw JFR failed independent parsing")) as parser:
                with self.assertRaisesRegex(ValueError, "failed independent parsing"):
                    client.audit_jfr(root, {"java": str(root / "java.exe")})
                parser.assert_called_once()

    def test_independent_binary_parser_rejects_failed_or_changed_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = root / "recording.jfr"
            recording.write_bytes(b"fixture")
            with mock.patch.object(client.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="")):
                with self.assertRaisesRegex(ValueError, "failed independent parsing"):
                    client.parse_jfr_recording(recording, str(root / "java.exe"))
            def changed(command, **kwargs):
                if command[1] == "summary":
                    return SimpleNamespace(returncode=0, stdout="Start: 2026-11-15 00:00:00 (UTC)\nDuration: 12 s\n")
                recording.write_bytes(b"changed during parse")
                return SimpleNamespace(returncode=0, stdout=json.dumps({"recording": {"events": []}}))
            with mock.patch.object(client.subprocess, "run", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "changed during independent parsing"):
                    client.parse_jfr_recording(recording, str(root / "java.exe"))


if __name__ == "__main__":
    unittest.main()
