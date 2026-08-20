"""Independent effect/idempotency lineage verification.

The verifier reasons over receipts only. It cannot execute or commit an external effect.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from harness.model import canonical_json, sha256_text

from .contract import DualAgentEvidenceError, validate_bundle

TERMINAL_RESOLVED = {"COMMITTED", "REFUSED", "FAILED", "COMPENSATED", "COMPENSATION_FAILED"}
UNKNOWN_PROVIDER_OUTCOMES = {"TIMEOUT", "CONNECTION_LOST", "UNKNOWN"}


def _refuse(code: str, detail: str = "") -> None:
    raise DualAgentEvidenceError(code, detail)


def _h64(value: Any, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        _refuse(code)
    return value


def _payload(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    value = receipt.get("payload")
    if not isinstance(value, Mapping):
        _refuse("EFFECT_PAYLOAD_INVALID")
    return value


def verify_effect_lineage(bundle: Mapping[str, Any]) -> dict[str, Any]:
    summary = validate_bundle(bundle)
    effects = sorted((item for item in bundle["receipts"] if item["family"] == "EFFECT"), key=lambda item: item["sequence"])
    if not effects:
        _refuse("EFFECT_DENOMINATOR_EMPTY")

    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for receipt in effects:
        payload = _payload(receipt)
        if payload.get("attempt_id") != receipt.get("attempt_id"):
            _refuse("COPIED_EFFECT_RECEIPT_ATTEMPT_MISMATCH", str(receipt.get("receipt_id")))
        effect_id = payload.get("effect_id")
        if not isinstance(effect_id, str) or not effect_id:
            _refuse("EFFECT_ID_INVALID")
        groups[effect_id].append(receipt)

    committed_effects: set[str] = set()
    group_summaries: list[dict[str, Any]] = []
    for effect_id, group in sorted(groups.items()):
        idempotency_key: str | None = None
        request_digest: str | None = None
        attempts: list[str] = []
        commits = 0
        has_unknown = False
        final_state = ""
        compensation_parent: str | None = None
        for receipt in group:
            payload = _payload(receipt)
            idem = payload.get("idempotency_key")
            if not isinstance(idem, str) or not idem:
                _refuse("IDEMPOTENCY_KEY_INVALID", effect_id)
            digest = _h64(payload.get("normalized_request_digest"), "EFFECT_REQUEST_DIGEST_INVALID")
            if idempotency_key is None:
                idempotency_key = idem
                request_digest = digest
            elif idem != idempotency_key or digest != request_digest:
                _refuse("IDEMPOTENCY_COLLISION", effect_id)

            attempt_id = str(receipt["attempt_id"])
            attempts.append(attempt_id)
            declared = payload.get("attempt_denominator")
            if not isinstance(declared, list) or not all(isinstance(item, str) and item for item in declared):
                _refuse("EFFECT_ATTEMPT_DENOMINATOR_INVALID", effect_id)

            provider_outcome = payload.get("provider_outcome")
            result_state = payload.get("result_state")
            if not isinstance(result_state, str) or not result_state:
                _refuse("EFFECT_RESULT_STATE_INVALID", effect_id)
            final_state = result_state
            if provider_outcome in UNKNOWN_PROVIDER_OUTCOMES and result_state == "COMMITTED":
                _refuse("TIMEOUT_OR_UNKNOWN_AS_COMMIT", effect_id)
            if payload.get("provider_self_commit") is True:
                _refuse("PROVIDER_SELF_COMMIT", effect_id)
            if result_state == "COMMITTED":
                commits += 1
                if payload.get("readback_verified") is not True:
                    _refuse("EFFECT_READBACK_REQUIRED", effect_id)
                _h64(payload.get("readback_digest"), "EFFECT_READBACK_DIGEST_INVALID")
            if result_state in {"UNKNOWN", "RESULT_UNKNOWN"}:
                has_unknown = True

            parent = payload.get("compensation_parent_effect_id")
            if parent is not None:
                if not isinstance(parent, str) or not parent or parent == effect_id:
                    _refuse("COMPENSATION_LINEAGE_INVALID", effect_id)
                if compensation_parent is None:
                    compensation_parent = parent
                elif compensation_parent != parent:
                    _refuse("COMPENSATION_LINEAGE_INVALID", effect_id)
                if payload.get("erases_parent_history") is True:
                    _refuse("COMPENSATION_ERASES_PARENT_HISTORY", effect_id)

        if commits > 1:
            _refuse("MULTIPLE_ACCEPTED_COMMITS", effect_id)
        actual_attempts = sorted(set(attempts))
        for receipt in group:
            declared = sorted(set(_payload(receipt)["attempt_denominator"]))
            if declared != actual_attempts:
                _refuse("EFFECT_ATTEMPT_DENOMINATOR_MISMATCH", effect_id)
        if has_unknown and final_state not in TERMINAL_RESOLVED:
            _refuse("UNRESOLVED_EFFECT", effect_id)
        if commits == 1:
            committed_effects.add(effect_id)
        group_summaries.append(
            {
                "effect_id": effect_id,
                "idempotency_key": idempotency_key,
                "request_digest": request_digest,
                "attempt_ids": actual_attempts,
                "accepted_commits": commits,
                "final_state": final_state,
                "compensation_parent_effect_id": compensation_parent,
            }
        )

    for group in group_summaries:
        parent = group["compensation_parent_effect_id"]
        if parent is not None and parent not in committed_effects:
            _refuse("COMPENSATION_PARENT_NOT_COMMITTED", str(parent))

    finding = {
        "family": "DA-TV-EF",
        "gate": True,
        "bundle_digest": summary["bundle_digest"],
        "effects": group_summaries,
        "receipt_ids": [item["receipt_id"] for item in effects],
        "authority": "EVIDENCE_ONLY",
        "external_effect_state": "NOT_EXERCISED",
        "human_state": "NOT_EXERCISED",
        "release_state": "NOT_PERFORMED",
        "evidence_ceiling": "DETERMINISTIC_EFFECT_LINEAGE_VERIFICATION_ONLY",
    }
    finding["finding_digest"] = sha256_text(canonical_json(finding))
    return finding
