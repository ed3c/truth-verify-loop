"""Dual-Agent evidence bundle contract.

The executing system is never trusted as the closure authority. This module validates
identity, denominator and redaction boundaries only. It deliberately reuses the
repository's existing ``tvl.evidence-closure.v1`` vocabulary and cannot produce a
closed claim by itself.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from harness.model import CLOSURE_STATES, ContractError, canonical_json, parse_timestamp, sha256_text

BUNDLE_SCHEMA = "tvl.dual-agent-evidence-bundle.v1"
CLOSURE_SCHEMA = "tvl.evidence-closure.v1"

REQUIRED_FAMILIES = (
    "SOURCE",
    "BINDING",
    "DELIVERY",
    "WORKFLOW",
    "PROVIDER_RUNTIME",
    "ROUTE_OBSERVATION",
    "EFFECT",
    "ARTIFACT",
    "INBOX",
    "USER_RESULT",
    "CLEANUP",
    "HUMAN",
    "RELEASE",
)

LANES = {
    "LOCAL",
    "CLOUD",
    "API",
    "BROWSER",
    "PROVIDER",
    "USER",
    "HUMAN",
    "RELEASE",
    "CROSS_LANE",
}

EVIDENCE_CLASSES = {
    "DETERMINISTIC_FIXTURE",
    "PUBLIC_READBACK",
    "LIVE_READBACK",
    "HUMAN_ATTESTATION",
    "RELEASE_RECORD",
}

H40 = re.compile(r"^[0-9a-f]{40}$")
H64 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,191}$")
SENSITIVE_KEY = re.compile(
    r"(password|cookie|raw[_-]?secret|secret[_-]?value|token[_-]?value|credential[_-]?value|"
    r"browser[_-]?profile|storage[_-]?state|session[_-]?bytes|private[_-]?reasoning|chain[_-]?of[_-]?thought)",
    re.IGNORECASE,
)


class DualAgentEvidenceError(ContractError):
    """Raised when a Dual-Agent evidence bundle violates the independent contract."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def _refuse(code: str, detail: str = "") -> None:
    raise DualAgentEvidenceError(code, detail)


def _text(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _refuse(code)
    return value.strip()


def _safe_id(value: Any, *, code: str) -> str:
    text = _text(value, code=code)
    if not SAFE_ID.fullmatch(text):
        _refuse(code, text)
    return text


def _h64(value: Any, *, code: str) -> str:
    text = _text(value, code=code)
    if not H64.fullmatch(text):
        _refuse(code, text)
    return text


def _scan_sensitive(value: Any, *, path: str = "$") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _scan_sensitive(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if SENSITIVE_KEY.search(str(key)):
                _refuse("SECRET_OR_PRIVATE_REASONING", f"{path}.{key}")
            _scan_sensitive(item, path=f"{path}.{key}")


def validate_producer(subject: Mapping[str, Any]) -> None:
    if not isinstance(subject, Mapping):
        _refuse("PRODUCER_SUBJECT_INVALID")
    repository = _text(subject.get("repository"), code="PRODUCER_SUBJECT_INVALID")
    if not REPOSITORY.fullmatch(repository):
        _refuse("PRODUCER_SUBJECT_INVALID", repository)
    commit = _text(subject.get("commit"), code="PRODUCER_SUBJECT_INVALID")
    tree = _text(subject.get("tree"), code="PRODUCER_SUBJECT_INVALID")
    if not H40.fullmatch(commit) or not H40.fullmatch(tree):
        _refuse("MUTABLE_PRODUCER_SUBJECT")
    _safe_id(subject.get("schema"), code="PRODUCER_SUBJECT_INVALID")
    _text(subject.get("version"), code="PRODUCER_SUBJECT_INVALID")
    _h64(subject.get("digest"), code="PRODUCER_SUBJECT_INVALID")


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    run_id: str,
    job_id: str,
    tenant_scope: str,
) -> None:
    if not isinstance(receipt, Mapping):
        _refuse("RECEIPT_INVALID")
    _safe_id(receipt.get("receipt_id"), code="RECEIPT_ID_INVALID")
    family = _text(receipt.get("family"), code="RECEIPT_FAMILY_INVALID")
    if family not in REQUIRED_FAMILIES:
        _refuse("RECEIPT_FAMILY_INVALID", family)
    lane = _text(receipt.get("lane"), code="RECEIPT_LANE_INVALID")
    if lane not in LANES:
        _refuse("RECEIPT_LANE_INVALID", lane)
    if receipt.get("run_id") != run_id or receipt.get("job_id") != job_id or receipt.get("tenant_scope") != tenant_scope:
        _refuse("CROSS_RUN_OR_TENANT_RECEIPT")
    _safe_id(receipt.get("attempt_id"), code="ATTEMPT_ID_INVALID")
    sequence = receipt.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        _refuse("RECEIPT_SEQUENCE_INVALID")
    _text(receipt.get("state"), code="RECEIPT_STATE_INVALID")
    _h64(receipt.get("payload_digest"), code="RECEIPT_DIGEST_INVALID")
    evidence_class = _text(receipt.get("evidence_class"), code="EVIDENCE_CLASS_INVALID")
    if evidence_class not in EVIDENCE_CLASSES:
        _refuse("EVIDENCE_CLASS_INVALID", evidence_class)
    validate_producer(receipt.get("producer", {}))
    observed_at = receipt.get("observed_at")
    if observed_at is not None:
        try:
            parse_timestamp(observed_at, field_name="observed_at")
        except ContractError as exc:
            _refuse("RECEIPT_TIMESTAMP_INVALID", str(exc))

    payload = receipt.get("payload", {})
    if not isinstance(payload, Mapping):
        _refuse("RECEIPT_PAYLOAD_INVALID")
    if sha256_text(canonical_json(payload)) != receipt.get("payload_digest"):
        _refuse("RECEIPT_DIGEST_MISMATCH", str(receipt.get("receipt_id", "")))

    if receipt.get("canonical_write") not in {None, "NONE", "OBSERVATION_ONLY", "PROPOSAL_ONLY"}:
        _refuse("VERIFIER_AUTHORITY_WIDENING")
    if evidence_class == "DETERMINISTIC_FIXTURE" and family in {"HUMAN", "RELEASE"}:
        if receipt.get("state") not in {"NOT_EXERCISED", "NOT_PERFORMED", "UNKNOWN"}:
            _refuse("DETERMINISTIC_AS_HUMAN_OR_RELEASE")

    _scan_sensitive(receipt)


def validate_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        _refuse("BUNDLE_INVALID")
    if bundle.get("schema") != BUNDLE_SCHEMA:
        _refuse("BUNDLE_SCHEMA_MISMATCH")
    bundle_id = _safe_id(bundle.get("bundle_id"), code="BUNDLE_ID_INVALID")
    claim_id = _safe_id(bundle.get("claim_id"), code="CLAIM_ID_INVALID")
    run_id = _safe_id(bundle.get("run_id"), code="RUN_ID_INVALID")
    job_id = _safe_id(bundle.get("job_id"), code="JOB_ID_INVALID")
    tenant_scope = _safe_id(bundle.get("tenant_scope"), code="TENANT_SCOPE_INVALID")

    requested_closure = bundle.get("requested_closure_state")
    if requested_closure is not None and requested_closure not in CLOSURE_STATES:
        _refuse("CLOSURE_VOCABULARY_DRIFT", str(requested_closure))

    raw_required = bundle.get("required_families")
    if raw_required != list(REQUIRED_FAMILIES):
        _refuse("DENOMINATOR_CONTRACT_DRIFT")

    receipts = bundle.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        _refuse("RECEIPT_DENOMINATOR_EMPTY")

    ids: set[str] = set()
    sequences: set[int] = set()
    families: set[str] = set()
    attempts: set[str] = set()
    for receipt in receipts:
        validate_receipt(receipt, run_id=run_id, job_id=job_id, tenant_scope=tenant_scope)
        receipt_id = str(receipt["receipt_id"])
        if receipt_id in ids:
            _refuse("DUPLICATE_RECEIPT_ID", receipt_id)
        ids.add(receipt_id)
        sequence = int(receipt["sequence"])
        if sequence in sequences:
            _refuse("DUPLICATE_RECEIPT_SEQUENCE", str(sequence))
        sequences.add(sequence)
        families.add(str(receipt["family"]))
        attempts.add(str(receipt["attempt_id"]))

    if sequences != set(range(len(receipts))):
        _refuse("DROPPED_OR_REORDERED_RECEIPT")
    missing_families = [family for family in REQUIRED_FAMILIES if family not in families]
    if missing_families:
        _refuse("MISSING_RECEIPT_FAMILY", ",".join(missing_families))
    if len(attempts) < 2:
        _refuse("ATTEMPT_DENOMINATOR_TOO_SMALL")

    external = bundle.get("external_states")
    if not isinstance(external, Mapping):
        _refuse("EXTERNAL_STATE_INVALID")
    allowed_external = {
        "task": "NOT_EXERCISED",
        "effect": "NOT_EXERCISED",
        "human": "NOT_EXERCISED",
        "release": "NOT_PERFORMED",
    }
    for key, expected in allowed_external.items():
        if external.get(key) != expected:
            _refuse("VERIFIER_SELF_PROMOTION", key)

    _scan_sensitive(bundle)
    return {
        "bundle_id": bundle_id,
        "claim_id": claim_id,
        "run_id": run_id,
        "job_id": job_id,
        "tenant_scope": tenant_scope,
        "receipt_count": len(receipts),
        "attempt_count": len(attempts),
        "families": sorted(families),
        "bundle_digest": sha256_text(canonical_json(bundle)),
    }


def compile_contract_closure(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the root contract and emit a deliberately non-closed TVL closure.

    DA-TV-C proves bundle shape, exact subjects, complete family coverage and redaction.
    It cannot decide delivery/effect/artifact/user-result correctness on its own.
    """

    summary = validate_bundle(bundle)
    return {
        "schema": CLOSURE_SCHEMA,
        "claim_id": summary["claim_id"],
        "state": "UNVERIFIABLE",
        "closed": False,
        "as_of": None,
        "expires_at": None,
        "gates": {
            "DA0_SCHEMA_AND_SUBJECTS": True,
            "DA1_COMPLETE_RECEIPT_FAMILIES": True,
            "DA2_SECRET_AND_REASONING_EXCLUSION": True,
            "DA3_DELIVERY_WORKFLOW": False,
            "DA4_EFFECT_LINEAGE": False,
            "DA5_SOURCE_ARTIFACT_READBACK": False,
            "DA6_USER_RESULT_CROSS_LANE": False,
            "DA7_NO_UNRESOLVED_CONFLICT": False,
        },
        "missing_requirements": [
            "independent delivery/workflow reconciliation",
            "independent effect/idempotency verification",
            "independent source/artifact byte readback",
            "independent user-result and cross-lane verification",
            "complete verifier-family convergence",
        ],
        "accepted_evidence_ids": [],
        "run": {
            **summary,
            "verification_plane": "truth-verify-loop",
            "authority": "EVIDENCE_ONLY",
            "task_state": "NOT_EXERCISED",
            "effect_state": "NOT_EXERCISED",
            "human_state": "NOT_EXERCISED",
            "release_state": "NOT_PERFORMED",
            "evidence_ceiling": "DETERMINISTIC_DUAL_AGENT_BUNDLE_CONTRACT_ONLY",
        },
    }


def mutated_copy(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Test helper that preserves production code's immutable-input posture."""

    return deepcopy(dict(bundle))
