import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
import packaged_client as client


class ProcessExitObservationTest(unittest.TestCase):
    def test_retains_real_zero_and_nonzero_exits(self):
        for code in (0, 7):
            with self.subTest(code=code):
                process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(" + str(code) + ")"])
                result = client.observe_exit(process, 10)
                self.assertTrue(result["exited"])
                self.assertEqual(result["exit_code"], code)
                self.assertEqual(result["pid"], process.pid)

    def test_timeout_leaves_the_actual_child_running(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
        try:
            result = client.observe_exit(process, 0.01)
            self.assertFalse(result["exited"])
            self.assertIsNone(result["exit_code"])
            self.assertIsNone(process.poll())
            self.assertEqual(process.wait(timeout=10), 0)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


class InstrumentationConfigurationTest(unittest.TestCase):
    def test_jfr_retains_full_history_without_size_or_age_trimming(self):
        plan = {"heap_mib": 3072, "smoke": False, "jfr": True, "jfr_max_size_bytes": 0}
        arguments = client.jvm_arguments(plan)
        recording = next(item.removeprefix("-XX:StartFlightRecording=") for item in arguments
                         if item.startswith("-XX:StartFlightRecording="))
        options = dict(item.split("=", 1) for item in recording.split(","))
        self.assertEqual(options["maxsize"], "0")
        self.assertNotIn("maxage", options)
        self.assertEqual(options["settings"], "profile")
        self.assertEqual(options["disk"], "true")
        self.assertEqual(options["dumponexit"], "true")
        self.assertEqual(options["filename"], "acceptance.jfr")

    def test_old_or_bounded_jfr_plans_cannot_inherit_full_history_retention(self):
        plan = {"heap_mib": 3072, "smoke": False, "jfr": True}
        with self.assertRaisesRegex(ValueError, "retention"):
            client.jvm_arguments(plan)
        for maximum in (None, False, 250 * 1024 * 1024):
            with self.subTest(maximum=maximum):
                plan["jfr_max_size_bytes"] = maximum
                with self.assertRaisesRegex(ValueError, "retention"):
                    client.jvm_arguments(plan)

    def test_uninstrumented_control_has_no_flight_recording_argument(self):
        plan = {"heap_mib": 3072, "smoke": False, "jfr": False, "jfr_max_size_bytes": None}
        self.assertFalse(any(item.startswith("-XX:StartFlightRecording=") for item in client.jvm_arguments(plan)))

    def test_native_tracking_requires_a_frozen_explicit_mode(self):
        plan = {"heap_mib": 3072, "smoke": False, "jfr": False}
        self.assertFalse(any("NativeMemoryTracking" in item for item in client.jvm_arguments(plan)))
        for mode in ("summary", "detail"):
            with self.subTest(mode=mode):
                plan["native_memory_tracking"] = mode
                self.assertIn("-XX:NativeMemoryTracking=" + mode, client.jvm_arguments(plan))
        plan["native_memory_tracking"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "tracking mode"):
            client.jvm_arguments(plan)


class PackagedArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = pathlib.Path(self.temporary.name) / "candidate.jar"
        self.matrix = client.read(client.ROOT / "config/targets.json")
        target = self.matrix["default"]
        self.identity = {"target": target, "version": "0.4.3", "java": self.matrix["java"],
                         "mtrSha256": self.matrix["mtr"]["official"]["sha256"],
                         "neoForge": self.matrix["targets"][target]["neoForge"]}
        self.embedded = {**self.identity, "minecraft": self.matrix["minecraft"]}

    def artifact(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("mtr-memory-target.json", json.dumps(self.embedded))
        identity = {**self.identity, "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()}
        client.write(self.path.with_suffix(".build.json"), identity)
        return identity

    def test_accepts_consistent_packaged_identity(self):
        identity = self.artifact()
        self.assertEqual(client.verified_artifact(self.path, self.matrix), identity)

    def test_rejects_changed_jar_bytes(self):
        self.artifact()
        with zipfile.ZipFile(self.path, "a") as archive:
            archive.comment = b"changed bytes with identical metadata"
        with self.assertRaisesRegex(ValueError, "fingerprinted"):
            client.verified_artifact(self.path, self.matrix)

    def test_rejects_embedded_manifest_disagreement(self):
        self.embedded["version"] = "0.4.2"
        self.artifact()
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            client.verified_artifact(self.path, self.matrix)

    def test_rejects_self_consistent_wrong_mtr_identity(self):
        self.identity["mtrSha256"] = "0" * 64
        self.embedded["mtrSha256"] = "0" * 64
        self.artifact()
        with self.assertRaisesRegex(ValueError, "audited target matrix"):
            client.verified_artifact(self.path, self.matrix)

    def test_rejects_wrong_minecraft_or_java_even_with_matching_hash(self):
        self.embedded["minecraft"] = "different"
        self.artifact()
        with self.assertRaisesRegex(ValueError, "Java/Minecraft"):
            client.verified_artifact(self.path, self.matrix)
        self.embedded["minecraft"] = self.matrix["minecraft"]
        self.identity["java"] += 1
        self.embedded["java"] = self.identity["java"]
        self.artifact()
        with self.assertRaisesRegex(ValueError, "Java/Minecraft"):
            client.verified_artifact(self.path, self.matrix)

    def test_rejects_unrequested_variant(self):
        self.artifact()
        matrix = copy.deepcopy(self.matrix)
        matrix["targets"][self.identity["target"]]["variant"] = "unrequested"
        with self.assertRaisesRegex(ValueError, "official-target"):
            client.verified_artifact(self.path, matrix)


if __name__ == "__main__":
    unittest.main()
