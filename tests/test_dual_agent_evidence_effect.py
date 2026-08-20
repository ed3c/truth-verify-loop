from __future__ import annotations

from copy import deepcopy
import unittest

from harness.dual_agent_evidence.contract import DualAgentEvidenceError
from harness.dual_agent_evidence.effect import verify_effect_lineage
from harness.model import canonical_json, sha256_text
from tests.test_dual_agent_evidence_contract import fixed_bundle


def _set_payload(receipt: dict, payload: dict) -> None:
    receipt["payload"] = payload
    receipt["payload_digest"] = sha256_text(canonical_json(payload))


def fixed_effect_bundle() -> dict:
    bundle = fixed_bundle()
    effect = next(item for item in bundle["receipts"] if item["family"] == "EFFECT")
    _set_payload(
        effect,
        {
            "attempt_id": "attempt-0",
            "effect_id": "effect-main-001",
            "idempotency_key": "idem-main-001",
            "normalized_request_digest": "4" * 64,
            "attempt_denominator": ["attempt-0", "attempt-1"],
            "provider_outcome": "CONNECTION_LOST",
            "result_state": "RESULT_UNKNOWN",
            "readback_verified": False,
            "readback_digest": None,
            "provider_self_commit": False,
            "compensation_parent_effect_id": None,
            "erases_parent_history": False,
        },
    )

    resolved = deepcopy(effect)
    resolved["receipt_id"] = "receipt-effect-resolution"
    resolved["sequence"] = len(bundle["receipts"])
    resolved["attempt_id"] = "attempt-1"
    _set_payload(
        resolved,
        {
            "attempt_id": "attempt-1",
            "effect_id": "effect-main-001",
            "idempotency_key": "idem-main-001",
            "normalized_request_digest": "4" * 64,
            "attempt_denominator": ["attempt-0", "attempt-1"],
            "provider_outcome": "SUCCESS",
            "result_state": "COMMITTED",
            "readback_verified": True,
            "readback_digest": "5" * 64,
            "provider_self_commit": False,
            "compensation_parent_effect_id": None,
            "erases_parent_history": False,
        },
    )
    bundle["receipts"].append(resolved)
    return bundle


def _append_compensation(bundle: dict, *, parent: str, erases: bool = False) -> dict:
    source = next(item for item in bundle["receipts"] if item["family"] == "EFFECT")
    compensation = deepcopy(source)
    compensation["receipt_id"] = f"receipt-comp-{len(bundle['receipts'])}"
    compensation["sequence"] = len(bundle["receipts"])
    compensation["attempt_id"] = "attempt-comp-0"
    _set_payload(
        compensation,
        {
            "attempt_id": "attempt-comp-0",
            "effect_id": "effect-comp-001",
            "idempotency_key": "idem-comp-001",
            "normalized_request_digest": "6" * 64,
            "attempt_denominator": ["attempt-comp-0"],
            "provider_outcome": "SUCCESS",
            "result_state": "COMMITTED",
            "readback_verified": True,
            "readback_digest": "7" * 64,
            "provider_self_commit": False,
            "compensation_parent_effect_id": parent,
            "erases_parent_history": erases,
        },
    )
    bundle["receipts"].append(compensation)
    return bundle


class EffectLineageVerificationTest(unittest.TestCase):
    def assert_code(self, code: str, bundle: dict) -> None:
        with self.assertRaises(DualAgentEvidenceError) as caught:
            verify_effect_lineage(bundle)
        self.assertEqual(caught.exception.code, code)

    def test_unknown_then_exact_readback_commit_is_reconciled(self) -> None:
        finding = verify_effect_lineage(fixed_effect_bundle())
        self.assertTrue(finding["gate"])
        self.assertEqual(finding["effects"][0]["accepted_commits"], 1)
        self.assertEqual(finding["external_effect_state"], "NOT_EXERCISED")

    def test_idempotency_collision_is_refused(self) -> None:
        bundle = fixed_effect_bundle()
        receipt = bundle["receipts"][-1]
        payload = dict(receipt["payload"])
        payload["normalized_request_digest"] = "8" * 64
        _set_payload(receipt, payload)
        self.assert_code("IDEMPOTENCY_COLLISION", bundle)

    def test_unresolved_unknown_cannot_close(self) -> None:
        bundle = fixed_effect_bundle()
        bundle["receipts"].pop()
        payload = bundle["receipts"][6]["payload"]
        payload["attempt_denominator"] = ["attempt-0"]
        _set_payload(bundle["receipts"][6], payload)
        self.assert_code("UNRESOLVED_EFFECT", bundle)

    def test_commit_requires_readback(self) -> None:
        bundle = fixed_effect_bundle()
        receipt = bundle["receipts"][-1]
        payload = dict(receipt["payload"])
        payload["readback_verified"] = False
        _set_payload(receipt, payload)
        self.assert_code("EFFECT_READBACK_REQUIRED", bundle)

    def test_timeout_cannot_be_commit(self) -> None:
        bundle = fixed_effect_bundle()
        receipt = bundle["receipts"][-1]
        payload = dict(receipt["payload"])
        payload["provider_outcome"] = "TIMEOUT"
        _set_payload(receipt, payload)
        self.assert_code("TIMEOUT_OR_UNKNOWN_AS_COMMIT", bundle)

    def test_provider_cannot_self_commit(self) -> None:
        bundle = fixed_effect_bundle()
        receipt = bundle["receipts"][-1]
        payload = dict(receipt["payload"])
        payload["provider_self_commit"] = True
        _set_payload(receipt, payload)
        self.assert_code("PROVIDER_SELF_COMMIT", bundle)

    def test_attempt_denominator_cannot_hide_unknown_attempt(self) -> None:
        bundle = fixed_effect_bundle()
        receipt = bundle["receipts"][-1]
        payload = dict(receipt["payload"])
        payload["attempt_denominator"] = ["attempt-1"]
        _set_payload(receipt, payload)
        self.assert_code("EFFECT_ATTEMPT_DENOMINATOR_MISMATCH", bundle)

    def test_copied_effect_receipt_under_other_attempt_is_refused(self) -> None:
        bundle = fixed_effect_bundle()
        bundle["receipts"][-1]["attempt_id"] = "attempt-copied"
        self.assert_code("COPIED_EFFECT_RECEIPT_ATTEMPT_MISMATCH", bundle)

    def test_multiple_accepted_commits_are_refused(self) -> None:
        bundle = fixed_effect_bundle()
        duplicate = deepcopy(bundle["receipts"][-1])
        duplicate["receipt_id"] = "receipt-effect-second-commit"
        duplicate["sequence"] = len(bundle["receipts"])
        duplicate["attempt_id"] = "attempt-2"
        for receipt in [item for item in bundle["receipts"] if item["family"] == "EFFECT"]:
            payload = dict(receipt["payload"])
            payload["attempt_denominator"] = ["attempt-0", "attempt-1", "attempt-2"]
            _set_payload(receipt, payload)
        payload = dict(duplicate["payload"])
        payload["attempt_id"] = "attempt-2"
        payload["attempt_denominator"] = ["attempt-0", "attempt-1", "attempt-2"]
        _set_payload(duplicate, payload)
        bundle["receipts"].append(duplicate)
        self.assert_code("MULTIPLE_ACCEPTED_COMMITS", bundle)

    def test_compensation_requires_committed_parent(self) -> None:
        bundle = _append_compensation(fixed_effect_bundle(), parent="effect-never-observed")
        self.assert_code("COMPENSATION_PARENT_NOT_COMMITTED", bundle)

    def test_compensation_cannot_erase_parent_history(self) -> None:
        bundle = _append_compensation(fixed_effect_bundle(), parent="effect-main-001", erases=True)
        self.assert_code("COMPENSATION_ERASES_PARENT_HISTORY", bundle)


if __name__ == "__main__":
    unittest.main()
