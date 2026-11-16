"""Bind the isolated diagnostic world's saved rail styles to the prior native branch audit."""
import collections
import datetime as dt
import hashlib
import json
import pathlib
import sys
import zipfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT.parent / ".cache/game-test/python-libs"))
import msgpack


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    output = OUT / "saved-rail-styles"
    output.mkdir(exist_ok=False)
    plan_path = OUT / "startup-prefix/packaged-client-plan.json"
    plan = json.loads(plan_path.read_bytes())
    instance = pathlib.Path(plan["instance"])
    world = instance / "saves" / plan["world"]["name"]
    rows, styles, modes = [], collections.Counter(), collections.Counter()
    for path in sorted((world / "mtr").glob("*/*/rails/*/*")):
        if not path.is_file():
            continue
        relative = path.relative_to(world).as_posix()
        raw = path.read_bytes()
        expected = plan["world"]["files"][relative]
        assert sha(raw) == expected, "Saved rail differs from prepared world snapshot: " + relative
        data = msgpack.unpackb(raw, raw=False)
        assert isinstance(data["styles"], list) and all(isinstance(style, str) for style in data["styles"])
        destination = output / "world" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        rows.append({"path": relative, "sha256": sha(raw), "raw": data})
        styles.update(data["styles"]); modes.update([data["transportMode"]])
    config_path = instance / "config/mtr.json"
    config_raw = config_path.read_bytes()
    config = json.loads(config_raw)
    (output / "mtr.json").write_bytes(config_raw)
    assert config_raw == (OUT / "startup-prefix/config/mtr.json").read_bytes(), "MTR config changed since diagnostic prefix"
    mtr = next(instance / "mods" / item["filename"] for item in plan["mods"] if item["role"] == "mtr")
    with mtr.open("rb") as stream:
        mtr_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    assert mtr_sha == plan["artifact"]["mtrSha256"]
    with zipfile.ZipFile(mtr) as archive:
        registry = archive.read("assets/mtr/mtr_custom_resources.json")
        relevant = [row for row in json.loads(registry)["rails"] if row["id"] in ("default_3d", "default_3d_siding")]
    report = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              "scope": "Read-only persisted fixture/configuration audit; not a runtime renderer trace",
              "plan_sha256": sha(plan_path.read_bytes()), "rails": rows, "rail_count": len(rows),
              "style_counts": dict(styles), "transport_mode_counts": dict(modes),
              "has_direction_suffixed_default": any(style in styles for style in ("default_1", "default_2")),
              "default_rail_3d": config["client"]["defaultRail3D"], "config_sha256": sha(config_raw),
              "official_mtr_sha256": mtr_sha, "official_registry_sha256": sha(registry),
              "mapped_native_rail_definitions": relevant,
              "native_branch_evidence": {"path": "evidence/engineering-047/native-invalid-model/rail-consumption-assessment.json",
                                         "sha256": sha((ROOT / "evidence/engineering-047/native-invalid-model/rail-consumption-assessment.json").read_bytes())},
              "msgpack_version": msgpack.__version__,
              "interpretation": "These persisted TRAIN rails use exact default; with the captured defaultRail3D=true, the audited native render branch maps them to default_3d/default_3d_siding. They do not use the problematic default_1/default_2 lookup boundary. This does not prove active runtime styles/config or visual output.",
              "unchanged_at_end": all(sha((world / row["path"]).read_bytes()) == row["sha256"] for row in rows)
                                   and config_path.read_bytes() == config_raw}
    assert rows and all(row["raw"]["styles"] == ["default"] and row["raw"]["transportMode"] == "TRAIN" for row in rows)
    assert report["unchanged_at_end"] and len(relevant) == 2
    (output / "assessment.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("rail_count", "style_counts", "default_rail_3d", "unchanged_at_end")}))


if __name__ == "__main__":
    main()
