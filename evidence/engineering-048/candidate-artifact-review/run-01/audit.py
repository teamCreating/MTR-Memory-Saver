"""Read-only comparison and sealed replay of the explicitly reviewed candidate.

Writes only a newly created --output directory. It does not invoke Gradle, alter
artifacts, infer gameplay acceptance, or reconstruct missing build receipts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tomllib
import zipfile


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def jar_members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as jar:
        names = jar.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP member names")
        if jar.testzip() is not None:
            raise ValueError("ZIP CRC failure")
        return {name: jar.read(name) for name in names if not name.endswith("/")}


def compare_members(before, after, spec):
    errors = []
    if before.keys() != after.keys():
        errors.append("ZIP member inventory changed")
    changed = sorted(name for name in before.keys() & after.keys()
                     if before[name] != after[name])
    expected = sorted(spec["expected_changed_classes"] + spec["metadata_members"])
    if changed != expected:
        errors.append("Changed ZIP payloads differ from reviewed scope")
    for name in spec["metadata_members"]:
        old = before.get(name)
        new = after.get(name)
        if old is None or new is None:
            errors.append(f"Missing metadata: {name}")
            continue
        old_version = spec["reference_version"]
        new_version = spec["candidate_version"]
        # Exact byte replacement also rejects unrelated formatting/content edits.
        if old.count(old_version.encode()) != 1:
            errors.append(f"Ambiguous reference version occurrence: {name}")
        if old.replace(old_version.encode(), new_version.encode()) != new:
            errors.append(f"Metadata changed beyond version: {name}")
    return {"errors": errors, "changed": changed,
            "added": sorted(after.keys() - before.keys()),
            "removed": sorted(before.keys() - after.keys())}


def negative_controls(before, after, spec):
    controls = []

    def require_rejection(name, modified):
        errors = compare_members(before, modified, spec)["errors"]
        controls.append({"name": name, "rejected": bool(errors), "errors": errors})

    changed = dict(after)
    changed["unexpected.class"] = b"not a product class"
    require_rejection("extra ZIP member", changed)
    unchanged = next(name for name in sorted(before) if name.endswith(".class")
                     and name not in spec["expected_changed_classes"])
    changed = dict(after)
    changed.pop(unchanged)
    require_rejection("missing unchanged class", changed)
    changed = dict(after)
    changed[unchanged] += b"unexpected modification"
    require_rejection("modified class outside approved scope", changed)
    for member in spec["metadata_members"]:
        changed = dict(after)
        changed[member] += b"\nUnreviewed-field: value\n"
        require_rejection(f"unrelated metadata edit: {member}", changed)
    changed = dict(after)
    member = spec["expected_changed_classes"][0]
    changed[member] = before[member]
    require_rejection("missing expected changed class", changed)
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--spec", type=Path,
                        default=Path(__file__).with_name("review-spec.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", action="append", default=[],
                        help="Additional repository-relative receipt to seal, without interpreting it")
    args = parser.parse_args()
    started = now()
    root = args.root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    spec_raw = args.spec.read_bytes()
    spec = json.loads(spec_raw)
    observed = {}

    def read(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Input escapes review root: {relative}")
        raw = path.read_bytes()
        if relative in observed and observed[relative] != raw:
            raise ValueError(f"Input changed during capture: {relative}")
        observed[relative] = raw
        return raw

    matrix = json.loads(read("config/targets.json"))
    properties = read("gradle.properties").decode("utf-8-sig")
    default_version = next(line.split("=", 1)[1].strip()
                           for line in properties.splitlines()
                           if line.startswith("modVersion="))
    read("LICENSE")
    for relative in args.context:
        read(relative)
    results = []
    candidate_maps = {}
    all_controls = []
    for target, paths in spec["targets"].items():
        result = {"target": target, "errors": []}
        errors = result["errors"]
        manifests = {}
        maps = {}
        for kind, version in (("reference", spec["reference_version"]),
                              ("candidate", spec["candidate_version"])):
            manifest = json.loads(read(paths[f"{kind}_manifest"]))
            raw = read(paths[f"{kind}_jar"])
            manifests[kind] = manifest
            maps[kind] = jar_members(raw)
            if sha(raw) != paths[f"{kind}_sha256"]:
                errors.append(f"{kind} JAR differs from explicitly pinned bytes")
            for key, expected in {"sha256": sha(raw), "target": target,
                                  "version": version, "java": matrix["java"],
                                  "mtrSha256": matrix["mtr"]["official"]["sha256"],
                                  "neoForge": matrix["targets"][target]["neoForge"],
                                  "artifact": Path(paths[f"{kind}_jar"]).name}.items():
                if manifest.get(key) != expected:
                    errors.append(f"{kind} manifest field mismatch: {key}")
            result[kind] = {"jar": paths[f"{kind}_jar"], "sha256": sha(raw),
                            "bytes": len(raw), "manifest": paths[f"{kind}_manifest"],
                            "manifest_sha256": sha(observed[paths[f"{kind}_manifest"]]),
                            "file_members": len(maps[kind]),
                            "classes": sum(name.endswith(".class") for name in maps[kind])}
        comparison = compare_members(maps["reference"], maps["candidate"], spec)
        errors.extend(comparison.pop("errors"))
        result["payload_comparison"] = comparison
        result["members"] = [
            {"name": name, "reference_sha256": sha(maps["reference"][name]),
             "candidate_sha256": sha(maps["candidate"][name]),
             "reference_bytes": len(maps["reference"][name]),
             "candidate_bytes": len(maps["candidate"][name]),
             "unchanged": maps["reference"][name] == maps["candidate"][name]}
            for name in sorted(maps["reference"].keys() & maps["candidate"].keys())]
        result["unchanged_classes"] = [
            entry["name"] for entry in result["members"]
            if entry["name"].endswith(".class") and entry["unchanged"]]
        old_inputs = manifests["reference"]["inputs"]
        new_inputs = manifests["candidate"]["inputs"]
        result["declared_inputs"] = []
        for relative, expected in sorted(new_inputs.items()):
            raw = read(relative)
            actual = sha(raw)
            record = {"path": relative, "sha256": actual, "expected": expected,
                      "matches": actual == expected}
            result["declared_inputs"].append(record)
            if actual != expected:
                errors.append(f"Candidate declared input mismatch: {relative}")
            generated_prefix = f"build/generated/resources/{target}/"
            if relative.startswith(generated_prefix):
                member = relative.removeprefix(generated_prefix)
                if maps["candidate"].get(member) != raw:
                    errors.append(f"Generated resource differs from JAR: {member}")
            if relative.startswith("src/main/resources/"):
                member = relative.removeprefix("src/main/resources/")
                if maps["candidate"].get(member) != raw:
                    errors.append(f"Source resource differs from JAR: {member}")
        if maps["candidate"].get("LICENSE") != observed["LICENSE"]:
            errors.append("JAR license differs from current license")
        if old_inputs.keys() != new_inputs.keys():
            errors.append("Declared input inventory differs from reference")
        result["changed_declared_inputs"] = sorted(
            name for name in old_inputs.keys() & new_inputs.keys()
            if old_inputs[name] != new_inputs[name])
        changed_java = [name for name in result["changed_declared_inputs"]
                        if name.endswith(".java")]
        if changed_java != spec["expected_changed_java_sources"]:
            errors.append("Changed Java source inventory differs from reviewed scope")
        # This is an artifact audit: semantic metadata parsing complements exact
        # byte equality; it is not used to erase extra fields or normalize bytes.
        metadata = json.loads(maps["candidate"]["mtr-memory-target.json"])
        toml = tomllib.loads(maps["candidate"]["META-INF/neoforge.mods.toml"].decode())
        if metadata.get("version") != spec["candidate_version"]:
            errors.append("Embedded target version mismatch")
        if len(toml["mods"]) != 1 or toml["mods"][0]["version"] != spec["candidate_version"]:
            errors.append("Embedded mod version mismatch")
        for name, raw in maps["candidate"].items():
            if name.endswith(".class") and (raw[:4] != b"\xca\xfe\xba\xbe"
                                          or int.from_bytes(raw[6:8], "big") != matrix["java"] + 44):
                errors.append(f"Unexpected class format/Java version: {name}")
        controls = negative_controls(maps["reference"], maps["candidate"], spec)
        all_controls.append({"target": target, "controls": controls})
        if not all(control["rejected"] for control in controls):
            errors.append("Review-scope negative control unexpectedly passed")
        candidate_maps[target] = maps["candidate"]
        results.append(result)
    target_names = list(candidate_maps)
    cross_target_changes = sorted(
        name for name in candidate_maps[target_names[0]]
        if candidate_maps[target_names[0]][name] != candidate_maps[target_names[1]][name])
    cross_target_ok = cross_target_changes == sorted(spec["metadata_members"])
    end_observations = {name: sha((root / name).read_bytes()) for name in observed}
    changed_during_review = [name for name, raw in observed.items()
                             if sha(raw) != end_observations[name]]
    for name, raw in observed.items():
        destination = output / "inputs" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    (output / "audit.py").write_bytes(Path(__file__).read_bytes())
    (output / "review-spec.json").write_bytes(spec_raw)
    report = {
        "schema": 1, "started": started, "completed": now(),
        "argv": sys.argv, "python": sys.executable, "python_version": sys.version,
        "root": str(root), "passed": all(not result["errors"] for result in results)
        and cross_target_ok and not changed_during_review,
        "scope": "Exact product JAR payload and declared-source identity comparison; no gameplay or performance acceptance",
        "source_default_mod_version": default_version,
        "candidate_effective_version": spec["candidate_version"],
        "declared_manifest_limit": "Build manifest enumerates main source/resources, targets.json and build.gradle; it does not include gradle.properties, LICENSE, the JDK or all dependency/build-environment files. LICENSE is separately captured and checked here.",
        "build_command_receipts": args.context,
        "build_command_receipt_limit": "Context receipts are preserved as observed bytes; this script does not reconstruct initial build timestamps or assert execution from text matching.",
        "cross_target_changed_members": cross_target_changes,
        "cross_target_payload_scope_matches": cross_target_ok,
        "all_candidate_classes_equal_across_targets": all(
            candidate_maps[target_names[0]][name] == candidate_maps[target_names[1]][name]
            for name in candidate_maps[target_names[0]] if name.endswith(".class")),
        "inputs_changed_during_review": changed_during_review,
        "source_fingerprints_before": {name: sha(raw) for name, raw in sorted(observed.items())},
        "source_fingerprints_after": dict(sorted(end_observations.items())),
        "targets": results, "negative_controls": all_controls,
    }
    (output / "assessment.json").write_bytes(json_bytes(report))
    inventory = {str(path.relative_to(output)).replace("\\", "/"): sha(path.read_bytes())
                 for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "SHA256SUMS.json").write_bytes(json_bytes(inventory))
    print(json.dumps({"passed": report["passed"], "output": str(output),
                      "targets": [{"target": r["target"], "errors": r["errors"],
                                   "changed": r["payload_comparison"]["changed"],
                                   "unchanged_classes": len(r["unchanged_classes"]),
                                   "declared_inputs": len(r["declared_inputs"])}
                                  for r in results],
                      "negative_controls": sum(len(item["controls"]) for item in all_controls),
                      "changed_during_review": changed_during_review}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
