import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import spark_client_sampler as sampler
import spark_operator as operator


def make_spark_data(*, version="0.4.8", instance_fragment=".cache\\acceptance\\official-nf248-spark048-candidate-profile", include_mtr_parse=True):
    threads = [
        {
            "name": "Render thread",
            "childrenRefs": [0],
            "times": [10.0, 20.0],
            "children": [{"className": "org.mtr.Render", "methodName": "draw", "childrenRefs": [], "times": [10.0, 20.0]}],
        },
        {
            "name": "Server thread",
            "childrenRefs": [0],
            "times": [5.0, 10.0],
            "children": [{"className": "net.minecraft.Server", "methodName": "tick", "childrenRefs": [], "times": [5.0, 10.0]}],
        },
    ]
    if include_mtr_parse:
        threads.append({
            "name": "MTR-memory-parse",
            "childrenRefs": [0],
            "times": [3.0, 1.0],
            "children": [{"className": "site.benli06.Loader", "methodName": "parse", "childrenRefs": [], "times": [3.0, 1.0]}],
        })
    return {
        "metadata": {
            "samplerEngine": {"name": "JAVA", "number": 0},
            "samplerMode": {"name": "EXECUTION", "number": 0},
            "interval": 100000,
            "sources": {
                "spark": {"version": "1.10.124"},
                "mtr_memory_sharing": {"version": version},
            },
            "platformMetadata": {
                "type": {"name": "CLIENT", "number": 1},
                "minecraftVersion": "1.21.1",
                "version": "21.1.248",
            },
            "threadDumper": {"type": {"name": "ALL", "number": 0}},
            "startTime": 1794978340000,
            "endTime": 1794978642000,
            "systemStatistics": {
                "uptime": 402000,
                "java": {
                    "vmArgs": f"-Xms512M -Xmx3072M -Djava.library.path=C:\\Users\\<redacted>\\repo\\{instance_fragment}\\versions\\natives"
                },
            },
        },
        "timeWindows": [1, 2],
        "timeWindowStatistics": {"1": {"players": -1}, "2": {"players": -1}},
        "classSources": {},
        "threads": threads,
    }


def make_evidence():
    return {
        "process": {"pid": 1234, "created": "2026-11-18T05:04:00+00:00"},
        "windows": {
            "warmup": {"start": "2026-11-18T05:05:45+00:00", "end": "2026-11-18T05:06:45+00:00"},
            "steady": {"start": "2026-11-18T05:06:45+00:00", "end": "2026-11-18T05:09:45+00:00"},
        },
    }


class SparkClientSamplerTest(unittest.TestCase):
    def setUp(self):
        self.spec = sampler.read(sampler.CATALOG)["samplers"][0]
        self.spec["filename"] = "spark-1.10.124-neoforge.jar"

    def test_spec_for_plan_requires_exact_hash_and_background_flag(self):
        plan = {
            "mods": [{"role": "measurement", "sha256": self.spec["jar_sha256"], "filename": self.spec["filename"]}],
            "extra_jvm_arguments": ["-XX:+UseG1GC", "-Dspark.backgroundProfiler=false"],
        }
        self.assertEqual(sampler.spec_for_plan(plan)["id"], "spark-client-1.10.124")
        bad_args = copy.deepcopy(plan)
        bad_args["extra_jvm_arguments"] = ["-XX:+UseG1GC"]
        with self.assertRaisesRegex(ValueError, "frozen before launch"):
            sampler.spec_for_plan(bad_args)
        bad_hash = copy.deepcopy(plan)
        bad_hash["mods"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "declared sampler protocol"):
            sampler.spec_for_plan(bad_hash)

    def test_request_and_continuation_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sampler.request(root, self.spec, {"pid": 10}, root / "instance", "2026-11-18T05:05:40+00:00")
            self.assertFalse(sampler.continued(root))
            req_sha = hashlib.sha256((root / "sampler-request.json").read_bytes()).hexdigest()
            (root / "sampler-continue.json").write_text(json.dumps({
                "schema": 1, "request_sha256": req_sha, "observed_at": "2026-11-18T05:05:39+00:00"
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "predates"):
                sampler.continued(root)
            (root / "sampler-continue.json").write_text(json.dumps({
                "schema": 1, "request_sha256": req_sha, "observed_at": "2026-11-18T05:05:42+00:00"
            }), encoding="utf-8")
            self.assertTrue(sampler.continued(root))

    def test_validate_handles_redacted_vmargs_and_optional_mtr_thread(self):
        instance = sampler.ROOT / ".cache/acceptance/official-nf248-spark048-candidate-profile"
        prepared = {"instance": str(instance), "artifact": {"version": "0.4.8", "neoForge": "21.1.248"}}
        result = sampler.validate(make_spark_data(include_mtr_parse=True), self.spec, prepared, make_evidence())
        self.assertTrue(result["verified"])
        self.assertIn("MTR-memory-parse", result["optional_thread_reports"])

        # Baseline 0.3.0 may not create MTR-memory-parse; outside-ROOT instance name fallback still checks vmArgs.
        with tempfile.TemporaryDirectory() as tmp:
            ext_inst = Path(tmp) / "official-nf248-spark048-baseline-profile"
            ext_inst.mkdir()
            data030 = make_spark_data(version="0.3.0", instance_fragment=ext_inst.name, include_mtr_parse=False)
            prep030 = {"instance": str(ext_inst), "artifact": {"version": "0.3.0", "neoForge": "21.1.248"}}
            res030 = sampler.validate(data030, self.spec, prep030, make_evidence())
            self.assertEqual(res030["optional_thread_reports"], {})

    def test_validate_rejects_unclosed_window_or_wrong_instance(self):
        prepared = {"instance": str(sampler.ROOT / ".cache/acceptance/other-instance"), "artifact": {"version": "0.4.8", "neoForge": "21.1.248"}}
        with self.assertRaisesRegex(ValueError, "another isolated instance"):
            sampler.validate(make_spark_data(), self.spec, prepared, make_evidence())

        prepared["instance"] = str(sampler.ROOT / ".cache/acceptance/official-nf248-spark048-candidate-profile")
        ev = make_evidence()
        ev["windows"]["steady"]["end"] = "2026-11-18T05:11:30+00:00"
        with self.assertRaisesRegex(ValueError, "enclose"):
            sampler.validate(make_spark_data(), self.spec, prepared, ev)

    def test_verify_idle_rejects_profile_file_or_started_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp)
            (inst / "logs").mkdir()
            (inst / "logs/latest.log").write_text("[INFO] Normal startup\n", encoding="utf-8")
            self.assertTrue(sampler.verify_idle(inst, self.spec)["verified_idle"])

            (inst / "logs/latest.log").write_text("[CHAT] [⚡] Starting a new profiler, please wait...\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "idle control"):
                sampler.verify_idle(inst, self.spec)

            (inst / "logs/latest.log").write_text("[INFO] Normal startup\n", encoding="utf-8")
            (inst / "config/spark").mkdir(parents=True)
            (inst / "config/spark/accident.sparkprofile").write_bytes(b"123")
            with self.assertRaisesRegex(ValueError, "Unexpected Spark profile"):
                sampler.verify_idle(inst, self.spec)

    def test_audit_detects_tampered_profile_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spark_dir = root / "spark"
            spark_dir.mkdir()
            prof = spark_dir / "recording.sparkprofile"
            prof.write_bytes(b"original-spark-bytes")
            (spark_dir / "assessment.json").write_text(json.dumps({
                "verified": True,
                "profile": {"path": str(prof), "sha256": hashlib.sha256(b"original-spark-bytes").hexdigest(), "bytes": 20},
            }), encoding="utf-8")
            prof.write_bytes(b"tampered-spark-bytes")
            with self.assertRaisesRegex(ValueError, "raw binary changed"):
                sampler.audit(root, {"instance": str(root / "instance"), "java": "java.exe"}, {}, self.spec)


class FakeBackend:
    def __init__(self, instance, pid, *, alive=True, lose_focus_once=False, pre_started=False):
        self.instance = Path(instance)
        self.pid = pid
        self.alive = alive
        self.lose_focus_once = lose_focus_once
        self.pre_started = pre_started
        self.focus_calls = 0
        self.typed = []
        self.keys = []
        self.foreground = True
        self._write_snap(None)

    def _write_snap(self, screen):
        probe = self.instance / "game-probe"
        probe.mkdir(parents=True, exist_ok=True)
        snap = {
            "pid": self.pid, "in_world": True, "paused": False, "screen": screen,
            "observed_at": operator.now(),
        }
        (probe / "native-observer.json").write_text(json.dumps(snap), encoding="utf-8")

    def verify_process(self, expected):
        if not self.alive or expected["pid"] != self.pid:
            raise RuntimeError("Target JVM exited.")
        return expected

    def find_window(self, pid):
        return 999

    def apply_us_layout(self, hwnd):
        pass

    def focus_window(self, hwnd):
        self.focus_calls += 1
        if self.lose_focus_once and self.focus_calls == 1:
            self.foreground = False
            raise RuntimeError("Focus stolen during first attempt")
        self.foreground = True

    def is_foreground(self, hwnd):
        return self.foreground

    def press_key(self, name, duration=0.06):
        self.keys.append(name)
        if name == "T":
            self._write_snap("net.minecraft.client.gui.screens.ChatScreen")
        elif name == "ESC":
            self._write_snap(None)
        elif name == "ENTER":
            self._write_snap(None)
            logs = self.instance / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "latest.log").write_text(
                "[CHAT] Starting a new profiler, please wait...\n[CHAT] Profiler is now running! (built-in java)\n",
                encoding="utf-8",
            )

    def type_text(self, value, hwnd=None):
        self.typed.append(value)


class SparkOperatorTest(unittest.TestCase):
    def setUp(self):
        self.spec = sampler.read(sampler.CATALOG)["samplers"][0]
        self.spec["filename"] = "spark-1.10.124-neoforge.jar"

    def test_operator_dispatches_command_and_recovers_from_focus_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = root / "instance"
            (inst / "logs").mkdir(parents=True)
            (inst / "logs/latest.log").write_text("[INFO] Ready\n", encoding="utf-8")
            sampler.request(root, self.spec, {"pid": 42, "created": operator.now()}, inst, operator.now())
            backend = FakeBackend(inst, 42, lose_focus_once=True)
            self.assertTrue(operator.handle_request(root / "sampler-request.json", backend=backend, sleep_fn=lambda _: None))
            self.assertEqual(len(backend.typed), 1)
            self.assertEqual(backend.typed[0], sampler.command(self.spec))
            self.assertTrue(sampler.continued(root))
            receipt = json.loads((root / "sampler-operator-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(len(receipt["attempts"]), 2)
            self.assertEqual(receipt["attempts"][0]["status"], "retry")
            self.assertEqual(receipt["attempts"][1]["status"], "confirmed")

    def test_operator_idempotent_recovery_never_retypes_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = root / "instance"
            (inst / "logs").mkdir(parents=True)
            (inst / "logs/latest.log").write_text(
                "[CHAT] Starting a new profiler, please wait...\n[CHAT] Profiler is now running!\n",
                encoding="utf-8",
            )
            sampler.request(root, self.spec, {"pid": 42, "created": operator.now()}, inst, operator.now())
            backend = FakeBackend(inst, 42)
            self.assertTrue(operator.handle_request(root / "sampler-request.json", backend=backend, sleep_fn=lambda _: None))
            self.assertEqual(backend.typed, [])
            self.assertTrue(sampler.continued(root))
            receipt = json.loads((root / "sampler-operator-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["attempts"][0]["status"], "recovered_from_log")

    def test_operator_fails_closed_when_target_process_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = root / "instance"
            sampler.request(root, self.spec, {"pid": 42, "created": operator.now()}, inst, operator.now())
            backend = FakeBackend(inst, 42, alive=False)
            self.assertFalse(operator.handle_request(root / "sampler-request.json", backend=backend, sleep_fn=lambda _: None))
            self.assertFalse((root / "sampler-continue.json").exists())
            self.assertTrue((root / "sampler-operator-failed.json").is_file())
            self.assertEqual(backend.typed, [])


if __name__ == "__main__":
    unittest.main()
