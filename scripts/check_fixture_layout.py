#!/usr/bin/env python3
"""Validate the blind fixture topology for a truth-verification run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _topics(path: Path) -> tuple[set[str], list[str]]:
    failures: list[str] = []
    if not path.is_file():
        return set(), [f"missing list: {path.name}"]
    topics = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not topics:
        failures.append(f"{path.name} must name at least one topic")
    return topics, failures


def validate(root: Path) -> list[str]:
    root = root.resolve()
    dev, failures = _topics(root / "dev.list")
    holdout, holdout_failures = _topics(root / "holdout.list")
    failures.extend(holdout_failures)
    overlap = dev & holdout
    if overlap:
        failures.append(f"dev/holdout overlap: {', '.join(sorted(overlap))}")
    for topic in sorted(dev | holdout):
        required = (
            root / "articles" / f"{topic}.md",
            root / "mutated" / f"{topic}.md",
            root / "mut-config" / f"{topic}.json",
            root / "_sealed" / f"{topic}.ledger.jsonl",
        )
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                failures.append(f"missing or empty fixture: {path.relative_to(root)}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    args = parser.parse_args(argv)
    failures = validate(args.fixtures)
    if failures:
        for failure in failures:
            print(f"FIXTURE-LAYOUT FAIL: {failure}", file=sys.stderr)
        return 2
    print("FIXTURE-LAYOUT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
