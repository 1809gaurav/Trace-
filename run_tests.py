"""Portable test runner; prefers pytest and falls back to unittest."""

from __future__ import annotations

import sys


def main() -> int:
    """Run the test suite with pytest or the standard-library fallback."""
    try:
        import pytest
    except ImportError as error:
        if error.name != "pytest":
            raise
        print("pytest is not installed; running unittest-compatible tests instead.", flush=True)
        import unittest

        return int(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.discover("tests")
        ).wasSuccessful())
    return int(pytest.main(["-q"]))


if __name__ == "__main__":
    raise SystemExit(main())
