"""Offline regression/catalog commands; no game controls or MCP server."""
import argparse
from collections import Counter
import json
import os
import subprocess
import sys

from . import ROOT
from .catalog import inventory, load_catalog, verify_catalog
from .samples import manifest, verify_samples


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    tests = commands.add_parser("test", help="Run current tests in a separate interpreter")
    tests.add_argument("--pattern", "-p", default="test_*.py")
    commands.add_parser("list", help="List historical script groups and available samples")
    commands.add_parser("verify", help="Verify catalog and sample bytes against their original sources")
    commands.add_parser("inventory", help="Print a refreshed historical catalog as JSON; does not write files")
    args = parser.parse_args(argv)
    if args.command == "test":
        environment = dict(os.environ)
        # Existing runtime tools are script modules with sibling imports. Restrict
        # their import path setup to the test child; leave the caller unchanged.
        paths = [str(ROOT / "tools"), str(ROOT)]
        if environment.get("PYTHONPATH"):
            paths.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(paths)
        return subprocess.call([sys.executable, "-m", "minecraft_testkit.testing", "--pattern", args.pattern],
                               cwd=ROOT, env=environment)
    if args.command == "verify":
        result = {**verify_catalog(), **verify_samples()}
    elif args.command == "inventory":
        result = inventory()
    else:
        result = {"historical_groups": dict(sorted(Counter(row["group"] for row in load_catalog()["scripts"]).items())),
                  "samples": [{key: row[key] for key in ("name", "kind", "scope")} for row in manifest()["datasets"]]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
