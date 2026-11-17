"""Unittest worker, run in an isolated interpreter by the kit's CLI."""
import argparse
import unittest

from . import ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test_*.py")
    args = parser.parse_args(argv)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=args.pattern, top_level_dir=str(ROOT))
    if suite.countTestCases() == 0:
        parser.error(f"No tests match {args.pattern!r}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
