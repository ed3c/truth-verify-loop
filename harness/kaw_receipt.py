"""Public-safe receipt bridge for Kotlin Auto WebView L5 domain canaries."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .closure import close_claim
from .model import Claim, Evidence, canonical_json
from .policy import SourcePolicy

RECEIPT_SCHEMA = "tvl.kaw-domain-receipt.v1"
RECEIPT_LANE = "L5_LIVE_DOMAIN_AUTHORITY_RECEIPT"
RECEIPT_ID = "TVL-KAW-PUBLIC-SYNTHETIC-1"
PUBLIC_CANARY_AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)
CLOSURE_ENGINE_BLOB = "3cbbc664e3a28f99be097996dc6e229a6417c581"
SEMANTIC_VERIFIER_SCHEMA_BLOB = "2c9085b66d080abcede3861812d15bdc92986d04"
ALLOWED_VERDICTS = {"SUPPORTED", "REFUTED", "CONFLICTED", "STALE", "UNVERIFIABLE"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_MARKERS = (
    "github_pat_", "ghp_", "bearer ", "authorization:", "set-cookie:",
    "cookie:", "access_token", "refresh_token", "private key",
)


class KawReceiptError(ValueError):
    """Raised when a KAW-facing domain receipt violates its public contract."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise KawReceiptError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise KawReceiptError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    if not rows:
        raise KawReceiptError(f"{path} must contain evidence")
    return rows


def build_public_canary_receipt(
    repository_root: Path,
    *,
    as_of: datetime = PUBLIC_CANARY_AS_OF,
) -> dict[str, Any]:
    """Rebuild the exact public synthetic receipt consumed by KAW."""

    raw_claim = _load_json(repository_root / "examples/live-search/fixture-claim.json")
    raw_evidence = _load_jsonl(repository_root / "examples/live-search/fixture-evidence.jsonl")
    raw_policy = _load_json(repository_root / "config/source-policy.example.json")

    claim = Claim.from_dict(raw_claim)
    evidence = [Evidence.from_dict(row) for row in raw_evidence]
    closure = close_claim(
        claim,
        evidence,
        policy=SourcePolicy.from_dict(raw_policy),
        now=as_of,
    )
    if closure["state"] not in ALLOWED_VERDICTS:
        raise KawReceiptError(f"unsupported closure state: {closure['state']!r}")
    if closure["coverage"]["directional_sources"] != len(raw_evidence):
        raise KawReceiptError("public canary directional denominator changed")
    if len(closure["accepted_evidence_ids"]) != len(raw_evidence):
        raise KawReceiptError("public canary accepted denominator changed")

    source_digests = {item.content_sha256 for item in evidence}
    if len(source_digests) != 1:
        raise KawReceiptError("public canary requires one source-content digest")

    return {
        "schema": RECEIPT_SCHEMA,
        "lane": RECEIPT_LANE,
        "receipt_id": RECEIPT_ID,
        "authority": {"kind": "DOMAIN_REPOSITORY", "owner": "truth-verify-loop"},
        "environment": "PUBLIC_SYNTHETIC_CI",
        "policy": {
            "engine": "harness.closure.close_claim",
            "policy_version": "source-policy-default-v1",
            "closure_schema": closure["schema"],
            "closure_engine_blob": CLOSURE_ENGINE_BLOB,
            "semantic_verifier_schema_blob": SEMANTIC_VERIFIER_SCHEMA_BLOB,
            "source_policy_digest": canonical_sha256(raw_policy),
        },
        "subject": {
            "claim_id": claim.claim_id,
            "claim_digest": canonical_sha256(raw_claim),
            "source_content_digest": next(iter(source_digests)),
            "evidence_record_digest": canonical_sha256(raw_evidence[0]),
            "source_count": len(raw_evidence),
            "source_freshness": "CURRENT" if not closure["stale_evidence_ids"] else "STALE",
        },
        "verdict": {
            "state": closure["state"],
            "closed": closure["closed"],
            "as_of": closure["as_of"],
            "expires_at": closure["expires_at"],
            "closure_digest": canonical_sha256(closure),
            "evidence_ceiling": "DOMAIN_VERDICT",
            "accepted_evidence_count": len(closure["accepted_evidence_ids"]),
            "supporting_evidence_count": len(closure["supporting_evidence_ids"]),
            "refuting_evidence_count": len(closure["refuting_evidence_ids"]),
        },
        "disclosure": {
            "class": "PUBLIC_SYNTHETIC",
            "raw_source_included": False,
            "raw_evidence_included": False,
            "credentials_included": False,
            "internal_reasoning_included": False,
            "private_locator_included": False,
        },
        "cleanup": {
            "temporary_files_removed": True,
            "external_credentials_required": False,
        },
        "evidence_boundary": {
            "other_domain_authorities": "NOT_EXERCISED",
            "private_source_access": "NOT_EXERCISED",
            "production_deployment": "NOT_EXERCISED",
            "user_outcome": "ABSENT",
            "paid_outcome": "ABSENT",
            "merge_release": "NOT_AUTHORIZED",
        },
    }


def validate_kaw_domain_receipt(
    receipt: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> str:
    """Validate bounded shape, disclosure safety, and optional exact rebuild equality."""

    required = {
        "schema", "lane", "receipt_id", "authority", "environment", "policy",
        "subject", "verdict", "disclosure", "cleanup", "evidence_boundary",
    }
    _require(set(receipt) == required, "receipt keys mismatch")
    _require(receipt["schema"] == RECEIPT_SCHEMA, "receipt schema mismatch")
    _require(receipt["lane"] == RECEIPT_LANE, "receipt lane mismatch")
    _require(receipt["receipt_id"] == RECEIPT_ID, "receipt id mismatch")
    _require(
        receipt["authority"] == {"kind": "DOMAIN_REPOSITORY", "owner": "truth-verify-loop"},
        "authority mismatch",
    )
    _require(receipt["environment"] == "PUBLIC_SYNTHETIC_CI", "environment widened")

    policy = _mapping(receipt["policy"], "policy")
    _require(policy.get("engine") == "harness.closure.close_claim", "engine mismatch")
    _require(policy.get("closure_engine_blob") == CLOSURE_ENGINE_BLOB, "engine blob drift")
    _require(
        policy.get("semantic_verifier_schema_blob") == SEMANTIC_VERIFIER_SCHEMA_BLOB,
        "semantic schema blob drift",
    )
    for key in ("source_policy_digest",):
        _require_sha256(policy.get(key), key)

    subject = _mapping(receipt["subject"], "subject")
    _require(subject.get("claim_id") == "synthetic-sdk-release", "claim mismatch")
    for key in ("claim_digest", "source_content_digest", "evidence_record_digest"):
        _require_sha256(subject.get(key), key)
    _require(subject.get("source_count") == 1, "source denominator changed")
    _require(subject.get("source_freshness") == "CURRENT", "source freshness changed")

    verdict = _mapping(receipt["verdict"], "verdict")
    _require(verdict.get("state") in ALLOWED_VERDICTS, "unknown verdict")
    _require(verdict.get("evidence_ceiling") == "DOMAIN_VERDICT", "evidence ceiling widened")
    _require_sha256(verdict.get("closure_digest"), "closure_digest")

    disclosure = _mapping(receipt["disclosure"], "disclosure")
    _require(disclosure.get("class") == "PUBLIC_SYNTHETIC", "disclosure class widened")
    _require(
        all(value is False for key, value in disclosure.items() if key != "class"),
        "forbidden disclosure",
    )
    _require(
        receipt["cleanup"] == {
            "temporary_files_removed": True,
            "external_credentials_required": False,
        },
        "cleanup mismatch",
    )
    _require(
        receipt["evidence_boundary"] == {
            "other_domain_authorities": "NOT_EXERCISED",
            "private_source_access": "NOT_EXERCISED",
            "production_deployment": "NOT_EXERCISED",
            "user_outcome": "ABSENT",
            "paid_outcome": "ABSENT",
            "merge_release": "NOT_AUTHORIZED",
        },
        "evidence boundary widened",
    )

    for text in _walk_strings(receipt):
        lowered = text.lower()
        _require(not any(marker in lowered for marker in SECRET_MARKERS), "secret-like material")
        _require("http://" not in lowered and "https://" not in lowered, "raw locator")
        _require("@" not in text, "email-like material")

    if expected is not None:
        _require(dict(receipt) == dict(expected), "receipt differs from deterministic rebuild")
    return canonical_sha256(receipt)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise KawReceiptError(message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _require_sha256(value: Any, label: str) -> None:
    _require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None, f"{label} invalid")


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_strings(child)
