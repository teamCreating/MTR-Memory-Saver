import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from minecraft_testkit import DATA, ROOT
from minecraft_testkit.catalog import inventory, verify_catalog
from minecraft_testkit.records import contained
from minecraft_testkit.samples import manifest, sample_directory, verify_samples


class TestkitTest(unittest.TestCase):
    def test_curated_samples_match_their_original_sources(self):
        result = verify_samples()
        self.assertEqual(result["datasets"], len(manifest()["datasets"]))
        self.assertGreater(result["files"], 0)

    def test_corrupt_or_unmanifested_sample_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            shutil.copytree(DATA / "samples", data / "samples")
            shutil.copyfile(DATA / "samples.json", data / "samples.json")
            dataset = manifest(data)["datasets"][0]
            directory = sample_directory(dataset["name"], data=data)
            member = directory / dataset["files"][0]["path"]
            original = member.read_bytes()
            member.write_bytes(original + b"corrupt")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                sample_directory(dataset["name"], data=data)
            member.write_bytes(original)
            (directory / "unreviewed.txt").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "Unmanifested"):
                sample_directory(dataset["name"], data=data)

    def test_resource_paths_cannot_escape_the_data_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            for path in ("../secret", "/absolute", "C:/absolute", "..\\secret", ""):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    contained(temporary, path)

    def test_archive_inventory_never_executes_scripts_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            source = root / "evidence/example/source.py"
            source.parent.mkdir(parents=True)
            source.write_text("raise RuntimeError('never execute an archived source')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "evidence"], check=True)
            data = root / "data"
            data.mkdir()
            catalog = inventory(root)
            (data / "historical-scripts.json").write_text(json.dumps(catalog), encoding="utf-8")
            self.assertEqual(verify_catalog(root=root, data=data), {"historical_scripts": 1})
            original = source.read_bytes()
            source.write_bytes(original + b"# changed\n")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                verify_catalog(root=root, data=data)
            source.write_bytes(original)
            (source.parent / "new.py").write_bytes(b"# newly tracked\n")
            subprocess.run(["git", "-C", str(root), "add", "evidence"], check=True)
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_catalog(root=root, data=data)

    def test_empty_test_selection_fails_instead_of_reporting_success(self):
        result = subprocess.run([sys.executable, "-m", "minecraft_testkit", "test", "--pattern", "no_matching_tests.py"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("No tests match", result.stderr)

    def test_legacy_full_discovery_contains_the_same_test_ids(self):
        def ids(suite):
            return [value for item in suite for value in (ids(item) if isinstance(item, unittest.TestSuite) else [item.id()])]
        current = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
        legacy = unittest.TestLoader().discover(str(ROOT / "tools"))
        self.assertGreater(current.countTestCases(), 0)
        self.assertEqual(sorted(ids(legacy)), sorted(ids(current)))


if __name__ == "__main__":
    unittest.main()
