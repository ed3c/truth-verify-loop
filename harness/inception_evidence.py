"""Read-only exact code/source/citation evidence validation for Inception A3."""

from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
from typing import Any

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class InceptionEvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InceptionEvidenceError(message)


def sha256_text(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _confined_file(root: Path, relative: str) -> Path:
    _require(bool(relative) and not relative.startswith("/"), "path must be repository-relative")
    pure = PurePosixPath(relative)
    _require(".." not in pure.parts and "." not in pure.parts, "path traversal is forbidden")
    root = root.resolve()
    target = (root / Path(*pure.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise InceptionEvidenceError("path or symlink escapes repository root") from exc
    _require(target.is_file(), "evidence path does not exist as a regular file")
    return target


def validate_code_evidence(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    _require(value.get("schema_version") == "truth-verify-loop/inception-code-evidence/v1", "schema_version")
    repository = value.get("repository")
    _require(isinstance(repository, str) and repository.strip() == repository and bool(repository), "repository")
    commit = value.get("commit")
    tree = value.get("tree")
    _require(isinstance(commit, str) and _HEX40.fullmatch(commit) is not None, "commit must be exact 40-hex")
    _require(isinstance(tree, str) and _HEX40.fullmatch(tree) is not None, "tree must be exact 40-hex")
    path = value.get("path")
    _require(isinstance(path, str), "path")
    target = _confined_file(root, path)

    start = value.get("start_line")
    end = value.get("end_line")
    _require(isinstance(start, int) and isinstance(end, int) and 1 <= start <= end, "line range")
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    _require(end <= len(lines), "line range exceeds file")
    snippet = "".join(lines[start - 1 : end])
    expected_digest = value.get("snippet_digest")
    _require(isinstance(expected_digest, str) and _DIGEST.fullmatch(expected_digest) is not None, "snippet_digest")
    _require(sha256_text(snippet) == expected_digest, "snippet digest mismatch")

    parser = value.get("parser")
    coverage = value.get("parser_coverage")
    symbol = value.get("symbol")
    _require(parser in {"python-ast", "text-only", "unavailable"}, "parser")
    _require(coverage in {"FULL", "LEXICAL_ONLY", "UNAVAILABLE"}, "parser_coverage")
    if parser == "unavailable":
        _require(coverage == "UNAVAILABLE", "unavailable parser cannot claim coverage")
        _require(symbol is None, "unavailable parser cannot verify symbol")
    elif parser == "text-only":
        _require(coverage == "LEXICAL_ONLY", "text-only parser coverage")
        _require(symbol is None, "text-only parser cannot verify symbol")
    else:
        _require(target.suffix == ".py", "python-ast requires a Python path")
        _require(coverage == "FULL", "python-ast must declare FULL coverage")
        _require(isinstance(symbol, str) and bool(symbol.strip()), "symbol required for python-ast")
        try:
            parsed = ast.parse(target.read_text(encoding="utf-8"), filename=path)
        except SyntaxError as exc:
            raise InceptionEvidenceError("parser could not cover source") from exc
        symbols = {
            node.name
            for node in ast.walk(parsed)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        _require(symbol in symbols, "symbol absent from parser result")

    _require(value.get("physical_state") in {"CANDIDATE", "PASS", "FAIL", "STALE", "UNVERIFIABLE"}, "physical_state")
    claims = value.get("claims_not_proven")
    _require(isinstance(claims, list) and claims and len(claims) == len(set(claims)), "claims_not_proven")
    return {
        "repository": repository,
        "commit": commit,
        "tree": tree,
        "path": path,
        "snippet_digest": expected_digest,
        "parser": parser,
        "parser_coverage": coverage,
        "symbol": symbol,
        "physical_state": "PASS",
    }


def validate_citation_claim(value: dict[str, Any]) -> dict[str, Any]:
    _require(value.get("schema_version") == "truth-verify-loop/inception-citation-claim/v1", "citation schema_version")
    source_digest = value.get("source_digest")
    quote_digest = value.get("quote_digest")
    quote = value.get("quote")
    _require(isinstance(source_digest, str) and _DIGEST.fullmatch(source_digest) is not None, "source_digest")
    _require(isinstance(quote, str) and bool(quote), "quote")
    _require(isinstance(quote_digest, str) and _DIGEST.fullmatch(quote_digest) is not None, "quote_digest")
    _require(sha256_text(quote) == quote_digest, "quote digest mismatch")
    locator = value.get("locator")
    _require(isinstance(locator, str) and bool(locator.strip()), "locator")
    lexical = value.get("lexical_state")
    semantic = value.get("semantic_state")
    receipt = value.get("semantic_receipt")
    _require(lexical in {"CANDIDATE", "PASS", "FAIL"}, "lexical_state")
    _require(semantic in {"NOT_EXERCISED", "SUPPORTED", "REFUTED", "CONFLICTED", "ABSTAIN"}, "semantic_state")
    if semantic != "NOT_EXERCISED":
        _require(lexical == "PASS", "semantic review requires lexical PASS")
        _require(isinstance(receipt, str) and _DIGEST.fullmatch(receipt) is not None, "semantic receipt required")
    else:
        _require(receipt is None, "unexercised semantic lane cannot have receipt")
    claims = value.get("claims_not_proven")
    _require(isinstance(claims, list) and claims, "claims_not_proven")
    return {
        "source_digest": source_digest,
        "locator": locator,
        "quote_digest": quote_digest,
        "lexical_state": lexical,
        "semantic_state": semantic,
        "semantic_receipt": receipt,
    }
