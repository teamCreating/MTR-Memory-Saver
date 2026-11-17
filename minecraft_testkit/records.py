"""Read and verify repository-relative, byte-preserved fixture/catalog records."""
import hashlib
from pathlib import Path, PurePosixPath


def contained(root, relative):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"Expected a relative POSIX path: {relative!r}")
    root = Path(root).resolve()
    result = (root / path).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f"Path escapes its data root: {relative!r}")
    return result


def fingerprint(path):
    raw = Path(path).read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def verify_record(path, record):
    actual = fingerprint(path)
    if any(actual[key] != record[key] for key in actual):
        raise ValueError(f"Fixture/catalog fingerprint mismatch: {path}")
