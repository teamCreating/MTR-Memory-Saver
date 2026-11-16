"""Verify captured release ZIPs independently of Gradle and the build runner."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlsplit
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_members(members, record, manifest, assessment):
    expected = {manifest["artifact"], manifest["artifact"].replace(".jar", ".build.json"),
                "LICENSE", "README.md", "docs/INSTALL.md", "docs/SUPPORT.md", "docs/VALIDATION.json", "config/targets.json"}
    require(set(members) == expected, "Release member inventory differs")
    require(sha(members[manifest["artifact"]]) == record["artifactSha256"] == manifest["sha256"], "Changed product JAR")
    require(manifest["target"] == record["target"] and manifest["version"] == record["version"], "Wrong version/target manifest")
    packaged = json.loads(members["docs/VALIDATION.json"])
    require(packaged["target"] == record["target"] and packaged["version"] == record["version"]
            and packaged["artifactSha256"] == record["artifactSha256"]
            and packaged["assessmentSha256"] == record["assessmentSha256"]
            and packaged["status"] == "verified-packaged-scope", "Validation metadata differs from exact artifact")
    require(packaged["scope"] == assessment["scope"] and packaged["cases"] ==
            [row for row in assessment["cases"] if row["target"] == record["target"]], "Validation overstates/replaces recorded cases")
    links = []
    for name, data in members.items():
        if not name.endswith(".md"):
            continue
        text = data.decode("utf-8")
        require("{{" not in text, "Unresolved document template field")
        for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if link.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):
                continue
            resolved = unquote(urlsplit(urljoin("https://release.invalid/" + name, link)).path.lstrip("/"))
            require(resolved in members, "Broken local navigation: " + name + " -> " + link)
            links.append({"source": name, "link": link, "resolved": resolved})
    require(b"development candidate" in members["README.md"]
            and b"development candidate" in members["docs/SUPPORT.md"], "Candidate label missing")
    with zipfile.ZipFile(io.BytesIO(members[manifest["artifact"]])) as product:
        metadata = json.loads(product.read("mtr-memory-target.json"))
        require(metadata["target"] == record["target"] and metadata["version"] == record["version"], "Wrong embedded product identity")
        require(not any("probe" in name.lower() for name in product.namelist()), "Product probe leaked")
    return links


def verify(root):
    expected = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))["files"]
    actual = {path.relative_to(root).as_posix(): {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
              for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts
              and path.relative_to(root).as_posix() not in {"SHA256SUMS.json", "sealed-verification.json"}}
    require(actual == expected, "Sealed release inventory changed")
    registry = json.loads((root / "source/config/delivery-evidence.json").read_text(encoding="utf-8"))
    results, negative = [], []
    for record in registry["records"]:
        directory = root / record["target"]
        archive_path = directory / (f"mtr-memory-saver-{record['target']}-{record['version']}.zip")
        with zipfile.ZipFile(archive_path) as archive:
            require(archive.testzip() is None, "Captured release CRC failed")
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
            require(len(names) == len(set(names)), "Duplicate release members")
            members = {name: archive.read(name) for name in names}
        manifest_name, = [name for name in members if name.endswith(".build.json")]
        manifest = json.loads(members[manifest_name])
        assessment_bytes = (root / "source" / record["assessment"]).read_bytes()
        require(sha(assessment_bytes) == record["assessmentSha256"], "Changed source assessment")
        assessment = json.loads(assessment_bytes)
        links = validate_members(members, record, manifest, assessment)
        for relative, digest in manifest["inputs"].items():
            require(sha((root / "inputs" / record["target"] / relative).read_bytes()) == digest,
                    "Declared build source changed: " + relative)
        for name, data in members.items():
            require((directory / "files" / name).read_bytes() == data, "Captured member copy differs")
        controls = {}
        altered = dict(members)
        altered.pop("docs/SUPPORT.md")
        controls["missing_support"] = altered
        altered = dict(members)
        altered["docs/SUPPORT.md"] += b"\n[missing](absent.md)\n"
        controls["broken_navigation"] = altered
        altered = dict(members)
        altered["docs/SUPPORT.md"] = altered["docs/SUPPORT.md"].replace(b"development candidate", b"approved release")
        controls["promoted_candidate"] = altered
        altered = dict(members)
        altered[manifest["artifact"]] += b"changed"
        controls["changed_product"] = altered
        altered = dict(members)
        value = json.loads(altered["docs/VALIDATION.json"])
        value["version"] = "0.0.0"
        altered["docs/VALIDATION.json"] = json.dumps(value).encode()
        controls["other_version_evidence"] = altered
        altered = dict(members)
        value = json.loads(altered["docs/VALIDATION.json"])
        value["cases"][0]["passed"] = False
        altered["docs/VALIDATION.json"] = json.dumps(value).encode()
        controls["replaced_actual_outcome"] = altered
        for label, altered in controls.items():
            try:
                validate_members(altered, record, manifest, assessment)
            except ValueError as error:
                negative.append({"target": record["target"], "control": label, "rejected": True, "reason": str(error)})
            else:
                raise AssertionError("Accepted altered bundle: " + label)
        results.append({"target": record["target"], "version": record["version"],
                        "artifact_sha256": record["artifactSha256"], "bundle_sha256": sha(archive_path.read_bytes()),
                        "file_members": len(members), "local_links": len(links), "passed": True})
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "passed": True,
            "payload_files": len(actual), "bundles": results, "negative_controls": negative,
            "verifier_sha256": sha(Path(__file__).read_bytes()),
            "scope": "Sealed candidate bundle bytes, exact source/evidence identities and navigation only; no Gradle or client launch."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    output = args.root / "sealed-verification.json"
    require(not output.exists(), "Do not overwrite sealed verification")
    result = verify(args.root.resolve())
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "bundles": len(result["bundles"]), "negative_controls": len(result["negative_controls"])}))
