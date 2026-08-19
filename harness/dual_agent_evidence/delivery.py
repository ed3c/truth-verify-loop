"""Independent delivery/workflow/inbox reconciliation for Dual-Agent evidence.

This verifier consumes evidence only. It never acknowledges transport, advances a
workflow, writes task state, or promotes user/release state.
"""

from __future__ import annotations

from typing import Any, Mapping

from harness.model import canonical_json, sha256_text

from .contract import DualAgentEvidenceError, validate_bundle

H64_LEN = 64
DELIVERY_OUTCOMES = {"ACKED", "FAILED", "TIMEOUT", "CONNECTION_LOST", "DUPLICATE"}


def _refuse(code: str, detail: str = "") -> None:
    raise DualAgentEvidenceError(code, detail)


def _receipt_payload(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = receipt.get("payload")
    if not isinstance(payload, Mapping):
        _refuse("DLV_PAYLOAD_INVALID")
    return payload


def _h64(value: Any, code: str) -> str:
    if not isinstance(value, str) or len(value) != H64_LEN or any(ch not in "0123456789abcdef" for ch in value):
        _refuse(code)
    return value


def verify_delivery_workflow(bundle: Mapping[str, Any]) -> dict[str, Any]:
    summary = validate_bundle(bundle)
    receipts = list(bundle["receipts"])
    deliveries = sorted((item for item in receipts if item["family"] == "DELIVERY"), key=lambda item: item["sequence"])
    workflow = [item for item in receipts if item["family"] == "WORKFLOW"]
    inbox = [item for item in receipts if item["family"] == "INBOX"]

    if len(deliveries) < 2:
        _refuse("DELIVERY_DENOMINATOR_INCOMPLETE")
    if len(workflow) != 1:
        _refuse("WORKFLOW_RECEIPT_CARDINALITY")
    if len(inbox) != 1:
        _refuse("INBOX_RECEIPT_CARDINALITY")

    request_digest: str | None = None
    packet_id: str | None = None
    delivery_ids: set[str] = set()
    attempt_ids: list[str] = []
    for item in deliveries:
        payload = _receipt_payload(item)
        if payload.get("attempt_id") != item.get("attempt_id"):
            _refuse("COPIED_RECEIPT_ATTEMPT_MISMATCH", str(item.get("receipt_id")))
        current_packet = payload.get("packet_id")
        current_delivery = payload.get("delivery_id")
        if not isinstance(current_packet, str) or not current_packet:
            _refuse("DELIVERY_PACKET_ID_INVALID")
        if not isinstance(current_delivery, str) or not current_delivery:
            _refuse("DELIVERY_ID_INVALID")
        if current_delivery in delivery_ids:
            _refuse("DUPLICATE_DELIVERY_ID")
        delivery_ids.add(current_delivery)
        current_digest = _h64(payload.get("request_digest"), "DELIVERY_REQUEST_DIGEST_INVALID")
        if packet_id is None:
            packet_id = current_packet
            request_digest = current_digest
        elif current_packet != packet_id or current_digest != request_digest:
            _refuse("DELIVERY_LOGICAL_IDENTITY_DRIFT")
        if payload.get("outcome") not in DELIVERY_OUTCOMES:
            _refuse("DELIVERY_OUTCOME_INVALID")
        if not isinstance(payload.get("transport_ack"), bool):
            _refuse("TRANSPORT_ACK_INVALID")
        if payload.get("task_state", "NOT_EXERCISED") not in {"NOT_EXERCISED", "UNKNOWN"}:
            _refuse("ACK_AS_TASK_SUCCESS")
        duplicate_of = payload.get("duplicate_of")
        if duplicate_of is not None and duplicate_of not in delivery_ids:
            _refuse("DUPLICATE_LINEAGE_INVALID")
        attempt_ids.append(str(item["attempt_id"]))

    if len(set(attempt_ids)) < 2:
        _refuse("DELIVERY_RETRY_DENOMINATOR_INCOMPLETE")

    workflow_payload = _receipt_payload(workflow[0])
    wf_attempts = workflow_payload.get("attempt_ids")
    if not isinstance(wf_attempts, list) or set(wf_attempts) != set(attempt_ids):
        _refuse("WORKFLOW_DROPPED_ATTEMPT")
    history_digest = _h64(workflow_payload.get("history_digest"), "WORKFLOW_HISTORY_DIGEST_INVALID")
    replay_digest = _h64(workflow_payload.get("replay_digest"), "WORKFLOW_REPLAY_DIGEST_INVALID")
    if history_digest != replay_digest:
        _refuse("WORKFLOW_REPLAY_DIGEST_MISMATCH")
    if workflow_payload.get("transport_ack_is_task_success") is True:
        _refuse("ACK_AS_TASK_SUCCESS")

    inbox_payload = _receipt_payload(inbox[0])
    inbox_attempts = inbox_payload.get("attempt_ids")
    if not isinstance(inbox_attempts, list) or set(inbox_attempts) != set(attempt_ids):
        _refuse("INBOX_DROPPED_ATTEMPT")
    if inbox_payload.get("reconciled") is not True or inbox_payload.get("restart_readback") is not True:
        _refuse("INBOX_RECONCILIATION_UNPROVEN")
    result_digest = _h64(inbox_payload.get("result_digest"), "INBOX_RESULT_DIGEST_INVALID")

    finding = {
        "family": "DA-TV-DLV",
        "gate": True,
        "bundle_digest": summary["bundle_digest"],
        "packet_id": packet_id,
        "request_digest": request_digest,
        "delivery_ids": sorted(delivery_ids),
        "attempt_ids": sorted(set(attempt_ids)),
        "workflow_history_digest": history_digest,
        "inbox_result_digest": result_digest,
        "receipt_ids": [item["receipt_id"] for item in deliveries + workflow + inbox],
        "authority": "EVIDENCE_ONLY",
        "task_state": "NOT_EXERCISED",
        "user_result_state": "NOT_EXERCISED",
        "release_state": "NOT_PERFORMED",
        "evidence_ceiling": "DETERMINISTIC_DELIVERY_WORKFLOW_VERIFICATION_ONLY",
    }
    finding["finding_digest"] = sha256_text(canonical_json(finding))
    return finding
