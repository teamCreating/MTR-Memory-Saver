"""Freeze a completed historical startup result without controlling its live JVM."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "capture-01"
ATTEMPT = REPO / ".cache/acceptance/owned-049c-startup-attempt02"
INSTANCE = REPO / ".cache/acceptance/official-nf248-owned-049c"
MANIFESTS = {
    "companion": REPO / "evidence/engineering-049/release/official-nf248/files/mtr-memory-saver-official-nf248-0.4.7.build.json",
    "observer": REPO / "evidence/engineering-049/publisher-race/sealed-01/official-nf248/mtr-native-observer-official-nf248-1.0.3.build.json",
}
INPUTS = {
    "companion": REPO / "evidence/engineering-049/full-load-startup/build-bindings-02/companion/inputs",
    "observer": REPO / "evidence/engineering-049/publisher-race/sealed-01/source",
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")


def copy(source, destination):
    started, before = now(), source.stat()
    raw = source.read_bytes()
    after, completed = source.stat(), now()
    assert before.st_size == after.st_size == len(raw) and before.st_mtime_ns == after.st_mtime_ns
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return {"source": str(source), "target": destination.relative_to(OUTPUT).as_posix(),
            "started_at": started, "read_completed_at": completed, "bytes": len(raw), "sha256": sha(raw),
            "source_size_before": before.st_size, "source_size_after": after.st_size}


def fingerprint(path):
    started, before = now(), path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after, completed = path.stat(), now()
    assert before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
    return {"path": str(path), "started_at": started, "completed_at": completed,
            "bytes": before.st_size, "sha256": digest, "stable_size_and_mtime": True}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    receipts, started = [], now()
    originals = {}
    original_files = [p for p in sorted(ATTEMPT.rglob("*")) if p.is_file()]
    for path in original_files:
        relative = path.relative_to(ATTEMPT)
        receipt = copy(path, OUTPUT / "observation" / relative)
        receipts.append(receipt)
        originals[relative.as_posix()] = receipt["sha256"]
    observation = OUTPUT / "observation"
    summary = json.loads((observation / "summary.json").read_bytes())
    assert summary["passed"] and summary["status"] == "settled" and summary["sample_count"] == summary["verified_sample_count"] == 13
    assert not summary["source_changed_during_observation"] and not summary["neutral_sources_changed"]
    assert sha((observation / "observer-source.py").read_bytes()) == summary["source_sha256"]
    assert sha((observation / "windows_snapshot_io.py").read_bytes()) == summary["snapshot_io_source_sha256"]
    for source, expected in summary["neutral_source_sha256"].items():
        assert sha((observation / Path(source).name).read_bytes()) == expected
    for name in ("packaged-client-plan.json", "packaged-client-launch.json"):
        receipts.append(copy(INSTANCE / name, OUTPUT / "instance" / name))
    plan = json.loads((OUTPUT / "instance/packaged-client-plan.json").read_bytes())
    launch = json.loads((OUTPUT / "instance/packaged-client-launch.json").read_bytes())
    assert sha((OUTPUT / "instance/packaged-client-plan.json").read_bytes()) == summary["plan_sha256"] == launch["plan_sha256"]
    assert sha((OUTPUT / "instance/packaged-client-launch.json").read_bytes()) == summary["launch_sha256"]
    bindings = []
    for mod in plan["mods"]:
        if mod["role"] in MANIFESTS:
            receipt = copy(INSTANCE / "mods" / mod["filename"], OUTPUT / "instance/mods" / mod["filename"])
            receipts.append(receipt)
            actual = receipt["sha256"]
            manifest_path = MANIFESTS[mod["role"]]
            receipts.append(copy(manifest_path, OUTPUT / "build-inputs" / mod["role"] / manifest_path.name))
            manifest = json.loads(manifest_path.read_bytes())
            assert manifest["sha256"] == actual
            for relative, expected in manifest["inputs"].items():
                source = INPUTS[mod["role"]] / relative
                receipt = copy(source, OUTPUT / "build-inputs" / mod["role"] / "inputs" / relative)
                assert receipt["sha256"] == expected
                receipts.append(receipt)
        else:
            receipt = fingerprint(INSTANCE / "mods" / mod["filename"])
            actual = receipt["sha256"]
        assert actual == mod["sha256"]
        bindings.append({**mod, "actual_sha256": actual, "copied": mod["role"] in MANIFESTS,
                         "fingerprint_receipt": receipt if mod["role"] not in MANIFESTS else None})
    save(OUTPUT / "instance/mod-bindings.json", {"mods": bindings})
    packs = []
    for index, pack in enumerate(plan["packs"], 1):
        source = fingerprint(Path(pack["source"]))
        installed = fingerprint(INSTANCE / "resourcepacks" / pack["filename"])
        assert source["sha256"] == installed["sha256"] == pack["sha256"]
        packs.append({"filename": pack["filename"], "expected_sha256": pack["sha256"],
                      "plan_source": source, "installed": installed})
        print(json.dumps({"pack_pairs_fingerprinted": index, "total": len(plan["packs"])}), flush=True)
    save(OUTPUT / "instance/pack-bindings.json", {"scope": "Plan-listed source and installed archives, hashed once per file; binaries not duplicated.", "packs": packs})
    review = json.loads((observation / "native-diagnostic-review.json").read_bytes())
    for proof in review["proofs"]:
        receipt = copy(REPO / proof["path"], OUTPUT / "proofs" / proof["path"])
        assert receipt["sha256"] == proof["sha256"]
        receipts.append(receipt)
    for relative, expected in originals.items():
        assert sha((ATTEMPT / relative).read_bytes()) == expected
    assert originals.keys() == {p.relative_to(ATTEMPT).as_posix() for p in ATTEMPT.rglob("*") if p.is_file()}
    save(OUTPUT / "freeze.json", {"started_at": started, "completed_at": now(), "source_attempt": str(ATTEMPT),
         "original_attempt_files_unchanged": originals, "read_receipts": receipts,
         "pack_hashing": "Each of 16 plan-source/installed archive pairs is read once; read receipts are preserved.",
         "tool_exit_provenance": "Root reports actual terminal exit 0; no separate original terminal receipt is present in this attempt directory.",
         "scope": "Completed historical settled startup window only. No current-source substitution, game input, exit/reload/route/rendering/performance acceptance."})
    print(json.dumps({"frozen_startup_completed": True, "read_receipts": len(receipts), "pack_pairs": len(packs), "original_files": len(originals)}))


if __name__ == "__main__":
    main()
