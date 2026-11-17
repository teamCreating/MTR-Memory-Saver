import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

import ci


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        self.matrix = json.loads((ci.ROOT / "config/targets.json").read_text(encoding="utf-8"))
        (self.root / "config/targets.json").write_text(json.dumps(self.matrix), encoding="utf-8")
        (self.root / "gradle.properties").write_text("modVersion=0.8.1\n", encoding="utf-8")
        self.assets = self.root / "assets"
        self.assets.mkdir()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.STDOUT, text=True).strip()

    def initialize_git(self):
        self.git("init", "-b", "main")
        self.git("config", "user.name", "A-BenLi06")
        self.git("config", "user.email", "ben_li06@outlook.com")
        self.git("add", "gradle.properties", "config/targets.json")
        self.git("commit", "-m", "Fixture main")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def bundle(self, target, *, version="0.8.1", bad_jar=False):
        jar = b"fixture companion bytes"
        identity = {"target": target, "version": version, "java": self.matrix["java"],
                    "neoForge": self.matrix["targets"][target]["neoForge"],
                    "mtrSha256": self.matrix["mtr"]["official"]["sha256"],
                    "artifact": "companion.jar", "sha256": hashlib.sha256(jar).hexdigest()}
        path = self.assets / (target + ".zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("companion.jar", b"changed" if bad_jar else jar)
            archive.writestr("companion.build.json", json.dumps(identity))
        return path

    def test_metadata_uses_current_official_matrix_and_property_version(self):
        matrix, version, targets = ci.configuration(self.root)
        self.assertEqual(version, "0.8.1")
        self.assertEqual(set(targets), {k for k, v in matrix["targets"].items() if v["variant"] == "official"})
        self.assertTrue(all(matrix["targets"][t]["variant"] != "v6" for t in targets))
        (self.root / "gradle.properties").write_text("modVersion=1.0.0\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ci.configuration(self.root)

    def test_tag_and_dispatch_guard_including_real_off_main_commit(self):
        self.initialize_git()
        self.assertEqual(ci.release_ref("push", "refs/tags/v0.8.1", self.root), "v0.8.1")
        self.assertEqual(ci.release_ref("workflow_dispatch", "refs/heads/main", self.root), "v0.8.1")
        for event, ref in [("push", "refs/tags/v0.8.2"), ("push", "refs/heads/main"),
                           ("workflow_dispatch", "refs/heads/topic"), ("pull_request", "refs/heads/main")]:
            with self.subTest(event=event, ref=ref), self.assertRaises(ValueError):
                ci.release_ref(event, ref, self.root)
        self.git("checkout", "-b", "topic")
        (self.root / "unmerged.txt").write_text("unmerged", encoding="utf-8")
        self.git("add", "unmerged.txt")
        self.git("commit", "-m", "Fixture unmerged work")
        with self.assertRaises(subprocess.CalledProcessError):
            ci.release_ref("push", "refs/tags/v0.8.1", self.root)

    def test_complete_bundles_pass_and_missing_target_or_changed_zip_fails(self):
        _, _, targets = ci.configuration(self.root)
        for target in targets:
            self.bundle(target)
        ci.checksums(self.assets)
        self.assertEqual(ci.verify_assets(self.assets, self.root), targets)
        path = self.assets / (targets[0] + ".zip")
        original = path.read_bytes()
        path.write_bytes(original + b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            ci.verify_assets(self.assets, self.root)
        path.write_bytes(original)
        path.unlink()
        path.with_suffix(".zip.sha256").unlink()
        with self.assertRaises(ValueError):
            ci.verify_assets(self.assets, self.root)

    def test_rehashed_bundle_cannot_hide_wrong_version_or_jar(self):
        _, _, targets = ci.configuration(self.root)
        for target in targets:
            self.bundle(target)
        for options in ({"version": "0.8.0"}, {"bad_jar": True}):
            with self.subTest(options=options):
                self.bundle(targets[0], **options)
                ci.checksums(self.assets)
                with self.assertRaises(ValueError):
                    ci.verify_assets(self.assets, self.root)

    def test_unexpected_files_and_empty_release_fail(self):
        with self.assertRaises(ValueError):
            ci.checksums(self.assets)
        with self.assertRaises(ValueError):
            ci.verify_assets(self.assets, self.root)
        (self.assets / "unexpected.txt").write_text("extra", encoding="utf-8")
        with self.assertRaises(ValueError):
            ci.verify_assets(self.assets, self.root)


if __name__ == "__main__":
    unittest.main()
