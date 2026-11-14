"""Audit frozen stage bytes, create their index, then verify staged Git blobs."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def staged_entries():
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
    entries = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        header, name = item.split(b"\t", 1)
        mode, oid, stage = header.split()
        assert stage == b"0", item
        entries[name.decode("utf-8")] = oid.decode("ascii")
    return entries


def verify_blobs(expected):
    entries = staged_entries()
    missing = set(expected) - set(entries)
    assert not missing, sorted(missing)
    names = sorted(expected)
    ids = [entries[name] for name in names]
    raw = subprocess.check_output(
        ["git", "cat-file", "--batch"], input=("\n".join(ids) + "\n").encode(), cwd=ROOT
    )
    offset = 0
    for name, oid in zip(names, ids):
        end = raw.index(b"\n", offset)
        actual_oid, kind, size = raw[offset:end].split()
        assert actual_oid.decode() == oid and kind == b"blob", name
        offset = end + 1
        length = int(size)
        payload = raw[offset:offset + length]
        assert hashlib.sha256(payload).hexdigest() == expected[name], name
        offset += length
        assert raw[offset:offset + 1] == b"\n"
        offset += 1
    assert offset == len(raw)
    return len(names)


def index_stage():
    plan = json.loads((BASE / "verification-plan.json").read_text(encoding="utf-8"))
    python = json.loads((BASE / "python-tests/attempt-02/execution.json").read_text(encoding="utf-8"))
    assert python["exit_code"] == 0 and not python["sources_changed_during_execution"]
    for name, sha in python["source_hashes"].items():
        assert digest(ROOT / name) == sha, name
    documents = ["README.md", "docs/ACCEPTANCE.md", "docs/COVERAGE_OFFICIAL.md",
                 "docs/RUNTIME_DESIGN.md", "docs/SUPPORT.md", "tools/acceptance/README.md"]
    link_count = 0
    for name in documents:
        source = ROOT / name
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target:
                continue
            assert (source.parent / target).exists(), (name, target)
            link_count += 1
    prefixes = tuple(path.name + "/" for path in BASE.iterdir() if path.is_dir())
    references = set()

    def inspect(value):
        if isinstance(value, dict):
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
        elif isinstance(value, str) and (value.startswith(prefixes) or value.startswith("../engineering-")):
            assert (BASE / value).exists(), value
            references.add(value)

    inspect(plan)
    products = []
    for artifact in plan["artifacts"]:
        jar = ROOT / artifact["artifact"]
        manifest = json.loads((BASE / artifact["manifest"]).read_text(encoding="utf-8"))
        assert digest(jar) == artifact["sha256"] == manifest["sha256"]
        for name, sha in manifest["inputs"].items():
            assert digest(ROOT / name) == sha, name
        junit = [ET.parse(path).getroot() for path in (BASE / artifact["junit_directory"]).glob("TEST-*.xml")]
        assert sum(int(suite.attrib["tests"]) for suite in junit) == 61
        assert all(int(suite.attrib[key]) == 0 for suite in junit for key in ("failures", "errors", "skipped"))
        with zipfile.ZipFile(jar) as packed:
            assert not any("/probe/" in name for name in packed.namelist())
        bundle = ROOT / "build/releases" / jar.with_suffix(".zip").name
        files = {
            jar.name: jar,
            jar.with_suffix(".build.json").name: jar.with_suffix(".build.json"),
            "README.md": ROOT / "build/generated/delivery" / artifact["target"] / "README.md",
            "LICENSE": ROOT / "LICENSE",
            "docs/INSTALL.md": ROOT / "docs/INSTALL.md",
            "docs/SUPPORT.md": ROOT / "docs/SUPPORT.md",
            "config/targets.json": ROOT / "config/targets.json",
        }
        with zipfile.ZipFile(bundle) as packed:
            actual = {name for name in packed.namelist() if not name.endswith("/")}
            assert actual == set(files), (artifact["target"], actual)
            for name, source in files.items():
                assert packed.read(name) == source.read_bytes(), name
        products.append({"target": artifact["target"], "jar_sha256": digest(jar),
                         "bundle_sha256": digest(bundle), "manifest_inputs": len(manifest["inputs"])})
    report = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              "passed": True, "python_tests": plan["completed"]["python_tests"],
              "document_links": link_count, "plan_evidence_paths": len(references),
              "products": products, "runtime_goal_complete": False}
    (BASE / "final-stage-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    index = {path.relative_to(BASE).as_posix(): digest(path) for path in sorted(BASE.rglob("*"))
             if path.is_file() and path.name != "sha256.json"}
    # Nested indexes are evidence too; only this root index excludes itself.
    for path in sorted(BASE.rglob("sha256.json")):
        if path.parent != BASE:
            index[path.relative_to(BASE).as_posix()] = digest(path)
    index = dict(sorted(index.items()))
    paths = [str((BASE / name).relative_to(ROOT)) for name in index]
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"],
                             input="\n".join(paths), text=True, capture_output=True, cwd=ROOT)
    assert not ignored.stdout.strip(), ignored.stdout
    (BASE / "sha256.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"indexed_files": len(index), **report}))


def verify_staged():
    index = json.loads((BASE / "sha256.json").read_text(encoding="utf-8"))
    expected = {}
    for name, sha in index.items():
        path = BASE / name
        assert digest(path) == sha, name
        expected[path.relative_to(ROOT).as_posix()] = sha
    expected[(BASE / "sha256.json").relative_to(ROOT).as_posix()] = digest(BASE / "sha256.json")
    entries = staged_entries()
    base_prefix = BASE.relative_to(ROOT).as_posix() + "/"
    assert {name for name in entries if name.startswith(base_prefix)} == set(expected)
    python = json.loads((BASE / "python-tests/attempt-02/execution.json").read_text(encoding="utf-8"))
    expected.update(python["source_hashes"])
    plan = json.loads((BASE / "verification-plan.json").read_text(encoding="utf-8"))
    for artifact in plan["artifacts"]:
        manifest = json.loads((BASE / artifact["manifest"]).read_text(encoding="utf-8"))
        expected.update({name: sha for name, sha in manifest["inputs"].items() if name in entries})
    print(json.dumps({"passed": True, "git_blob_files_verified": verify_blobs(expected),
                      "indexed_evidence_files": len(index)}))


parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=("index", "staged"))
args = parser.parse_args()
index_stage() if args.phase == "index" else verify_staged()
