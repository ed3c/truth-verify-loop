"""Public-only verification canary for the Inception A3 evidence pipeline."""

from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .inception_evidence import (
    sha256_text,
    validate_citation_claim,
    validate_code_evidence,
)


PUBLIC_REPOSITORY = "ed3c/truth-verify-loop"
PUBLIC_COMMIT = "c01254547672a9ad03345c9013b20d3d1049e274"
PUBLIC_TREE = "577213165a091aee389e9c7028570eb8cf6da1c7"
PUBLIC_PATH = "harness/orchestrator.py"
PUBLIC_SYMBOL = "run_live_verification"


class PublicCanaryError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as exc:
        raise PublicCanaryError(exc.output.decode("utf-8", errors="replace")) from exc


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def reconcile_fixture_reviewers(regex_support: bool, ast_support: bool) -> str:
    if regex_support and ast_support:
        return "SUPPORTED"
    if regex_support != ast_support:
        return "CONFLICTED"
    return "ABSTAIN"


def _semantic_receipt(
    *, statement: str, regex_support: bool, ast_support: bool, state: str
) -> str:
    payload = {
        "schema_version": "truth-verify-loop/inception-semantic-fixture-receipt/v1",
        "subject": {
            "repository": PUBLIC_REPOSITORY,
            "commit": PUBLIC_COMMIT,
            "tree": PUBLIC_TREE,
            "path": PUBLIC_PATH,
        },
        "statement": statement,
        "reviewers": [
            {"id": "regex-symbol-reviewer/v1", "supports": regex_support},
            {"id": "python-ast-symbol-reviewer/v1", "supports": ast_support},
        ],
        "state": state,
        "evidence_ceiling": "PUBLIC_DETERMINISTIC_FIXTURE_ONLY",
    }
    return sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def run_public_blob_canary(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    observed_tree = _git(repository_root, "rev-parse", f"{PUBLIC_COMMIT}^{{tree}}").decode().strip()
    if observed_tree != PUBLIC_TREE:
        raise PublicCanaryError(
            f"tree mismatch for public subject: expected {PUBLIC_TREE}, got {observed_tree}"
        )

    raw = _git(repository_root, "show", f"{PUBLIC_COMMIT}:{PUBLIC_PATH}")
    source = raw.decode("utf-8")
    lines = source.splitlines(keepends=True)
    start_line = next(
        (
            index
            for index, line in enumerate(lines, start=1)
            if line.startswith(f"def {PUBLIC_SYMBOL}(")
        ),
        None,
    )
    if start_line is None:
        raise PublicCanaryError("public symbol definition was not found")
    snippet = lines[start_line - 1]

    with tempfile.TemporaryDirectory(prefix="inception-a3-public-") as directory:
        root = Path(directory)
        target = root / PUBLIC_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        code_result = validate_code_evidence(
            root,
            {
                "schema_version": "truth-verify-loop/inception-code-evidence/v1",
                "repository": PUBLIC_REPOSITORY,
                "commit": PUBLIC_COMMIT,
                "tree": PUBLIC_TREE,
                "path": PUBLIC_PATH,
                "start_line": start_line,
                "end_line": start_line,
                "snippet_digest": sha256_text(snippet),
                "symbol": PUBLIC_SYMBOL,
                "parser": "python-ast",
                "parser_coverage": "FULL",
                "physical_state": "CANDIDATE",
                "claims_not_proven": [
                    "Public blob readback does not prove any business claim.",
                    "Parser presence does not by itself prove semantic entailment.",
                ],
            },
        )

        regex_support = f"def {PUBLIC_SYMBOL}(" in source
        parsed = ast.parse(source, filename=PUBLIC_PATH)
        ast_support = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == PUBLIC_SYMBOL
            for node in ast.walk(parsed)
        )
        semantic_state = reconcile_fixture_reviewers(regex_support, ast_support)
        semantic_receipt = _semantic_receipt(
            statement=f"{PUBLIC_SYMBOL} is defined in {PUBLIC_PATH}",
            regex_support=regex_support,
            ast_support=ast_support,
            state=semantic_state,
        )
        citation_result = validate_citation_claim(
            {
                "schema_version": "truth-verify-loop/inception-citation-claim/v1",
                "source_digest": _digest_bytes(raw),
                "locator": f"{PUBLIC_PATH}:L{start_line}",
                "quote": snippet.rstrip("\n"),
                "quote_digest": sha256_text(snippet.rstrip("\n")),
                "lexical_state": "PASS",
                "semantic_state": semantic_state,
                "semantic_receipt": semantic_receipt,
                "claims_not_proven": [
                    "Fixture semantic agreement is not an external independent model review.",
                    "No private evidence or business claim closure is represented.",
                ],
            }
        )

    return {
        "schema_version": "truth-verify-loop/inception-public-canary/v1",
        "subject": {
            "repository": PUBLIC_REPOSITORY,
            "commit": PUBLIC_COMMIT,
            "tree": PUBLIC_TREE,
            "path": PUBLIC_PATH,
            "blob_digest": _digest_bytes(raw),
        },
        "code": code_result,
        "citation": citation_result,
        "reviewers": ["regex-symbol-reviewer/v1", "python-ast-symbol-reviewer/v1"],
        "evidence_ceiling": "PUBLIC_DETERMINISTIC_FIXTURE_ONLY",
        "claims_not_proven": [
            "No private evidence was accessed.",
            "No external semantic provider was executed.",
            "No arbitrary business claim was supported or refuted.",
            "No Human admission, merge, release or rollback occurred.",
        ],
    }
