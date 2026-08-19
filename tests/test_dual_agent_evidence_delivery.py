from __future__ import annotations

from copy import deepcopy
import unittest

from harness.dual_agent_evidence.contract import DualAgentEvidenceError
from harness.dual_agent_evidence.delivery import verify_delivery_workflow
from harness.model import canonical_json, sha256_text
from tests.test_dual_agent_evidence_contract import fixed_bundle


def _set_payload(receipt: dict, payload: dict) -> None:
    receipt["payload"] = payload
    receipt["payload_digest"] = sha256_text(canonical_json(payload))


def fixed_delivery_bundle() -> dict:
    bundle = fixed_bundle()
    delivery = next(item for item in bundle["receipts"] if item["family"] == "DELIVERY")
    _set_payload(
        delivery,
        {
            "attempt_id": "attempt-0",
            "packet_id": "packet-dual-agent-001",
            "delivery_id": "delivery-001",
            "request_digest": "1" * 64,
            "outcome": "ACKED",
            "transport_ack": True,
            "task_state": "NOT_EXERCISED",
            "duplicate_of": None,
        },
    )

    retry = deepcopy(delivery)
    retry["receipt_id"] = "receipt-delivery-retry"
    retry["sequence"] = len(bundle["receipts"])
    retry["attempt_id"] = "attempt-1"
    _set_payload(
        retry,
        {
            "attempt_id": "attempt-1",
            "packet_id": "packet-dual-agent-001",
            "delivery_id": "delivery-002",
            "request_digest": "1" * 64,
            "outcome": "DUPLICATE",
            "transport_ack": True,
            "task_state": "NOT_EXERCISED",
            "duplicate_of": "delivery-001",
        },
    )
    bundle["receipts"].append(retry)

    workflow = next(item for item in bundle["receipts"] if item["family"] == "WORKFLOW")
    _set_payload(
        workflow,
        {
            "attempt_ids": ["attempt-0", "attempt-1"],
            "history_digest": "2" * 64,
            "replay_digest": "2" * 64,
            "terminal_state": "COMPLETED",
            "transport_ack_is_task_success": False,
        },
    )
    inbox = next(item for item in bundle["receipts"] if item["family"] == "INBOX")
    _set_payload(
        inbox,
        {
            "attempt_ids": ["attempt-0", "attempt-1"],
            "result_digest": "3" * 64,
            "reconciled": True,
            "restart_readback": True,
        },
    )
    return bundle


class DeliveryWorkflowVerificationTest(unittest.TestCase):
    def assert_code(self, code: str, bundle: dict) -> None:
        with self.assertRaises(DualAgentEvidenceError) as caught:
            verify_delivery_workflow(bundle)
        self.assertEqual(caught.exception.code, code)

    def test_complete_retry_replay_and_restart_denominator(self) -> None:
        finding = verify_delivery_workflow(fixed_delivery_bundle())
        self.assertTrue(finding["gate"])
        self.assertEqual(finding["attempt_ids"], ["attempt-0", "attempt-1"])
        self.assertEqual(finding["authority"], "EVIDENCE_ONLY")
        self.assertEqual(finding["user_result_state"], "NOT_EXERCISED")

    def test_transport_ack_cannot_be_task_success(self) -> None:
        bundle = fixed_delivery_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "DELIVERY")
        payload = dict(receipt["payload"])
        payload["task_state"] = "PASS"
        _set_payload(receipt, payload)
        self.assert_code("ACK_AS_TASK_SUCCESS", bundle)

    def test_retry_omission_is_visible(self) -> None:
        bundle = fixed_delivery_bundle()
        bundle["receipts"].pop()
        self.assert_code("DELIVERY_DENOMINATOR_INCOMPLETE", bundle)

    def test_copied_receipt_under_other_attempt_is_refused(self) -> None:
        bundle = fixed_delivery_bundle()
        retry = bundle["receipts"][-1]
        retry["attempt_id"] = "attempt-2"
        self.assert_code("COPIED_RECEIPT_ATTEMPT_MISMATCH", bundle)

    def test_logical_packet_identity_drift_is_refused(self) -> None:
        bundle = fixed_delivery_bundle()
        retry = bundle["receipts"][-1]
        payload = dict(retry["payload"])
        payload["request_digest"] = "4" * 64
        _set_payload(retry, payload)
        self.assert_code("DELIVERY_LOGICAL_IDENTITY_DRIFT", bundle)

    def test_workflow_cannot_drop_failed_or_retry_attempt(self) -> None:
        bundle = fixed_delivery_bundle()
        workflow = next(item for item in bundle["receipts"] if item["family"] == "WORKFLOW")
        payload = dict(workflow["payload"])
        payload["attempt_ids"] = ["attempt-0"]
        _set_payload(workflow, payload)
        self.assert_code("WORKFLOW_DROPPED_ATTEMPT", bundle)

    def test_replay_digest_mismatch_is_refused(self) -> None:
        bundle = fixed_delivery_bundle()
        workflow = next(item for item in bundle["receipts"] if item["family"] == "WORKFLOW")
        payload = dict(workflow["payload"])
        payload["replay_digest"] = "5" * 64
        _set_payload(workflow, payload)
        self.assert_code("WORKFLOW_REPLAY_DIGEST_MISMATCH", bundle)

    def test_inbox_cannot_drop_attempt(self) -> None:
        bundle = fixed_delivery_bundle()
        inbox = next(item for item in bundle["receipts"] if item["family"] == "INBOX")
        payload = dict(inbox["payload"])
        payload["attempt_ids"] = ["attempt-1"]
        _set_payload(inbox, payload)
        self.assert_code("INBOX_DROPPED_ATTEMPT", bundle)

    def test_restart_reconciliation_must_be_read_back(self) -> None:
        bundle = fixed_delivery_bundle()
        inbox = next(item for item in bundle["receipts"] if item["family"] == "INBOX")
        payload = dict(inbox["payload"])
        payload["restart_readback"] = False
        _set_payload(inbox, payload)
        self.assert_code("INBOX_RECONCILIATION_UNPROVEN", bundle)

    def test_invalid_duplicate_lineage_is_refused(self) -> None:
        bundle = fixed_delivery_bundle()
        retry = bundle["receipts"][-1]
        payload = dict(retry["payload"])
        payload["duplicate_of"] = "delivery-never-observed"
        _set_payload(retry, payload)
        self.assert_code("DUPLICATE_LINEAGE_INVALID", bundle)


if __name__ == "__main__":
    unittest.main()
