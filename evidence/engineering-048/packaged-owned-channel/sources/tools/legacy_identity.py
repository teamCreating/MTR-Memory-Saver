"""Explicit, immutable identity adaptation for audited historical companions.

This adapter does not add modern metadata or API support to the original JAR.
The catalogue pins original JAR and manifest bytes; metadata is also interpreted
so that the resulting launcher identity retains the actual dependency contract.
"""
import hashlib
import json
import pathlib
import tomllib
import zipfile


def digest(path):
    with pathlib.Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_legacy_identity(path, matrix, baseline, catalogue, manifest_path=None):
    path = pathlib.Path(path)
    if catalogue.get("schema") != 1 or baseline not in catalogue.get("baselines", {}):
        raise ValueError("Select an explicitly audited legacy baseline.")
    pinned = catalogue["baselines"][baseline]
    target = matrix["targets"].get(pinned["target"])
    if target is None or target["variant"] != "official":
        raise ValueError("Legacy baseline must target the official matrix.")
    manifest_path = pathlib.Path(manifest_path) if manifest_path else path.with_suffix(".build.json")
    if digest(path) != pinned["sha256"] or digest(manifest_path) != pinned["manifest_sha256"]:
        raise ValueError("Legacy JAR/manifest fingerprint differs from the audited baseline.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected = {
        "target": {"minecraft": matrix["minecraft"], "mtr": matrix["mtr"]["official"]["version"]},
        "version": pinned["version"], "mod_loader": "neoforge", "loader_version": target["neoForge"],
        "release_jar_sha256": matrix["mtr"]["official"]["sha256"], "output_sha256": pinned["sha256"],
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Legacy manifest differs from the audited target matrix.")
    with zipfile.ZipFile(path) as archive:
        if "mtr-memory-target.json" in archive.namelist():
            raise ValueError("Modern embedded identity is not a legacy baseline.")
        raw_metadata = archive.read("META-INF/neoforge.mods.toml")
        # Old releases contain CR CR LF; normalize line endings for TOML parsing
        # while retaining the SHA of the original, unchanged metadata bytes.
        metadata = tomllib.loads(raw_metadata.decode("utf-8").replace("\r\r\n", "\n"))
        mods = metadata.get("mods", [])
        if (metadata.get("modLoader") != "lowcodefml" or metadata.get("loaderVersion") != "[4,)"
                or len(mods) != 1 or mods[0].get("modId") != matrix["modId"]
                or mods[0].get("version") != pinned["version"]):
            raise ValueError("Legacy mod metadata identity mismatch.")
        dependencies = metadata.get("dependencies", {}).get(matrix["modId"], [])
        ranges = {"minecraft": f"[{matrix['minecraft']}]", "neoforge": f"[{target['neoForge']},)",
                  "mtr": f"[{matrix['mtr']['official']['version']}]"}
        if len(dependencies) != len(ranges) or {item.get("modId") for item in dependencies} != set(ranges):
            raise ValueError("Legacy dependency set mismatch.")
        for item in dependencies:
            if (item.get("versionRange") != ranges[item["modId"]] or item.get("type") != "required"
                    or item.get("side") != "CLIENT"
                    or item.get("ordering") != ("AFTER" if item["modId"] == "mtr" else "NONE")):
                raise ValueError("Legacy dependency contract mismatch.")
        mixins = metadata.get("mixins", [])
        if not mixins or any(json.loads(archive.read(item["config"])).get("compatibilityLevel")
                             != f"JAVA_{matrix['java']}" for item in mixins):
            raise ValueError("Legacy Mixin Java compatibility mismatch.")
    return {"identity_format": "legacy_manifest", "legacy_baseline": baseline, "target": pinned["target"],
            "version": pinned["version"], "java": matrix["java"], "minecraft": matrix["minecraft"],
            "mtrSha256": matrix["mtr"]["official"]["sha256"], "neoForge": target["neoForge"],
            "artifact": path.name, "sha256": pinned["sha256"], "manifest_sha256": pinned["manifest_sha256"],
            "mod_metadata_sha256": hashlib.sha256(raw_metadata).hexdigest(),
            "module_api_capabilities": {"status": "unsupported", "reason": "Historical artifact has no modern observer API."}}
