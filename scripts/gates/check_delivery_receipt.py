#!/usr/bin/env python3
"""Validate the materialized Forgejo delivery receipt without network access."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


REGISTRY_REL = Path(".skill-bindings/forgejo-delivery-loop/registry.json")


def fail(message: str) -> None:
    raise ValueError(message)


def load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing file: {path}")
    except json.JSONDecodeError as error:
        fail(f"invalid JSON in {path}: {error}")
    if not isinstance(value, dict):
        fail(f"expected a JSON object in {path}")
    return value


def local_url(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{field} must be a non-empty URL")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.netloc != "localhost:3000":
        fail(f"{field} must point to http://localhost:3000, got {value!r}")
    return value


def check(root: Path) -> None:
    root = root.resolve()
    registry_path = root / REGISTRY_REL
    registry = load_object(registry_path)
    required = registry.get("required_receipt_fields")
    lines = registry.get("lines")
    if not isinstance(required, list) or not required:
        fail(f"{registry_path} has no required_receipt_fields[]")
    if not isinstance(lines, list) or not lines:
        fail(f"{registry_path} has no lines[]")

    checked = 0
    for line in lines:
        if not isinstance(line, dict):
            fail("registry lines[] entries must be objects")
        materialized = line.get("materialized_path")
        if materialized in (None, ""):
            print(f"SKIP {line.get('line', '?')}: not materialized")
            continue
        target = (root / str(materialized)).resolve()
        if target != root and root not in target.parents:
            fail(f"materialized_path escapes repository: {materialized!r}")
        if not target.is_dir():
            print(f"SKIP {line.get('line', '?')}: path is absent ({materialized})")
            continue

        receipt = load_object(target / "delivery.json")
        for field in required:
            if receipt.get(field) in (None, "", []):
                fail(f"delivery.json lacks required field {field!r}")
        if receipt["line"] != line.get("line"):
            fail("delivery.json line does not match registry line")
        if receipt["repo"] != line.get("forgejo_repo"):
            fail("delivery.json repo does not match registry forgejo_repo")

        local_url(receipt["pr"], "pr")
        local_url(receipt["milestone_url"], "milestone_url")
        issues = receipt["issues"]
        if not isinstance(issues, list) or not issues:
            fail("issues must be a non-empty list")
        for index, issue in enumerate(issues):
            local_url(issue, f"issues[{index}]")
        commit = receipt["synced_at_commit"]
        if not isinstance(commit, str) or not 7 <= len(commit) <= 40:
            fail("synced_at_commit must be a 7-40 character commit id")
        if any(character not in "0123456789abcdef" for character in commit.lower()):
            fail("synced_at_commit must be hexadecimal")

        checked += 1
        print(
            f"PASS {receipt['line']}: pr={receipt['pr']} "
            f"issues={len(issues)} commit={commit[:12]}"
        )

    if not checked:
        print("PASS: no registered delivery line is materialized")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    try:
        check(root)
    except (OSError, ValueError) as error:
        print(f"FAIL delivery receipt: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
