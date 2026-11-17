"""Repository-derived CI metadata and fail-closed release validation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RUNNERS = ("ubuntu-24.04", "windows-2022")


def configuration(root=ROOT):
    matrix = json.loads((root / "config/targets.json").read_text(encoding="utf-8"))
    properties = (root / "gradle.properties").read_text(encoding="utf-8")
    versions = re.findall(r"(?m)^modVersion\s*=\s*(\S+)\s*$", properties)
    if len(versions) != 1 or not re.fullmatch(r"0\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", versions[0]):
        raise ValueError("Require one valid 0.x.x modVersion in gradle.properties.")
    targets = sorted(name for name, value in matrix["targets"].items() if value["variant"] == "official")
    if not targets:
        raise ValueError("No official build targets are configured.")
    return matrix, versions[0], targets


def release_ref(event, ref, root=ROOT):
    _, version, _ = configuration(root)
    tag = "v" + version
    if event == "push":
        if ref != "refs/tags/" + tag:
            raise ValueError("Release tag must exactly match gradle.properties modVersion.")
    elif event != "workflow_dispatch" or ref != "refs/heads/main":
        raise ValueError("Rehearsals must run on main; publishing requires a version tag.")
    subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main"], cwd=root, check=True)
    return tag


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def checksums(directory):
    archives = sorted(directory.glob("*.zip"))
    if not archives:
        raise ValueError("No release bundles were built.")
    for archive in archives:
        archive.with_suffix(".zip.sha256").write_text(digest(archive) + "  " + archive.name + "\n", encoding="utf-8")


def verify_assets(directory, root=ROOT):
    matrix, version, targets = configuration(root)
    archives = sorted(directory.glob("*.zip"))
    expected_checksums = {path.name + ".sha256" for path in archives}
    if {p.name for p in directory.iterdir()} != {p.name for p in archives} | expected_checksums:
        raise ValueError("Release assets contain missing or unexpected files.")
    found = set()
    for archive in archives:
        expected = digest(archive) + "  " + archive.name + "\n"
        if archive.with_suffix(".zip.sha256").read_text(encoding="utf-8") != expected:
            raise ValueError("Bundle checksum mismatch: " + archive.name)
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate bundle members.")
            manifests = [name for name in names if name.endswith(".build.json") and "/" not in name]
            if len(manifests) != 1:
                raise ValueError("Require exactly one root build manifest.")
            identity = json.loads(bundle.read(manifests[0]))
            target = identity["target"]
            if target not in targets or target in found or identity["version"] != version:
                raise ValueError("Unexpected, duplicate or wrong-version release target.")
            if (identity["java"] != matrix["java"] or identity["neoForge"] != matrix["targets"][target]["neoForge"]
                    or identity["mtrSha256"] != matrix["mtr"]["official"]["sha256"]):
                raise ValueError("Bundle target differs from the audited matrix.")
            artifact = identity["artifact"]
            if Path(artifact).name != artifact or hashlib.sha256(bundle.read(artifact)).hexdigest() != identity["sha256"]:
                raise ValueError("Companion JAR differs from its build manifest.")
            found.add(target)
    if found != set(targets):
        raise ValueError("All official targets must be present before publication.")
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("matrix", "release-ref", "checksums", "verify-assets"))
    parser.add_argument("directory", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "matrix":
        config, _, targets = configuration()
        print("java=" + str(config["java"]))
        print("matrix=" + json.dumps({"include": [{"os": runner, "target": target} for runner in RUNNERS for target in targets]}, separators=(",", ":")))
    elif args.command == "release-ref":
        print("tag=" + release_ref(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"]))
    elif args.directory is None:
        parser.error("This command requires an asset directory.")
    elif args.command == "checksums":
        checksums(args.directory)
    else:
        print(json.dumps({"verified_targets": verify_assets(args.directory)}))


if __name__ == "__main__":
    main()
