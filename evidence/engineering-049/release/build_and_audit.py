"""Build and audit exact official candidate bundles; never start a game client."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote, urljoin, urlsplit
import zipfile


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def copy(path, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("Do not overwrite captured release evidence: " + str(destination))
    shutil.copy2(path, destination)


def require(value, message):
    if not value:
        raise ValueError(message)


def audit(target, record, version, directory):
    manifest_path = ROOT / "build/libs" / (f"mtr-memory-saver-{target}-{version}.build.json")
    manifest = read(manifest_path)
    candidate = ROOT / "build/libs" / manifest["artifact"]
    require(sha(candidate) == record["artifactSha256"] == manifest["sha256"], "Product JAR changed")
    require(manifest["version"] == version and manifest["target"] == target, "Wrong effective release target/version")
    for relative, digest in manifest["inputs"].items():
        require(sha(ROOT / relative) == digest, "Stale build input: " + relative)
        destination = BASE / "inputs" / target / relative
        if not destination.exists():
            copy(ROOT / relative, destination)
    bundle = ROOT / "build/releases" / (f"mtr-memory-saver-{target}-{version}.zip")
    source_files = {candidate.name: candidate, manifest_path.name: manifest_path,
        "LICENSE": ROOT / "LICENSE", "README.md": ROOT / f"build/generated/delivery/{target}/README.md",
        "docs/INSTALL.md": ROOT / "docs/INSTALL.md",
        "docs/SUPPORT.md": ROOT / f"build/generated/delivery-support/{target}/SUPPORT.md",
        "docs/VALIDATION.json": ROOT / f"build/generated/delivery-support/{target}/VALIDATION.json",
        "config/targets.json": ROOT / "config/targets.json"}
    entries, links = {}, []
    with zipfile.ZipFile(bundle) as archive:
        require(archive.testzip() is None, "Release ZIP CRC failure")
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        require(len(names) == len(set(names)) and set(names) == set(source_files), "Release file inventory differs")
        for name, source in source_files.items():
            data = archive.read(name)
            require(data == source.read_bytes(), "Release member differs from source: " + name)
            entries[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if name.endswith(".md"):
                for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", data.decode("utf-8")):
                    if link.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):
                        continue
                    resolved = unquote(urlsplit(urljoin("https://release.invalid/" + name, link)).path.lstrip("/"))
                    require(resolved in names, "Broken bundle navigation: " + name + " -> " + link)
                    links.append({"source": name, "link": link, "resolved": resolved})
        validation = json.loads(archive.read("docs/VALIDATION.json"))
        require(validation["artifactSha256"] == manifest["sha256"] and validation["target"] == target
                and validation["version"] == version and validation["status"] == "verified-packaged-scope",
                "Runtime summary is not bound to this exact version/artifact")
        require(validation["assessmentSha256"] == record["assessmentSha256"]
                == sha(ROOT / record["assessment"]), "Runtime summary assessment identity differs")
        source_assessment = read(ROOT / record["assessment"])
        require(validation["cases"] == [case for case in source_assessment["cases"] if case["target"] == target]
                and validation["scope"] == source_assessment["scope"], "Runtime summary changed its audited scope")
        require(b"development candidate" in archive.read("docs/SUPPORT.md")
                and b"development candidate" in archive.read("README.md"), "Candidate label is missing")
    with zipfile.ZipFile(candidate) as product:
        require(not any("probe" in name.lower() for name in product.namelist()), "Probe entered product artifact")
    for name, source in source_files.items():
        copy(source, directory / "files" / name)
    copy(bundle, directory / bundle.name)
    return {"timestamp": now(), "passed": True, "target": target, "version": version,
        "artifact_sha256": sha(candidate), "exact_previously_audited_jar_unchanged": True,
        "manifest_sha256": sha(manifest_path), "declared_build_inputs_verified": len(manifest["inputs"]),
        "bundle": bundle.name, "bundle_sha256": sha(bundle), "bundle_bytes": bundle.stat().st_size,
        "zip_crc_passed": True, "file_inventory": entries, "local_markdown_links": links,
        "version_bound_validation": validation, "product_probe_excluded": True,
        "tests": "No Java test rerun: releaseBundle -x test; exact unchanged product has prior 73-test and packaged acceptance evidence.",
        "scope": "Local candidate delivery identity, contents and navigation only. No new gameplay, reload, endurance or performance claim."}


if __name__ == "__main__":
    require(not (BASE / "execution.json").exists(), "Use a fresh release build/audit evidence directory")
    properties = (ROOT / "gradle.properties").read_text(encoding="utf-8")
    version, = re.findall(r"^modVersion=(.+)$", properties, re.MULTILINE)
    records = [record for record in read(ROOT / "config/delivery-evidence.json")["records"] if record["version"] == version]
    matrix = read(ROOT / "config/targets.json")
    records = [record for record in records if matrix["targets"][record["target"]]["variant"] == "official"]
    require(len(records) == 2, "Require both reviewed official candidate records")
    frozen = {relative: sha(ROOT / relative) for relative in (
        "build.gradle", "gradle.properties", "config/targets.json", "config/delivery-evidence.json", "LICENSE",
        "docs/templates/delivery-support.md", "docs/INSTALL.md", records[0]["assessment"])}
    for relative in frozen:
        copy(ROOT / relative, BASE / "source" / relative)
    receipt = {"started": now(), "runner_sha256": sha(Path(__file__)), "cwd": str(ROOT),
               "sequential_shared_build_directory": True, "source_sha256": frozen, "commands": [], "passed": False}
    write(BASE / "execution.json", receipt)
    try:
        for record in records:
            target = record["target"]
            directory = BASE / target
            directory.mkdir()
            plan = read(ROOT / "evidence/engineering-048/packaged-owned-channel/prepared" / (target + "-faults.json"))
            java_home = Path(plan["java"]).parent.parent
            environment = os.environ.copy()
            environment["JAVA_HOME"] = str(java_home)
            environment["PATH"] = str(java_home / "bin") + os.pathsep + environment["PATH"]
            command = [str(ROOT / "gradlew.bat"), "releaseBundle", "-Ptarget=" + target, "-x", "test", "--console=plain"]
            execution = {"started": now(), "command": command, "java_home": str(java_home),
                         "java_sha256": sha(java_home / "bin/java.exe")}
            receipt["commands"].append(execution)
            write(BASE / "execution.json", receipt)
            with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
                execution["pid"] = process.pid
                write(BASE / "execution.json", receipt)
                execution["exit_code"] = process.wait()
            execution["ended"] = now()
            write(BASE / "execution.json", receipt)
            require(execution["exit_code"] == 0, "Release build failed: " + target)
            require(all(sha(ROOT / relative) == digest for relative, digest in frozen.items()),
                    "Frozen release input changed during execution")
            result = audit(target, record, version, directory)
            write(directory / "assessment.json", result)
            execution["audit_passed"] = True
            execution["bundle_sha256"] = result["bundle_sha256"]
            print(json.dumps({"target": target, "passed": True, "bundle_sha256": result["bundle_sha256"]}), flush=True)
        receipt["passed"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        receipt["ended"] = now()
        write(BASE / "execution.json", receipt)
