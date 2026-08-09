#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 -m unittest discover -s "$ROOT/tests"
python3 -m unittest discover -s "$ROOT/core" -p 'test_*.py'
bash "$ROOT/core/tests/run-tests.sh"
python3 "$ROOT/scripts/check_fixture_layout.py" "$ROOT/examples/synthetic/fixtures"
python3 "$ROOT/scripts/check_public_surface.py" "$ROOT"
echo "VERIFY PASS"
