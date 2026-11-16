"""Refresh both official bundles and audit their exact current source identity."""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import urllib.parse
import zipfile

OUTPUT = pathlib.Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
OFFSET = dt.timezone(dt.timedelta(hours=8))


def now():
    return dt.datetime.now(OFFSET).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(target, expected, version):
    manifests = list((ROOT / "build/libs").glob(f"*-{target}-{version}.build.json"))
    require(len(manifests) == 1, "Product manifest identity is ambiguous: " + target)
    manifest_path = manifests[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jar_path = ROOT / "build/libs" / manifest["artifact"]
    jar_bytes = jar_path.read_bytes()
    require(sha(jar_bytes) == expected == manifest["sha256"], "Tested product JAR changed: " + target)
    require(manifest["target"] == target and manifest["version"] == version, "Product target/version differs.")
    input_paths = [ROOT / "config/targets.json", ROOT / "build.gradle"]
    for source_root in (ROOT / "src/main", ROOT / "src/targets/official", ROOT / "build/generated/resources" / target):
        input_paths.extend(path for path in source_root.rglob("*") if path.is_file())
    actual_inputs = {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in input_paths}
    require(actual_inputs == manifest["inputs"], "Product manifest source closure differs from current sources.")
    with zipfile.ZipFile(jar_path) as product:
        names = product.namelist()
        require(not any(name.startswith(("site/benli06/probe/", "dev/abenli/neutralprobe/"))
                        or "mtr-memory-acceptance" in name or "mtr-native-observer" in name for name in names),
                "An observer entered the product JAR.")
        embedded = json.loads(product.read("mtr-memory-target.json"))
        require(embedded["target"] == target and embedded["mtrSha256"] == manifest["mtrSha256"],
                "Embedded product identity differs.")
    bundle_path = ROOT / "build/releases" / (jar_path.stem + ".zip")
    source_map = {jar_path.name: jar_path, manifest_path.name: manifest_path,
                  "README.md": ROOT / "build/generated/delivery" / target / "README.md",
                  **{name: ROOT / name for name in ("LICENSE", "docs/INSTALL.md", "docs/SUPPORT.md", "config/targets.json")}}
    entries, links = [], []
    with zipfile.ZipFile(bundle_path) as bundle:
        names = [entry.filename for entry in bundle.infolist() if not entry.is_dir()]
        require(len(names) == len(set(names)) and set(names) == set(source_map), "Release ZIP inventory differs.")
        for name in sorted(names):
            data = bundle.read(name)
            require(data == source_map[name].read_bytes(), "Release ZIP entry is stale: " + name)
            entries.append({"entry": name, "bytes": len(data), "sha256": sha(data),
                            "source": source_map[name].relative_to(ROOT).as_posix()})
            if name.endswith(".md"):
                for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", data.decode("utf-8")):
                    if link.startswith("#") or urllib.parse.urlsplit(link).scheme:
                        continue
                    resolved = urllib.parse.unquote(urllib.parse.urlsplit(urllib.parse.urljoin(
                        "https://bundle.invalid/" + name, link)).path).lstrip("/")
                    require(resolved in names, "Broken bundle navigation: " + name + " -> " + link)
                    links.append({"source": name, "link": link, "resolved_entry": resolved})
    archived = OUTPUT / target
    archived.mkdir()
    shutil.copyfile(manifest_path, archived / manifest_path.name)
    shutil.copyfile(bundle_path, archived / bundle_path.name)
    require((archived / manifest_path.name).read_bytes() == manifest_path.read_bytes(), "Archived manifest differs.")
    return {"timestamp": now(), "utc_offset": "+08:00", "target": target, "passed": True,
            "product_sha256": expected, "product_jar_unchanged": True, "observers_excluded": True,
            "manifest_sha256": sha(manifest_path.read_bytes()), "manifest_inputs": actual_inputs,
            "release_zip_sha256": sha(bundle_path.read_bytes()), "release_zip_bytes": bundle_path.stat().st_size,
            "entries": entries, "navigation": links,
            "tests": "Delivery rebuild skips test; unchanged product already passed 66 archived core tests per target.",
            "limits": "Exact delivery and source identity; no additional runtime or performance acceptance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require(not (OUTPUT / "execution.json").exists(), "Use a fresh delivery evidence directory.")
    assessment = json.loads((OUTPUT.parent / "snapshot-io/assessment.json").read_text(encoding="utf-8"))
    expected = {target: result["artifact_sha256"] for target, result in assessment["windows_packaged_reader_audits"].items()}
    require(all(target.startswith("official-") for target in expected), "Delivery scope must remain official.")
    java_home = args.java_home.resolve(strict=True)
    java = java_home / "bin/java.exe"
    env = {**os.environ, "JAVA_HOME": str(java_home), "PATH": str(java.parent) + os.pathsep + os.environ["PATH"]}
    frozen_names = ("build.gradle", "gradle.properties", "config/targets.json", "LICENSE", "docs/INSTALL.md", "docs/SUPPORT.md")
    frozen = {name: sha((ROOT / name).read_bytes()) for name in frozen_names}
    record = {"started_at": now(), "utc_offset": "+08:00", "status": "running",
              "java_home": str(java_home), "java_executable_sha256": sha(java.read_bytes()),
              "source_hashes_before": frozen, "target_execution": "sequential shared build directory", "commands": []}
    save(OUTPUT / "execution.json", record)
    try:
        java_version = subprocess.run([str(java), "-version"], capture_output=True, timeout=30, env=env)
        (OUTPUT / "java-version.stdout.log").write_bytes(java_version.stdout)
        (OUTPUT / "java-version.stderr.log").write_bytes(java_version.stderr)
        require(java_version.returncode == 0, "Java version command failed.")
        for target, expected_hash in expected.items():
            command = [str(ROOT / "gradlew.bat"), "releaseBundle", "-Ptarget=" + target, "-x", "test", "--console=plain"]
            item = {"target": target, "started_at": now(), "command": command}
            record["commands"].append(item)
            save(OUTPUT / "execution.json", record)
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=600)
            except subprocess.TimeoutExpired as error:
                (OUTPUT / (target + ".stdout.log")).write_bytes(error.stdout or b"")
                (OUTPUT / (target + ".stderr.log")).write_bytes(error.stderr or b"")
                item.update(error="Release build timeout", finished_at=now())
                save(OUTPUT / "execution.json", record)
                raise
            (OUTPUT / (target + ".stdout.log")).write_bytes(result.stdout)
            (OUTPUT / (target + ".stderr.log")).write_bytes(result.stderr)
            item.update(exit_code=result.returncode, finished_at=now())
            save(OUTPUT / "execution.json", record)
            require(result.returncode == 0, "Release build failed: " + target)
            require(frozen == {name: sha((ROOT / name).read_bytes()) for name in frozen_names}, "Frozen delivery sources changed during build.")
            result = audit(target, expected_hash, assessment["version"])
            save(OUTPUT / (target + ".audit.json"), result)
            item["audit"] = target + ".audit.json"
        record.update(status="passed", passed=True)
    except BaseException as error:
        record.update(status="failed", passed=False, error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        record.update(finished_at=now(), source_hashes_after={name: sha((ROOT / name).read_bytes()) for name in frozen_names})
        save(OUTPUT / "execution.json", record)
    print("Both official release bundles preserve their tested product JAR identity.")


if __name__ == "__main__":
    main()
