"""Compatibility for the old full-suite unittest discovery command.

Current tests live in tests/. Prefer python -m minecraft_testkit test; this public
unittest load_tests hook keeps legacy full-suite discovery from passing with zero
tests after the move. Old filename-specific filters must use the new entry point.
"""
from minecraft_testkit import ROOT


def load_tests(loader, standard_tests, pattern):
    return loader.discover(str(ROOT / "tests"), pattern=pattern or "test_*.py", top_level_dir=str(ROOT))
