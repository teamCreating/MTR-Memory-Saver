import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import client_experiment as exp
import client_experiment_analysis as analysis
import practical_client_verification as pcv
from tests.test_client_experiment import evidence, policy, scenario


class TurnaroundRouteAndHardlinkCloneTests(unittest.TestCase):
    def test_turnaround_route_zero_allowed_after_target_route_with_displacement(self):
        record = evidence()
        # Samples 0..5 on target route 10 with advancing progress; samples 6..9 enter turnaround route 0.
        for index in range(6, 10):
            record["samples"][index]["native"]["train_state"]["vehicles"][0]["route_id"] = 0
        result = analysis.assess_observation(record, policy(), scenario(), "plain")
        self.assertTrue(result["passed"], result["errors"])

    def test_route_zero_across_entire_steady_window_still_fails(self):
        record = evidence()
        for sample in record["samples"]:
            sample["native"]["train_state"]["vehicles"][0]["route_id"] = 0
        result = analysis.assess_observation(record, policy(), scenario(), "plain")
        self.assertFalse(result["passed"])
        self.assertTrue(any("displacement" in err for err in result["errors"]))

    def test_unrelated_nonzero_route_still_fails(self):
        record = evidence()
        record["samples"][7]["native"]["train_state"]["vehicles"][0]["route_id"] = 11
        result = analysis.assess_observation(record, policy(), scenario(), "plain")
        self.assertFalse(result["passed"])

    def test_clone_prepared_hardlinks_readonly_dirs_and_isolates_mutable_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template"
            dest = root / "cloned"
            for folder, filename, body in (
                ("assets", "lang.json", b"{}"),
                ("mods", "mod.jar", b"jar-bytes"),
                ("saves/world", "level.dat", b"world-v1"),
                ("config", "fml.toml", b"fml=1"),
            ):
                target = template / folder / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            (template / "options.txt").write_text("maxFps:60\n", encoding="utf-8")
            (template / "packaged-client-plan.json").write_text(json.dumps({"instance": str(template)}), encoding="utf-8")
            (template / "vehicle-test-instance.json").write_text(json.dumps({"instance": str(template), "pid": None}), encoding="utf-8")

            with mock.patch.object(exp.packaged, "verify_prepared_inputs"), mock.patch.object(exp.packaged, "verify_performance_controls"):
                plan = exp.clone_prepared({"instance": str(template)}, dest)

            self.assertEqual(Path(plan["instance"]), dest.resolve())
            self.assertEqual(os.stat(template / "assets/lang.json").st_ino, os.stat(dest / "assets/lang.json").st_ino)
            self.assertEqual(os.stat(template / "mods/mod.jar").st_ino, os.stat(dest / "mods/mod.jar").st_ino)
            self.assertNotEqual(os.stat(template / "saves/world/level.dat").st_ino, os.stat(dest / "saves/world/level.dat").st_ino)
            (dest / "saves/world/level.dat").write_bytes(b"world-v2")
            self.assertEqual((template / "saves/world/level.dat").read_bytes(), b"world-v1")


class PracticalVerificationTests(unittest.TestCase):
    def test_trial_inventory_excludes_its_receipt_and_rejects_changed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "samples.jsonl"
            sample.write_bytes(b"sample")
            nested = root / "native-log"
            nested.mkdir()
            (nested / "trial-summary.json").write_bytes(b"nested evidence")
            files = pcv.trial_raw_files(root)
            (root / "trial-summary.json").write_text(json.dumps({"files": files}), encoding="utf-8")
            self.assertEqual(len(files), 2)
            exp.verify_raw_files(root, files, excluded_root_files=pcv.TRIAL_INVENTORY_EXCLUSIONS)
            sample.write_bytes(b"edited")
            with self.assertRaisesRegex(ValueError, "Raw evidence changed"):
                exp.verify_raw_files(root, files, excluded_root_files=pcv.TRIAL_INVENTORY_EXCLUSIONS)

    def _probe_off_fixture(self, root, *, extra_error=None):
        created = dt.datetime(2026, 11, 18, 6, 0, 0, tzinfo=dt.timezone.utc)
        stamp = lambda s: (created + dt.timedelta(seconds=s)).isoformat()
        log_lines = [
            f"[14:00:01] [main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, {root / 'instance'}]",
            "[14:01:00] [Render thread/ERROR] [MinecraftTransitRailway/]: [mtr:textures/block/transparent.png] Invalid model!",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: Loaded 1092 vehicles and completed door movement validation in 0.0 ms",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: Loaded 142 signs",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: Loaded 23 rails",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: Loaded 290 objects",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: Loaded 1 lifts",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: MTR memory sharing: 3375 requests, 2724 path hits, 651 unique parses, 0 failures, 0 pending, 0 outstanding, 0 queued",
            "[14:02:00] [Render thread/INFO] [MinecraftTransitRailway/]: MTR streamed OBJ: 1128 requests, 154 path hits, 974 parses, 0 failures, 0 pending, 0 outstanding, 0 queued",
        ]
        if extra_error:
            log_lines.append(extra_error)
        raw_log = ("\n".join(log_lines) + "\n").encode("utf-8")
        samples = []
        for s in (10, 120, 122, 270, 420, 422, 510, 600):
            samples.append({
                "observed_at": stamp(s),
                "os": {"running": True, "private_usage": 2000, "working_set": 2200, "peak_working_set_since_process_start": 3000},
                "errors": [],
                "client_log_witness": {"bytes": len(raw_log), "sha256": hashlib.sha256(raw_log).hexdigest()},
            })
        run_start = {"schema": 1, "scope": pcv.PROBE_OFF_SCOPE, "root": str(root), "started_at": stamp(0), "trial_spec": {"id": "06-probe-off-01"}}
        run_start_sha = hashlib.sha256(b"start").hexdigest()
        cleanup = {"exited": True, "exit_code": 0, "pid": 77, "timestamp": stamp(602)}
        ev = {
            "schema": 1, "status": "complete", "scope": pcv.PROBE_OFF_SCOPE, "capture_root": str(root),
            "started_at": stamp(0), "finished_at": stamp(605), "measurement_completed_at": stamp(600),
            "measurement_process_running": True, "run_start": run_start, "run_start_sha256": run_start_sha,
            "run_finish": {"schema": 1, "scope": pcv.PROBE_OFF_SCOPE, "root": str(root), "finished_at": stamp(605),
                           "start_sha256": run_start_sha, "process": {"pid": 77, "created": stamp(1)},
                           "measurement_completed_at": stamp(600), "cleanup": cleanup},
            "process": {"pid": 77, "created": stamp(1), "captured_at": stamp(3)},
            "launch": {"timestamp": stamp(2)},
            "windows": {
                "startup": {"start": stamp(1), "end": stamp(120)},
                "warmup": {"start": stamp(120), "end": stamp(420)},
                "steady": {"start": stamp(420), "end": stamp(600)},
            },
            "samples": samples,
            "cleanup": cleanup,
            "client_diagnostics": analysis.native_diagnostics(raw_log.decode("utf-8")),
            "client_log_completeness": analysis.client_log_completeness(raw_log, samples, root / "instance"),
        }
        return ev, raw_log.decode("utf-8")

    def test_policy_loads_twelve_trials(self):
        cfg = pcv.load_policy()
        self.assertEqual(len(cfg["schedule"]), 12)
        self.assertEqual(sum(1 for item in cfg["schedule"] if item["mode"] == "plain"), 6)
        self.assertEqual(sum(1 for item in cfg["schedule"] if item["mode"] == "profile" and item["spark"]), 4)
        self.assertEqual(sum(1 for item in cfg["schedule"] if item["mode"] == "probe_off"), 2)

    def test_probe_off_assessment_accepts_clean_log_and_rejects_oom_or_unsettled(self):
        policy_cfg = copy.deepcopy(pcv.load_policy())
        policy_cfg["maximum_sample_gap_seconds"] = 200
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ev, text = self._probe_off_fixture(root)
            res = pcv.assess_probe_off_observation(ev, policy_cfg, text)
            self.assertTrue(res["passed"], res["errors"])
            self.assertEqual(res["metrics"]["steady_private_bytes"], 2000)
            self.assertIn("steady_heap_bytes", res["unavailable_metrics"])

            ev_oom, text_oom = self._probe_off_fixture(root, extra_error="[14:03:00] [Render thread/ERROR]: java.lang.OutOfMemoryError: Java heap space")
            res_oom = pcv.assess_probe_off_observation(ev_oom, policy_cfg, text_oom)
            self.assertFalse(res_oom["passed"])

    def test_compare_arms_computes_paired_deltas(self):
        summary = pcv.compare_arms(
            [({"steady_private_bytes": 4000, "loading_ms": 200000}, {"steady_private_bytes": 3200, "loading_ms": 180000}),
             ({"steady_private_bytes": 4200, "loading_ms": 210000}, {"steady_private_bytes": 3360, "loading_ms": 189000})],
            ("steady_private_bytes", "loading_ms"),
        )
        self.assertAlmostEqual(summary["steady_private_bytes"]["median_percent_delta"], -20.0)
        self.assertAlmostEqual(summary["loading_ms"]["median_percent_delta"], -10.0)


if __name__ == "__main__":
    unittest.main()
