"""Verify preserved native observer identities, source inputs, and JUnit evidence."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET
import zipfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    output = OUT / "verification.json"
    if output.exists():
        raise ValueError("Refuse to overwrite verification")
    rows = []
    for target in ("official-nf248", "official-nf265"):
        directory = OUT / ("final-" + target)
        jar_path = directory / f"mtr-native-observer-{target}-1.0.2.jar"
        manifest = json.loads(jar_path.with_suffix(".build.json").read_bytes())
        assert digest(jar_path) == manifest["sha256"]
        for relative, expected in manifest["inputs"].items():
            assert digest(directory / "source-inputs" / relative) == expected, relative
            assert digest(ROOT / relative) == expected, relative
        with zipfile.ZipFile(jar_path) as jar:
            metadata = json.loads(jar.read("mtr-native-observer-target.json"))
            capabilities = json.loads(jar.read("capabilities.json"))["capabilities"]
            assert metadata["observer_version"] == "1.0.2" and metadata["target"] == target
            assert metadata["diagnostics_schema"] == 1 and capabilities["native_model_diagnostics"] is True
            assert all(capabilities[name] is False for name in ("module_counters", "active_read_permits", "text_workspace"))
            classes = {}
            for name in jar.namelist():
                if not name.endswith(".class"):
                    continue
                raw = jar.read(name)
                assert name.startswith(("dev/abenli/neutralprobe/", "dev/abenli/probeio/")), name
                for forbidden in (b"site/benli06", b"site.benli06", b"dev/abenli/mtrmemory", b"dev.abenli.mtrmemory",
                                  b"getCachedVehicleResource", b"awaitParsing", b"getOptimizedModel"):
                    assert forbidden not in raw, (name, forbidden)
                classes[name] = hashlib.sha256(raw).hexdigest()
        junit = [ET.parse(path).getroot() for path in (directory / "junit").glob("TEST-*.xml")]
        counts = {key: sum(int(suite.attrib[key]) for suite in junit) for key in ("tests", "failures", "errors", "skipped")}
        assert counts == {"tests": 24, "failures": 0, "errors": 0, "skipped": 0}
        reproduction = json.loads((OUT / "reproducibility" / f"{target}.json").read_bytes())
        assert reproduction["expected"] == reproduction["actual"] == manifest["sha256"] and reproduction["equal"] is True
        rows.append({"target": target, "sha256": manifest["sha256"], "source_inputs": len(manifest["inputs"]),
                     "classes": classes, "junit": counts, "product_version_independent_build": reproduction})
    report = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              "scope": "Engineering verification. Live application and qualification are separate evidence.",
              "targets": rows,
              "test_sources": {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted((ROOT / "tools/probes/neutral/test").rglob("*.java"))},
              "passed": True}
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "targets": [{"target": row["target"], "junit": row["junit"], "classes": len(row["classes"])} for row in rows]}))


if __name__ == "__main__":
    main()
