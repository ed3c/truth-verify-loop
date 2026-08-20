"""Independent user-result and cross-lane verification.

Backend completion, provider observations and route receipts are separate facts. This
module can verify consistency of deterministic evidence, but cannot manufacture a live
user observation, Human approval or release state.
"""

from __future__ import annotations

from typing import Any, Mapping

from harness.model import canonical_json, sha256_text

from .contract import DualAgentEvidenceError, validate_bundle


def _refuse(code: str, detail: str = "") -> None:
    raise DualAgentEvidenceError(code, detail)


def _h64(value: Any, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        _refuse(code)
    return value


def _single(bundle: Mapping[str, Any], family: str) -> Mapping[str, Any]:
    receipts = [item for item in bundle["receipts"] if item["family"] == family]
    if len(receipts) != 1:
        _refuse(f"{family}_RECEIPT_CARDINALITY")
    return receipts[0]


def _payload(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    value = receipt.get("payload")
    if not isinstance(value, Mapping):
        _refuse("USER_RESULT_PAYLOAD_INVALID")
    return value


def verify_user_result(bundle: Mapping[str, Any]) -> dict[str, Any]:
    summary = validate_bundle(bundle)
    provider = _single(bundle, "PROVIDER_RUNTIME")
    route = _single(bundle, "ROUTE_OBSERVATION")
    user = _single(bundle, "USER_RESULT")
    cleanup = _single(bundle, "CLEANUP")
    human = _single(bundle, "HUMAN")
    release = _single(bundle, "RELEASE")

    provider_payload = _payload(provider)
    route_payload = _payload(route)
    user_payload = _payload(user)
    cleanup_payload = _payload(cleanup)
    human_payload = _payload(human)
    release_payload = _payload(release)

    provider_digest = _h64(provider_payload.get("provider_result_digest"), "PROVIDER_RESULT_DIGEST_INVALID")
    if provider_payload.get("user_result_claimed") is True:
        _refuse("PROVIDER_AS_USER_RESULT")
    if provider_payload.get("task_state", "NOT_EXERCISED") not in {"NOT_EXERCISED", "UNKNOWN"}:
        _refuse("PROVIDER_AS_TASK_SUCCESS")

    route_kind = route_payload.get("route_kind")
    evidence_lane = route_payload.get("evidence_lane")
    if route_kind not in {"API", "BROWSER"} or evidence_lane != route_kind or route.get("lane") != route_kind:
        _refuse("ROUTE_EVIDENCE_SUBSTITUTION")
    route_observation_digest = _h64(route_payload.get("observation_digest"), "ROUTE_OBSERVATION_DIGEST_INVALID")
    route_result_digest = _h64(route_payload.get("result_digest"), "ROUTE_RESULT_DIGEST_INVALID")
    if route_payload.get("provider_result_digest") != provider_digest:
        _refuse("PROVIDER_ROUTE_DISAGREEMENT")
    if route_payload.get("user_result_claimed") is True:
        _refuse("ROUTE_AS_USER_RESULT")

    expected_route = user_payload.get("expected_route")
    if expected_route != route_kind:
        _refuse("USER_ROUTE_SUBJECT_MISMATCH")
    if user_payload.get("evidence_lane") != "USER" or user.get("lane") != "USER":
        _refuse("NON_USER_EVIDENCE_AS_USER_RESULT")
    if user_payload.get("route_observation_digest") != route_observation_digest:
        _refuse("USER_ROUTE_OBSERVATION_MISMATCH")
    user_result_digest = _h64(user_payload.get("result_digest"), "USER_RESULT_DIGEST_INVALID")
    if user_result_digest != route_result_digest:
        _refuse("USER_RESULT_ROUTE_DISAGREEMENT")
    if user_payload.get("user_observed") is not True:
        if user_payload.get("backend_completion") in {"COMPLETED", "PASS", "SUCCESS"}:
            _refuse("BACKEND_COMPLETE_AS_USER_SUCCESS")
        _refuse("USER_RESULT_NOT_OBSERVED")

    if cleanup_payload.get("independent_receipt") is not True:
        _refuse("CLEANUP_INFERRED_FROM_SUCCESS")
    if cleanup_payload.get("related_result_digest") != user_result_digest:
        _refuse("CLEANUP_RESULT_SUBJECT_MISMATCH")
    cleanup_state = cleanup_payload.get("cleanup_state")
    residue = cleanup_payload.get("residue")
    if cleanup_state != "CLEAN" or not isinstance(residue, list) or residue:
        _refuse("CLEANUP_NOT_CLOSED")

    if human.get("state") not in {"NOT_EXERCISED", "UNKNOWN"} or human_payload.get("inferred_from_deterministic") is True:
        _refuse("HUMAN_INFERRED_FROM_DETERMINISTIC")
    if release.get("state") != "NOT_PERFORMED" or release_payload.get("inferred_from_deterministic") is True:
        _refuse("RELEASE_INFERRED_FROM_DETERMINISTIC")

    finding = {
        "family": "DA-TV-USER",
        "gate": True,
        "bundle_digest": summary["bundle_digest"],
        "route_kind": route_kind,
        "provider_result_digest": provider_digest,
        "route_observation_digest": route_observation_digest,
        "user_result_digest": user_result_digest,
        "cleanup_state": cleanup_state,
        "receipt_ids": [
            provider["receipt_id"],
            route["receipt_id"],
            user["receipt_id"],
            cleanup["receipt_id"],
            human["receipt_id"],
            release["receipt_id"],
        ],
        "authority": "EVIDENCE_ONLY",
        "live_user_result_state": "NOT_EXERCISED",
        "human_state": "NOT_EXERCISED",
        "release_state": "NOT_PERFORMED",
        "evidence_ceiling": "DETERMINISTIC_USER_RESULT_CROSS_LANE_VERIFICATION_ONLY",
    }
    finding["finding_digest"] = sha256_text(canonical_json(finding))
    return finding
