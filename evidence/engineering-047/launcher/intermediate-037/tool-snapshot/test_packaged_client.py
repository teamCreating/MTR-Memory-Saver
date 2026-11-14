import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
import argparse
import contextlib
import io
from unittest import mock
import packaged_client as client
import legacy_identity


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

    def test_optional_embedded_java_and_variant_must_agree_with_matrix(self):
        self.embedded["java"] = 17
        self.artifact()
        with self.assertRaisesRegex(ValueError, "Java/Minecraft"):
            client.verified_artifact(self.path, self.matrix)
        self.embedded["java"] = self.matrix["java"]
        self.embedded["variant"] = "unrequested"
        self.artifact()
        with self.assertRaisesRegex(ValueError, "variant"):
            client.verified_artifact(self.path, self.matrix)


class LegacyArtifactTest(unittest.TestCase):
    def setUp(self):
        self.matrix = client.read(client.ROOT / "config/targets.json")
        self.catalogue = client.read(client.ROOT / "config/legacy-baselines.json")
        self.paths = {
            "official-030-nf248": client.ROOT / "dist/compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v030-nf248.jar",
            "official-030-nf265": client.ROOT / "dist/releases/mtr-memory-sharing-neoforge-v030.jar",
        }

    def test_original_audited_artifacts_are_accepted_without_any_byte_changes(self):
        for key, path in self.paths.items():
            with self.subTest(key=key):
                before = (client.digest(path), client.digest(path.with_suffix(".build.json")))
                identity = client.verified_artifact(path, self.matrix, key)
                self.assertEqual(identity["target"], self.catalogue["baselines"][key]["target"])
                self.assertEqual(identity["identity_format"], "legacy_manifest")
                self.assertEqual(identity["module_api_capabilities"]["status"], "unsupported")
                self.assertEqual(before, (client.digest(path), client.digest(path.with_suffix(".build.json"))))
                with self.assertRaisesRegex(ValueError, "explicit"):
                    client.verified_artifact(path, self.matrix)

    def test_unlisted_wrong_loader_and_wrong_matrix_are_rejected(self):
        path = self.paths["official-030-nf248"]
        for key in ("unlisted", "official-030-nf265"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                client.verified_artifact(path, self.matrix, key)
        matrix = copy.deepcopy(self.matrix)
        matrix["mtr"]["official"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "target matrix"):
            client.verified_artifact(path, matrix, "official-030-nf248")

    def test_changed_jar_and_original_manifest_are_rejected(self):
        path = self.paths["official-030-nf248"]
        with tempfile.TemporaryDirectory() as temporary:
            clone = pathlib.Path(temporary) / path.name
            clone.write_bytes(path.read_bytes())
            manifest = clone.with_suffix(".build.json")
            manifest.write_bytes(path.with_suffix(".build.json").read_bytes())
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                client.verified_artifact(clone, self.matrix, "official-030-nf248")
            manifest.write_bytes(path.with_suffix(".build.json").read_bytes())
            with zipfile.ZipFile(clone, "a") as archive:
                archive.comment = b"changed"
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                client.verified_artifact(clone, self.matrix, "official-030-nf248")

    def test_metadata_dependency_and_java_contracts_are_interpreted_after_fingerprinting(self):
        original = self.paths["official-030-nf248"]
        changes = {
            "dependency": ("META-INF/neoforge.mods.toml", b'[21.1.248,)', b'[21.1.265,)'),
            "mod identity": ("META-INF/neoforge.mods.toml", b'mtr_memory_sharing', b'wrong_mod_identity'),
            "java": ("mtr-memory-sharing.mixins.json", b'JAVA_21', b'JAVA_17'),
        }
        for name, (entry, old, new) in changes.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                path = pathlib.Path(temporary) / original.name
                with zipfile.ZipFile(original) as source, zipfile.ZipFile(path, "w") as destination:
                    for item in source.infolist():
                        payload = source.read(item.filename)
                        destination.writestr(item, payload.replace(old, new) if item.filename == entry else payload)
                manifest = client.read(original.with_suffix(".build.json"))
                manifest["output_sha256"] = client.digest(path)
                client.write(path.with_suffix(".build.json"), manifest)
                catalogue = copy.deepcopy(self.catalogue)
                catalogue["baselines"]["official-030-nf248"].update(
                    sha256=client.digest(path), manifest_sha256=client.digest(path.with_suffix(".build.json")))
                with self.assertRaises(ValueError):
                    legacy_identity.verify_legacy_identity(path, self.matrix, "official-030-nf248", catalogue)

    def test_legacy_adapter_rejects_modern_metadata_even_with_a_catalogue_entry(self):
        original = self.paths["official-030-nf248"]
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / original.name
            path.write_bytes(original.read_bytes())
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("mtr-memory-target.json", "{}")
            manifest = client.read(original.with_suffix(".build.json"))
            manifest["output_sha256"] = client.digest(path)
            client.write(path.with_suffix(".build.json"), manifest)
            catalogue = copy.deepcopy(self.catalogue)
            catalogue["baselines"]["official-030-nf248"].update(
                sha256=client.digest(path), manifest_sha256=client.digest(path.with_suffix(".build.json")))
            with self.assertRaisesRegex(ValueError, "Modern"):
                legacy_identity.verify_legacy_identity(path, self.matrix, "official-030-nf248", catalogue)


class PerformancePreparationTest(unittest.TestCase):
    """Tiny real filesystem fixtures; Java/launcher/child execution are mocked."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.instance = self.root / "instance"
        self.runtime = self.root / "runtime"
        self.java = self.runtime / "bin/java.exe"
        self.file(self.java, b"java executable")
        self.file(self.runtime / "bin/server/jvm.dll", b"native jvm")
        self.file(self.runtime / "lib/modules", b"modules")
        self.file(self.runtime / "conf/security/java.security", b"security")
        self.file(self.runtime / "release", b'JAVA_VERSION="21.0.11"')
        self.matrix = copy.deepcopy(client.read(client.ROOT / "config/targets.json"))
        self.official_mtr_sha = self.matrix["mtr"]["official"]["sha256"]
        self.mtr = self.source / "mods/official-mtr.jar"
        self.file(self.mtr, b"official mtr fixture")
        self.matrix["mtr"]["official"]["sha256"] = client.digest(self.mtr)
        self.target = self.matrix["default"]
        self.loader = self.matrix["targets"][self.target]["neoForge"]
        self.companion = self.root / "companion.jar"
        identity = {"target": self.target, "version": "0.4.6", "java": self.matrix["java"],
                    "minecraft": self.matrix["minecraft"], "mtrSha256": client.digest(self.mtr), "neoForge": self.loader}
        with zipfile.ZipFile(self.companion, "w") as archive:
            archive.writestr("mtr-memory-target.json", json.dumps(identity))
        client.write(self.companion.with_suffix(".build.json"), {**identity, "artifact": self.companion.name, "sha256": client.digest(self.companion)})
        self.observer = self.root / "observer.jar"
        capabilities = {**dict.fromkeys(("native_pending", "registration_counts", "native_epochs", "heap", "world",
                                        "train_state", "cache_state", "frame_jfr", "server_tick_jfr"), True),
                        **dict.fromkeys(("module_counters", "active_read_permits", "text_workspace"), False)}
        metadata = {**identity, "schema_version": 1, "probe_kind": "official-native-observer", "observer_version": "1.0.0",
                    "mod_id": "mtr_native_observer", "variant": "official", "mtrVersion": self.matrix["mtr"]["official"]["version"],
                    "frame_event": "mtrtest.ClientFrame", "server_tick_event": "mtrtest.ServerTick",
                    "snapshot_path": "game-probe/native-observer.json", "epochs_path": "game-probe/native-resource-epochs.jsonl"}
        with zipfile.ZipFile(self.observer, "w") as archive:
            archive.writestr("mtr-native-observer-target.json", json.dumps(metadata))
            archive.writestr("capabilities.json", json.dumps({"schema_version": 1, "probe_kind": metadata["probe_kind"], "capabilities": capabilities}))
        client.write(self.observer.with_suffix(".build.json"), {**metadata, "artifact": self.observer.name,
                     "sha256": client.digest(self.observer), "capabilities": capabilities})
        for name in client.INPUT_DIRECTORIES:
            self.file(self.source / name / "input.dat", name.encode())
        self.file(self.source / "versions" / ("neoforge-" + self.loader) / ("neoforge-" + self.loader + ".json"), b"{}")
        self.file(self.source / "saves/world/level.dat", b"level")
        self.file(self.source / "saves/world/region/a.dat", b"region")
        self.file(self.source / "options.txt", b'resourcePacks:["vanilla"]\nrenderDistance:8\n')
        client.write(self.source / "vehicle-test-instance.json", {"instance": str(self.source), "loader": self.loader, "java": str(self.java), "pid": None})
        client.write(self.source / "usercache.json", [{"name": "tester", "uuid": "fixture-uuid"}])
        pack = self.root / "pack.zip"
        self.file(pack, b"pack")
        self.catalogue = self.root / "catalogue.json"
        client.write(self.catalogue, {"passed": True, "target": {"mtr": self.matrix["mtr"]["official"]["version"]},
                                    "packs": [{"output": pack.name, "output_sha256": client.digest(pack)}]})
        self.context = self.root / "context.json"
        client.write(self.context, {"schema": 1, "scenario_name": "fixture", "world_name": "world", "camera": {}, "route": {}})
        self.args = argparse.Namespace(source=self.source, instance=self.instance, companion=self.companion, legacy_baseline=None,
            probe=None, observer=[self.observer], catalogue=self.catalogue, world="world", username="tester", heap_mib=3072,
            initial_heap_mib=512, scheduler_parallelism=None, scheduler_max_pool_size=None, jvm_arg=[], jfr=False, nmt=None,
            smoke=False, faults=False, expect_binary_rejection=False, resolution_width=1280, resolution_height=720,
            performance=True, controls=self.context)
        original_read = client.read
        self.patch(mock.patch.object(client, "read", side_effect=lambda path: copy.deepcopy(self.matrix)
                   if pathlib.Path(path) == client.ROOT / "config/targets.json" else original_read(path)))
        self.patch(mock.patch.object(client.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", 'openjdk version "21.0.11"\n')))
        self.patch(mock.patch.object(client, "launcher_implementation", return_value={"distribution": "fixture", "version": "1", "sources": {"command.py": "abc"}}))
        self.real_launch_command = client.launch_command
        self.patch(mock.patch.object(client, "launch_command", side_effect=self.command))
        self.patch(mock.patch.dict(client.os.environ, {name: "" for name in client.JAVA_INJECTION_ENV}))

    def patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def file(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def command(self, instance, plan):
        return [plan["java"], *client.jvm_arguments(plan), "-cp", str(pathlib.Path(instance) / "libraries/input.dat"),
                "FixtureMain", "--gameDir", str(instance)]

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            client.prepare(self.args)
        return client.read(self.instance / "packaged-client-plan.json")

    def test_full_preparation_freezes_complete_closure_and_launch_returns_actual_child(self):
        plan = self.prepare()
        self.assertEqual(plan["schema"], 2)
        self.assertEqual(plan["controls_sha256"], client.controls_sha256(plan))
        self.assertEqual(plan["artifact"]["module_api_capabilities"], {"status": "unassessed"})
        self.assertNotIn("root", client.comparison_controls(plan)["runtime"])
        self.assertIsNone(plan["scheduler_parallelism"])
        child = mock.Mock(pid=123)
        with mock.patch.object(client.subprocess, "Popen", return_value=child) as popen, contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(client.launch(argparse.Namespace(instance=self.instance, wait_seconds=None)), child)
        command = popen.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], str(self.java))
        self.assertNotIn("shell", popen.call_args.kwargs)

    def test_old_plans_cannot_qualify_as_performance_preparation(self):
        plan = self.prepare()
        plan["schema"] = 1
        with self.assertRaisesRegex(ValueError, "schema-2"):
            client.verify_performance_controls(self.instance, plan)

    def test_changed_added_removed_library_and_config_inputs_are_rejected(self):
        plan = self.prepare()
        for directory in client.INPUT_DIRECTORIES:
            file = self.instance / directory / "input.dat"
            original = file.read_bytes()
            for change in ("changed", "added", "removed"):
                with self.subTest(directory=directory, change=change):
                    addition = file.parent / "additional.dat"
                    if change == "changed":
                        file.write_bytes(b"different")
                    elif change == "added":
                        addition.write_bytes(b"extra")
                    else:
                        file.unlink()
                    with self.assertRaises(ValueError):
                        client.verify_performance_controls(self.instance, plan)
                    file.write_bytes(original)
                    addition.unlink(missing_ok=True)

    def test_runtime_modules_native_jvm_and_configuration_mutations_are_rejected(self):
        plan = self.prepare()
        for name in ("release", "lib/modules", "bin/server/jvm.dll", "conf/security/java.security"):
            with self.subTest(name=name):
                path = self.runtime / name
                original = path.read_bytes()
                path.write_bytes(b"different")
                with self.assertRaisesRegex(ValueError, "runtime"):
                    client.verify_performance_controls(self.instance, plan)
                path.write_bytes(original)
        extra = self.runtime / "lib/additional.dat"
        extra.write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "runtime"):
            client.verify_performance_controls(self.instance, plan)

    def test_world_options_pack_and_unlisted_mod_mutations_are_rejected(self):
        plan = self.prepare()
        for name in ("saves/world/region/a.dat", "options.txt", "resourcepacks/pack.zip"):
            with self.subTest(name=name):
                path = self.instance / name
                original = path.read_bytes()
                path.write_bytes(b"different")
                with self.assertRaises(ValueError):
                    client.verify_prepared_inputs(self.instance, plan)
                path.write_bytes(original)
        self.file(self.instance / "mods/extra.jar", b"extra mod")
        with self.assertRaisesRegex(ValueError, "mods"):
            client.verify_prepared_inputs(self.instance, plan)

    def test_environment_and_incomplete_jvm_source_controls_are_rejected(self):
        plan = self.prepare()
        for variable in client.JAVA_INJECTION_ENV:
            with self.subTest(variable=variable), mock.patch.dict(client.os.environ, {variable: "-Xmx8G"}):
                with self.assertRaisesRegex(ValueError, "injection"):
                    client.verify_performance_controls(self.instance, plan)
        incomplete = copy.deepcopy(plan)
        del incomplete["scheduler_parallelism"]
        with self.assertRaisesRegex(ValueError, "explicit JVM"):
            client.verify_performance_controls(self.instance, incomplete)
        incomplete = copy.deepcopy(plan)
        incomplete["controls"]["sources"] = {}
        incomplete["controls_sha256"] = client.controls_sha256(incomplete)
        with self.assertRaisesRegex(ValueError, "source identity"):
            client.verify_performance_controls(self.instance, incomplete)

    def test_same_contents_different_instance_roots_remain_comparable(self):
        plan = self.prepare()
        self.args.instance = self.root / "other-instance"
        with contextlib.redirect_stdout(io.StringIO()):
            client.prepare(self.args)
        other = client.read(self.args.instance / "packaged-client-plan.json")
        self.assertEqual(client.controls_sha256(plan), client.controls_sha256(other))
        self.assertTrue(client.verify_performance_controls(self.args.instance, other))

    def test_treatment_identity_is_excluded_but_other_content_settings_and_order_are_included(self):
        plan = self.prepare()
        changed = copy.deepcopy(plan)
        changed["artifact"].update(version="0.3.0", artifact="old.jar", sha256="0" * 64, identity_format="legacy_manifest")
        changed["controls"]["companion_manifest_sha256"] = "0" * 64
        companion = next(mod for mod in changed["mods"] if mod["role"] == "companion")
        companion.update(filename="old.jar", sha256="0" * 64)
        self.assertEqual(client.controls_sha256(plan), client.controls_sha256(changed))
        changes = (lambda value: value["packs"].append({"filename": "other.zip", "sha256": "0" * 64}),
                   lambda value: value.update(options_sha256="0" * 64),
                   lambda value: value["world"]["files"].update({"extra": "0" * 64}),
                   lambda value: value["controls"]["launcher"]["settings"].update(resolutionWidth="1920"),
                   lambda value: value["controls"]["context"]["declarations"]["camera"].update(x=1),
                   lambda value: next(mod for mod in value["mods"] if mod["role"] == "observer").update(sha256="0" * 64))
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                altered = copy.deepcopy(plan)
                change(altered)
                self.assertNotEqual(client.controls_sha256(plan), client.controls_sha256(altered))
        ordered = copy.deepcopy(plan)
        ordered["packs"].append({"filename": "other.zip", "sha256": "0" * 64})
        reversed_packs = copy.deepcopy(ordered)
        reversed_packs["packs"].reverse()
        self.assertNotEqual(client.controls_sha256(ordered), client.controls_sha256(reversed_packs))

    def test_frozen_workload_bytes_and_launcher_command_cannot_change(self):
        plan = self.prepare()
        context = self.instance / ".prepared-controls/context.json"
        original = context.read_bytes()
        context.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "workload"):
            client.verify_performance_controls(self.instance, plan)
        context.write_bytes(original)
        with mock.patch.object(client, "launch_command", return_value=[str(self.java), "DifferentMain"]):
            with self.assertRaisesRegex(ValueError, "launcher"):
                client.verify_performance_controls(self.instance, plan)

    def test_missing_or_multiple_neutral_probes_fail_before_copying(self):
        for observers in ([], [self.observer, self.observer]):
            with self.subTest(observers=len(observers)):
                self.args.observer = observers
                with self.assertRaisesRegex(ValueError, "independent observer"):
                    client.prepare(self.args)
                self.assertFalse(self.instance.exists())

    def test_absent_configuration_directory_presence_is_frozen(self):
        directory = self.source / "defaultconfigs"
        (directory / "input.dat").unlink()
        directory.rmdir()
        plan = self.prepare()
        self.assertFalse(plan["controls"]["inputs"]["defaultconfigs"]["present"])
        (self.instance / "defaultconfigs").mkdir()
        with self.assertRaisesRegex(ValueError, "defaultconfigs"):
            client.verify_performance_controls(self.instance, plan)

    def test_legacy_product_probe_smoke_fault_and_binary_controls_are_rejected_before_copy(self):
        # The helper must use the actual original official dependency identity.
        self.matrix["mtr"]["official"]["sha256"] = self.official_mtr_sha
        self.args.companion = client.ROOT / "dist/compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v030-nf248.jar"
        self.args.legacy_baseline = "official-030-nf248"
        for field in ("probe", "smoke", "faults", "expect_binary_rejection"):
            with self.subTest(field=field):
                setattr(self.args, field, self.observer if field == "probe" else True)
                with self.assertRaisesRegex(ValueError, "Legacy baselines"):
                    client.prepare(self.args)
                setattr(self.args, field, None if field == "probe" else False)
                self.assertFalse(self.instance.exists())

    def test_nonperformance_preparation_remains_compatible(self):
        self.args.performance = False
        self.args.controls = None
        self.args.observer = []
        plan = self.prepare()
        self.assertEqual(plan["schema"], 1)
        self.assertNotIn("controls", plan)
        self.assertEqual(client.jvm_arguments(plan)[0], "-Xms512M")
        client.verify_prepared_inputs(self.instance, plan)

    def test_historical_plan_fields_and_windows_world_paths_still_launch_normally(self):
        self.args.performance = False
        self.args.controls = None
        self.args.observer = []
        plan = self.prepare()
        for key in ("schema", "scope", "initial_heap_mib", "scheduler_parallelism", "scheduler_max_pool_size",
                    "extra_jvm_arguments", "resolution_width", "resolution_height"):
            del plan[key]
        plan["world"]["files"] = {key.replace("/", "\\"): value for key, value in plan["world"]["files"].items()}
        for mod in plan["mods"]:
            del mod["role"]
        client.write(self.instance / "packaged-client-plan.json", plan)
        child = mock.Mock(pid=123)
        with mock.patch.object(client.subprocess, "Popen", return_value=child), contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(client.launch(argparse.Namespace(instance=self.instance, wait_seconds=None)), child)

    def test_real_public_launcher_command_is_frozen_and_loader_heap_overrides_are_rejected(self):
        loader_path = self.source / "versions" / ("neoforge-" + self.loader) / ("neoforge-" + self.loader + ".json")
        metadata = {"id": "neoforge-" + self.loader, "type": "release", "mainClass": "FixtureMain", "libraries": [],
                    "assets": "fixture", "assetIndex": {"id": "fixture"},
                    "arguments": {"jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"],
                                  "game": ["--username", "${auth_player_name}", "--gameDir", "${game_directory}"]}}
        client.write(loader_path, metadata)
        with mock.patch.object(client, "launch_command", side_effect=self.real_launch_command):
            plan = self.prepare()
            generated = self.real_launch_command(self.instance, plan)
            self.assertIn("FixtureMain", generated)
            self.assertEqual(client.command_template(generated, self.instance, self.java), plan["controls"]["launcher"]["command_template"])
            self.assertTrue(client.verify_performance_controls(self.instance, plan))
        metadata["arguments"]["jvm"].append("-Xmx8G")
        client.write(loader_path, metadata)
        self.args.instance = self.root / "override-instance"
        with mock.patch.object(client, "launch_command", side_effect=self.real_launch_command), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "overrides"):
                client.prepare(self.args)
        self.assertFalse((self.args.instance / "packaged-client-plan.json").exists())

    def test_neutral_observer_rejects_changed_binary_wrong_target_and_fabricated_capability(self):
        plan = self.prepare()
        identity = plan["artifact"]
        original_jar = self.observer.read_bytes()
        original_manifest = self.observer.with_suffix(".build.json").read_bytes()
        for mutation in ("jar", "target", "module capability"):
            with self.subTest(mutation=mutation):
                self.observer.write_bytes(original_jar)
                self.observer.with_suffix(".build.json").write_bytes(original_manifest)
                manifest = client.read(self.observer.with_suffix(".build.json"))
                if mutation == "jar":
                    with zipfile.ZipFile(self.observer, "a") as archive:
                        archive.comment = b"changed"
                else:
                    with zipfile.ZipFile(io.BytesIO(original_jar)) as archive:
                        payloads = {name: archive.read(name) for name in archive.namelist()}
                    if mutation == "target":
                        target = json.loads(payloads["mtr-native-observer-target.json"])
                        target["neoForge"] = "different"
                        payloads["mtr-native-observer-target.json"] = json.dumps(target)
                        manifest["neoForge"] = "different"
                    else:
                        capabilities = json.loads(payloads["capabilities.json"])
                        capabilities["capabilities"]["module_counters"] = True
                        payloads["capabilities.json"] = json.dumps(capabilities)
                        manifest["capabilities"] = capabilities["capabilities"]
                    with zipfile.ZipFile(self.observer, "w") as archive:
                        for name, payload in payloads.items():
                            archive.writestr(name, payload)
                    manifest["sha256"] = client.digest(self.observer)
                    client.write(self.observer.with_suffix(".build.json"), manifest)
                with self.assertRaises(ValueError):
                    client.verified_observer(self.observer, identity, self.matrix)


class ExtraJvmControlsTest(unittest.TestCase):
    def test_control_aliases_response_files_and_launcher_inputs_are_rejected(self):
        for argument in ("-Xms1G", "-Xmx4G", "-XX:MaxHeapSize=4G", "-XX:InitialHeapSize=1G",
                         "-XX:MaxRAMPercentage=90", "-XX:StartFlightRecording=foo", "-XX:FlightRecorderOptions=foo",
                         "-XX:NativeMemoryTracking=detail", "-Dmtr.memory.acceptance=false", "-Xlog:gc",
                         "-Djdk.virtualThreadScheduler.parallelism=2", "-Djdk.virtualThreadScheduler.maxPoolSize=2",
                         "-Djava.util.concurrent.ForkJoinPool.common.parallelism=2", "-cp", "--class-path=x",
                         "-jar", "main.Class", "@arguments.txt", "--module=x", "-Djava.library.path=elsewhere",
                         "-XX:Flags=other.options", "-XX:VMOptionsFile=other.options", "-Xbootclasspath/a:external.jar",
                         "--patch-module=java.base=external.jar"):
            with self.subTest(argument=argument), self.assertRaisesRegex(ValueError, "overrides"):
                client.extra_jvm_arguments([argument])

    def test_scheduler_and_extra_arguments_remain_individual_list_entries(self):
        plan = {"heap_mib": 3072, "initial_heap_mib": 1024, "smoke": False, "jfr": False,
                "scheduler_parallelism": 2, "scheduler_max_pool_size": 2,
                "extra_jvm_arguments": ["-XX:-CompactStrings", "-Dfixture.message=value with spaces"]}
        arguments = client.jvm_arguments(plan)
        self.assertIn("-Xms1024M", arguments)
        self.assertIn("-Djdk.virtualThreadScheduler.parallelism=2", arguments)
        self.assertIn("-Djdk.virtualThreadScheduler.maxPoolSize=2", arguments)
        self.assertEqual(arguments[-2:], plan["extra_jvm_arguments"])

    def test_complete_generated_command_rejects_late_control_overrides_and_response_files(self):
        plan = {"java": "java.exe", "heap_mib": 3072, "smoke": False, "jfr": False}
        command = ["java.exe", *client.jvm_arguments(plan), "-cp", "frozen-libraries", "FixtureMain"]
        self.assertEqual(client.verify_generated_command(command, plan), command)
        for argument in ("-Xmx8G", "-Djdk.virtualThreadScheduler.maxPoolSize=8", "@args.txt"):
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                client.verify_generated_command(command + [argument], plan)


if __name__ == "__main__":
    unittest.main()
