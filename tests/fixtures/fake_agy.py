#!/usr/bin/env python3
"""Deterministic executable stand-in for agy timeout integration tests."""

import json
import sys
import time


def argument(name: str) -> str:
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except (ValueError, IndexError):
        print(f"missing required argument: {name}", file=sys.stderr)
        raise SystemExit(64)


if "--version" in sys.argv:
    print("fake-agy 1.1.12")
    raise SystemExit(0)

prompt = argument("--print")
print_timeout = argument("--print-timeout")
if not print_timeout.endswith("s"):
    print("--print-timeout must use an explicit seconds duration", file=sys.stderr)
    raise SystemExit(64)

print(
    json.dumps(
        {
            "type": "step_update",
            "usage": {"input_tokens": 7, "cache_read_tokens": 11},
        }
    ),
    flush=True,
)

if prompt == "complete":
    envelope = {
        "schema": "tvl.search-result.v1",
        "query": prompt,
        "candidates": [
            {
                "source_uri": "https://docs.example.invalid/complete",
                "relationship": "supports",
                "quote": "complete",
            }
        ],
    }
    print(json.dumps({"type": "result", "result": envelope}), flush=True)
    raise SystemExit(0)

if prompt == "provider-timeout":
    time.sleep(float(print_timeout[:-1]))
    print("provider print timeout", file=sys.stderr, flush=True)
    raise SystemExit(124)

if prompt == "outer-timeout":
    time.sleep(1)
    raise SystemExit(0)

print(f"unknown fake prompt: {prompt}", file=sys.stderr)
raise SystemExit(64)
