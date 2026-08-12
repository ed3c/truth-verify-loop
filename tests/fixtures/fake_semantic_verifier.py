#!/usr/bin/env python3
"""Deterministic stdin/stdout stand-in for semantic command adapter tests."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time


payload = json.load(sys.stdin)
mode = sys.argv[1] if len(sys.argv) > 1 else "entails"
if mode == "recover":
    state = Path(sys.argv[2])
    if not state.exists():
        state.write_text("failed-once", encoding="utf-8")
        print("fixture primary failure", file=sys.stderr)
        raise SystemExit(17)
if mode == "fail":
    print("fixture failure", file=sys.stderr)
    raise SystemExit(17)
if mode == "timeout":
    time.sleep(2)
if mode == "invalid":
    print("not-json")
    raise SystemExit(0)
if mode == "oversized":
    sys.stdout.write("x" * 1_100_000)
    raise SystemExit(0)
if mode == "child-holds-pipe":
    subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        stdin=subprocess.DEVNULL,
    )
    time.sleep(5)
if mode == "parent-exits-child-holds-pipe":
    subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        stdin=subprocess.DEVNULL,
    )
    raise SystemExit(0)
if mode == "escaped-child-holds-pipe":
    subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    raise SystemExit(0)
if mode == "require-judge" and payload.get("role") != "judge":
    print("expected judge role", file=sys.stderr)
    raise SystemExit(19)
if mode == "verify-instruction-digest":
    import hashlib

    if any(
        hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
        != item["sha256"]
        for item in payload["instructions"]
    ):
        print("instruction digest mismatch", file=sys.stderr)
        raise SystemExit(23)
if mode == "assert-isolated-runtime":
    workdir = Path.cwd()
    if Path(os.environ.get("HOME", "missing")).resolve() != workdir:
        print("HOME is not the disposable cwd", file=sys.stderr)
        raise SystemExit(29)
    if any(key in os.environ for key in ("SSH_AUTH_SOCK", "XDG_CONFIG_HOME")):
        print("credential-bearing environment leaked", file=sys.stderr)
        raise SystemExit(31)
    if list(workdir.iterdir()):
        print("disposable cwd is not empty", file=sys.stderr)
        raise SystemExit(37)
if mode == "assert-explicit-cli-home":
    cli_home = os.environ.get("TVL_CLI_HOME")
    if not cli_home or not Path(cli_home).is_absolute():
        print("TVL_CLI_HOME was not preserved", file=sys.stderr)
        raise SystemExit(41)
    if Path(os.environ.get("HOME", "missing")).resolve() == Path(cli_home).resolve():
        print("credential home replaced the disposable process HOME", file=sys.stderr)
        raise SystemExit(43)

reviews = [
    {
        "request_id": request["request_id"],
        "evidence_id": request["evidence"]["evidence_id"],
        "verdict": (
            "DOES_NOT_ENTAIL" if mode == "does-not-entail" else "ENTAILS"
        ),
        "rationale_summary": "The captured quote entails the proposed relationship.",
    }
    for request in payload["requests"]
]
if mode == "missing-review":
    reviews = []
json.dump(
    {
        "schema": "tvl.semantic-review-batch.v1",
        "reviews": reviews,
        "usage": (
            {"input_tokens": -1}
            if mode == "invalid-usage"
            else {"input_tokens": 11, "output_tokens": 4, "cost_usd": 0.02}
        ),
    },
    sys.stdout,
)
if mode == "fail-with-usage":
    raise SystemExit(17)
