"""Explicit plan/capture/offline-inspect commands; no operation runs on import."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from .contract import fingerprint, identity, require
from .etw_diagnostic import capture_diagnostic, commands, inspect_bundle, load_profile, private_output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "capture"):
        child = sub.add_parser(action)
        child.add_argument("--target-json", required=True, type=Path, help="Actual native identity with PID, created, executable and command")
        child.add_argument("--presentmon", required=True, type=Path)
        child.add_argument("--output", required=True, type=Path)
        child.add_argument("--duration", type=int, default=25)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--bundle", required=True, type=Path)
    inspect.add_argument("--replay-output", type=Path, help="Fresh .cache directory for independent offline ETL redecoding; needed to certify saved CSV derivation")
    args = parser.parse_args(argv)
    if args.action == "inspect":
        result = inspect_bundle(args.bundle, args.replay_output)
    else:
        target = json.loads(args.target_json.read_text(encoding="utf-8-sig"))
        identity(target)
        require(20 <= args.duration <= 30, "Duration must be 20–30 seconds")
        if args.action == "capture":
            result = capture_diagnostic(args.output, target, args.presentmon, args.duration)
        else:
            profile = load_profile()
            binary = args.presentmon.resolve(strict=True)
            require(fingerprint(binary)["sha256"] == profile["presentmon_sha256"], "Unreviewed PresentMon bytes")
            output = private_output(args.output)
            session = "mtr-frame-diagnostic-" + str(uuid.uuid4())
            result = {"scope": "prospective commands only; no process attach or ETW start",
                "target": target, "session_name": session, "profile": profile,
                "commands": commands(output, binary, session, target["pid"], args.duration, profile,
                                     Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"),
                "data_source_available": False, "capture_ran": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
