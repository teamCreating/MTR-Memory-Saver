"""Verified small historical samples, reusable by tests and a future MCP adapter."""
import json

from . import DATA, ROOT
from .records import contained, verify_record


def manifest(data=DATA):
    value = json.loads((data / "samples.json").read_text(encoding="utf-8"))
    if value["schema"] != 1:
        raise ValueError("Unsupported sample manifest schema")
    names = [row["name"] for row in value["datasets"]]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate sample dataset")
    return value


def sample_directory(name, *, data=DATA, source_root=ROOT, compare_sources=False):
    datasets = {row["name"]: row for row in manifest(data)["datasets"]}
    dataset = datasets[name]
    directory = contained(data / "samples", name)
    paths = set()
    for record in dataset["files"]:
        if record["path"] in paths:
            raise ValueError("Duplicate sample member")
        paths.add(record["path"])
        verify_record(contained(directory, record["path"]), record)
        if compare_sources:
            verify_record(contained(source_root, record["source"]), record)
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if not paths or paths != actual:
        raise ValueError(f"Unmanifested or missing sample members: {name}")
    return directory


def verify_samples(*, data=DATA, source_root=ROOT):
    datasets = manifest(data)["datasets"]
    for row in datasets:
        sample_directory(row["name"], data=data, source_root=source_root, compare_sources=True)
    return {"datasets": len(datasets), "files": sum(len(row["files"]) for row in datasets)}
