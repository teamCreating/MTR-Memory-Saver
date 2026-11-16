"""Capture immutable post-exit file identities; no game input or process launch."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    if path.exists():
        raise ValueError("Do not overwrite a final verification receipt")
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


for directory in sorted((BASE / "runtime").iterdir()):
    plan = read(directory / "packaged-client-plan.json")
    execution = read(directory / "execution.json")
    exited = read(directory / "packaged-client-exit.json")
    instance = Path(plan["instance"])
    result = {"timestamp": now(), "pid": exited["pid"], "plan_sha256": sha(directory / "packaged-client-plan.json"),
              "tool_sha256": sha(Path(__file__)), "mods": [], "source_sha256": {}, "passed": False}
    for item in plan["mods"]:
        actual = dict(item, sha256=sha(instance / "mods" / item["filename"]))
        if actual != item:
            raise ValueError("Installed mod bytes changed after process exit")
        result["mods"].append(actual)
    for relative, expected in execution["source_sha256"].items():
        actual = sha(ROOT / relative)
        if actual != expected:
            raise ValueError("Runtime source differs after process exit: " + relative)
        result["source_sha256"][relative] = actual
    if execution["mode"] == "mismatch":
        mtr, = [item for item in plan["mods"] if item["role"] == "mtr"]
        original, modified = Path(plan["source"]) / "mods" / mtr["filename"], instance / "mods" / mtr["filename"]
        with zipfile.ZipFile(original) as archive:
            old_comment = archive.comment
        with zipfile.ZipFile(modified) as archive:
            new_comment = archive.comment
        old_bytes, new_bytes = original.read_bytes(), modified.read_bytes()
        if new_bytes != old_bytes[:-(len(old_comment) + 2)] + len(new_comment).to_bytes(2, "little") + new_comment:
            raise ValueError("Binary negative control changed bytes outside the ZIP comment")
        result["mtr_comment_control"] = {"original_sha256": sha(original), "modified_sha256": sha(modified),
            "comment_only_change": True, "original_comment_hex": old_comment.hex(),
            "modified_comment_hex": new_comment.hex(), "member_and_metadata_bytes_unchanged": True}
    else:
        result["jfr_sha256"] = sha(directory / "acceptance.jfr")
        summary = directory / "jfr-summary"
        if not summary.exists():
            summary.mkdir()
            command = [str(Path(plan["java"]).parent / "jfr.exe"), "summary", str(directory / "acceptance.jfr")]
            receipt = {"command": command, "cwd": str(ROOT), "started": now(), "tool_sha256": sha(Path(__file__))}
            with (summary / "stdout.log").open("wb") as stdout, (summary / "stderr.log").open("wb") as stderr:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=ROOT)
                receipt["pid"] = process.pid
                receipt["exit_code"] = process.wait()
            receipt["ended"] = now()
            write(summary / "execution.json", receipt)
            if receipt["exit_code"] != 0:
                raise ValueError("Actual preserved JFR cannot be read")
    result["completed"] = now()
    result["passed"] = True
    write(directory / "final-input-verification.json", result)
    print(json.dumps({"case": directory.name, "passed": True}))
