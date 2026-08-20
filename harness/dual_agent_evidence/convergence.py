"""Convergence for the independent Dual-Agent verifier families.

All technical verifier families may agree while the business/semantic claim remains
UNVERIFIABLE. This module intentionally stops before semantic/Human/release authority.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from harness.model import canonical_json, sha256_text

from .artifact import verify_source_artifacts
from .contract import CLOSURE_SCHEMA, REQUIRED_FAMILIES, DualAgentEvidenceError, validate_bundle
from .delivery import verify_delivery_workflow
from .effect import verify_effect_lineage
from .user_result import verify_user_result

REQUIRED_VERIFIERS = (
    "DA-TV-DLV",
    "DA-TV-EF",
    "DA-TV-ART",
    "DA-TV-USER",
)

EXPECTED_CEILINGS = {
    "DA-TV-DLV": "DETERMINISTIC_DELIVERY_WORKFLOW_VERIFICATION_ONLY",
    "DA-TV-EF": "DETERMINISTIC_EFFECT_LINEAGE_VERIFICATION_ONLY",
    "DA-TV-ART": "DETERMINISTIC_SOURCE_ARTIFACT_READBACK_ONLY",
    "DA-TV-USER": "DETERMINISTIC_USER_RESULT_CROSS_LANE_VERIFICATION_ONLY",
}


def _refuse(code: str, detail: str = "") -> None:
    raise DualAgentEvidenceError(code, detail)


def _h64(value: Any, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        _refuse(code)
    return value


def _binding_payload(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    bindings = [item for item in bundle["receipts"] if item["family"] == "BINDING"]
    if len(bindings) != 1:
        _refuse("BINDING_RECEIPT_CARDINALITY")
    payload = bindings[0].get("payload")
    if not isinstance(payload, Mapping):
        _refuse("BINDING_PAYLOAD_INVALID")
    return payload


def verify_cross_family_bindings(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the exact producer/runtime/policy subjects named by the binding receipt."""

    payload = _binding_payload(bundle)
    expected = payload.get("expected_producer_digests")
    if not isinstance(expected, Mapping):
        _refuse("EXPECTED_PRODUCER_BINDINGS_MISSING")
    required = {family for family in REQUIRED_FAMILIES if family != "BINDING"}
    if set(expected) != required:
        _refuse("EXPECTED_PRODUCER_BINDINGS_INCOMPLETE")

    actual: dict[str, set[str]] = {family: set() for family in required}
    for receipt in bundle["receipts"]:
        family = str(receipt["family"])
        if family == "BINDING":
            continue
        producer = receipt.get("producer")
        if not isinstance(producer, Mapping):
            _refuse("PRODUCER_SUBJECT_INVALID", family)
        digest = _h64(producer.get("digest"), "PRODUCER_SUBJECT_DIGEST_INVALID")
        actual[family].add(digest)

    for family in sorted(required):
        expected_digest = _h64(expected.get(family), "EXPECTED_PRODUCER_DIGEST_INVALID")
        if actual[family] != {expected_digest}:
            _refuse("STALE_OR_CONFLICTED_PRODUCER_BINDING", family)

    runtime = _h64(payload.get("runtime_contract_digest"), "RUNTIME_BINDING_INVALID")
    expected_runtime = _h64(payload.get("expected_runtime_contract_digest"), "RUNTIME_BINDING_INVALID")
    if runtime != expected_runtime:
        _refuse("STALE_RUNTIME_BINDING")
    policy = _h64(payload.get("policy_digest"), "POLICY_BINDING_INVALID")
    expected_policy = _h64(payload.get("expected_policy_digest"), "POLICY_BINDING_INVALID")
    if policy != expected_policy:
        _refuse("STALE_POLICY_BINDING")

    return {
        "producer_digests": {family: next(iter(actual[family])) for family in sorted(actual)},
        "runtime_contract_digest": runtime,
        "policy_digest": policy,
        "binding_digest": sha256_text(canonical_json(dict(payload))),
    }


def _verify_finding_digest(finding: Mapping[str, Any], family: str) -> None:
    claimed = _h64(finding.get("finding_digest"), "VERIFIER_FINDING_DIGEST_INVALID")
    body = dict(finding)
    body.pop("finding_digest", None)
    actual = sha256_text(canonical_json(body))
    if actual != claimed:
        _refuse("VERIFIER_FINDING_DIGEST_MISMATCH", family)


def converge_findings(bundle: Mapping[str, Any], findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary = validate_bundle(bundle)
    binding = verify_cross_family_bindings(bundle)
    if bundle.get("requested_closure_state") not in {None, "UNVERIFIABLE"}:
        _refuse("TECHNICAL_VERIFIER_SELF_CLOSURE", str(bundle.get("requested_closure_state")))

    by_family: dict[str, Mapping[str, Any]] = {}
    for finding in findings:
        if not isinstance(finding, Mapping):
            _refuse("VERIFIER_FINDING_INVALID")
        family = finding.get("family")
        if family not in REQUIRED_VERIFIERS:
            _refuse("UNKNOWN_VERIFIER_FAMILY", str(family))
        if family in by_family:
            _refuse("DUPLICATE_VERIFIER_FAMILY", str(family))
        by_family[str(family)] = finding

    missing = [family for family in REQUIRED_VERIFIERS if family not in by_family]
    if missing:
        _refuse("MISSING_VERIFIER_FAMILY", ",".join(missing))

    for family in REQUIRED_VERIFIERS:
        finding = by_family[family]
        _verify_finding_digest(finding, family)
        if finding.get("gate") is not True:
            _refuse("VERIFIER_FAMILY_FAILED", family)
        if finding.get("bundle_digest") != summary["bundle_digest"]:
            _refuse("VERIFIER_BUNDLE_DRIFT", family)
        if finding.get("authority") != "EVIDENCE_ONLY":
            _refuse("VERIFIER_AUTHORITY_WIDENING", family)
        if finding.get("evidence_ceiling") != EXPECTED_CEILINGS[family]:
            _refuse("VERIFIER_EVIDENCE_CEILING_WIDENING", family)

    if by_family["DA-TV-DLV"].get("task_state") != "NOT_EXERCISED" or by_family["DA-TV-DLV"].get("release_state") != "NOT_PERFORMED":
        _refuse("DELIVERY_VERIFIER_SELF_PROMOTION")
    if by_family["DA-TV-EF"].get("external_effect_state") != "NOT_EXERCISED" or by_family["DA-TV-EF"].get("release_state") != "NOT_PERFORMED":
        _refuse("EFFECT_VERIFIER_SELF_PROMOTION")
    if by_family["DA-TV-ART"].get("semantic_state") != "NOT_EXERCISED" or by_family["DA-TV-ART"].get("release_state") != "NOT_PERFORMED":
        _refuse("ARTIFACT_VERIFIER_SELF_PROMOTION")
    if by_family["DA-TV-USER"].get("live_user_result_state") != "NOT_EXERCISED" or by_family["DA-TV-USER"].get("release_state") != "NOT_PERFORMED":
        _refuse("USER_VERIFIER_SELF_PROMOTION")

    accepted_ids = sorted({str(receipt["receipt_id"]) for receipt in bundle["receipts"]})
    closure = {
        "schema": CLOSURE_SCHEMA,
        "claim_id": summary["claim_id"],
        "state": "UNVERIFIABLE",
        "closed": False,
        "as_of": summary["as_of"],
        "expires_at": None,
        "gates": {
            "DA0_SCHEMA_AND_SUBJECTS": True,
            "DA1_COMPLETE_RECEIPT_FAMILIES": True,
            "DA2_CROSS_FAMILY_BINDINGS": True,
            "DA3_DELIVERY_WORKFLOW": True,
            "DA4_EFFECT_LINEAGE": True,
            "DA5_SOURCE_ARTIFACT_READBACK": True,
            "DA6_USER_RESULT_CROSS_LANE": True,
            "DA7_NO_TECHNICAL_DISAGREEMENT": True,
            "G7_SEMANTIC_REVIEW": False,
            "G8_LIVE_OR_HUMAN_AUTHORITY": False,
        },
        "missing_requirements": [
            "semantic claim-direction verification by the existing Truth Verify Loop semantic plane",
            "live/private evidence when required by the claim",
            "Human/release admission remains external to evidence verification",
        ],
        "accepted_evidence_ids": accepted_ids,
        "authority": {
            "verification_plane": "truth-verify-loop",
            "canonical_write": "NONE",
            "execution": "FORBIDDEN",
            "workflow_write": "FORBIDDEN",
            "effect_write": "FORBIDDEN",
            "human_admission": "EXTERNAL",
            "release": "EXTERNAL",
        },
        "coverage": {
            "technical_verifier_families": list(REQUIRED_VERIFIERS),
            "finding_digests": {family: by_family[family]["finding_digest"] for family in REQUIRED_VERIFIERS},
            "binding_digest": binding["binding_digest"],
        },
        "run": {
            **summary,
            "runtime_contract_digest": binding["runtime_contract_digest"],
            "policy_digest": binding["policy_digest"],
            "technical_matrix": "PASS",
            "live_provider_state": "NOT_EXERCISED",
            "live_network_state": "NOT_EXERCISED",
            "live_user_result_state": "NOT_EXERCISED",
            "human_state": "NOT_EXERCISED",
            "release_state": "NOT_PERFORMED",
            "evidence_ceiling": "COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY",
        },
    }
    closure["run"]["closure_digest"] = sha256_text(canonical_json(closure))
    return closure


def verify_complete_bundle(
    bundle: Mapping[str, Any],
    *,
    source_bytes: bytes,
    artifact_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    findings = [
        verify_delivery_workflow(bundle),
        verify_effect_lineage(bundle),
        verify_source_artifacts(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes),
        verify_user_result(bundle),
    ]
    return converge_findings(bundle, findings)
