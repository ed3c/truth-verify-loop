from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_fixture_layout", ROOT / "scripts/check_fixture_layout.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FixtureLayoutTests(unittest.TestCase):
    def test_good_layout_passes(self) -> None:
        self.assertEqual(MODULE.validate(ROOT / "tests/fixtures/layout-good"), [])

    def test_hollow_layout_fails(self) -> None:
        failures = MODULE.validate(ROOT / "tests/fixtures/layout-hollow")
        self.assertTrue(any("overlap" in failure for failure in failures), failures)
        self.assertTrue(any("missing or empty" in failure for failure in failures), failures)


if __name__ == "__main__":
    unittest.main()
