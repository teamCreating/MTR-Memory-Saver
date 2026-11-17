"""Index historical Python evidence without importing or executing its scripts."""
import json
import subprocess

from . import DATA, ROOT
from .records import contained, fingerprint, verify_record


def tracked_archive_paths(root=ROOT):
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--", "evidence/**/*.py"])
    return sorted(path for path in raw.decode("utf-8").split("\0") if path)


def inventory(root=ROOT):
    return {"schema": 1, "execution": "reference-only", "scripts": [
        {"path": path, "group": path.split("/")[1], **fingerprint(contained(root, path))}
        for path in tracked_archive_paths(root)]}


def load_catalog(data=DATA):
    value = json.loads((data / "historical-scripts.json").read_text(encoding="utf-8"))
    if value["schema"] != 1 or value["execution"] != "reference-only":
        raise ValueError("Unsupported historical catalog contract")
    return value


def verify_catalog(*, root=ROOT, data=DATA):
    scripts = load_catalog(data)["scripts"]
    paths = [row["path"] for row in scripts]
    if len(paths) != len(set(paths)) or sorted(paths) != tracked_archive_paths(root):
        raise ValueError("Historical catalog differs from tracked evidence scripts; regenerate and review it")
    for row in scripts:
        verify_record(contained(root, row["path"]), row)
    return {"historical_scripts": len(scripts)}
