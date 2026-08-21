from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from harness.closure import close_claim
from harness.kaw_receipt import (
    KawReceiptError,
    build_public_canary_receipt,
    canonical_sha256,
    validate_kaw_domain_receipt,
)
from harness.model import Claim, Evidence
from harness.policy import SourcePolicy

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "receipts/kaw/public-claim-canary.json"
CLAIM_PATH = ROOT / "examples/live-search/fixture-claim.json"
EVIDENCE_PATH = ROOT / "examples/live-search/fixture-evidence.jsonl"
POLICY_PATH = ROOT / "config/source-policy.example.json"


def load_claim() -> dict:
    return json.loads(CLAIM_PATH.read_text(encoding="utf-8"))


def load_evidence() -> dict:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8").strip())


def load_policy() -> SourcePolicy:
    return SourcePolicy.from_dict(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


class KawDomainReceiptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = build_public_canary_receipt(ROOT)

    def assert_rejected(self, mutate) -> None:
        candidate = deepcopy(self.expected)
        mutate(candidate)
        with self.assertRaises(KawReceiptError):
            validate_kaw_domain_receipt(candidate, expected=self.expected)

    def test_tracked_receipt_is_exact_deterministic_rebuild(self) -> None:
        tracked = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        digest = validate_kaw_domain_receipt(tracked, expected=self.expected)
        self.assertEqual("0f315e70842caf9d8330ad41d5d2b8e0fddde99fd581aa99957a4b4f502aa661", digest)

    def test_claim_and_evidence_digests_are_bound(self) -> None:
        claim = load_claim()
        evidence = load_evidence()
        subject = self.expected["subject"]
        self.assertEqual(canonical_sha256(claim), subject["claim_digest"])
        self.assertEqual(canonical_sha256(evidence), subject["evidence_record_digest"])
        self.assertEqual(evidence["content_sha256"], subject["source_content_digest"])

    def test_closure_engine_retains_all_domain_states(self) -> None:
        claim = Claim.from_dict(load_claim())
        base = load_evidence()
        policy = load_policy()
        now = datetime(2026, 8, 21, tzinfo=timezone.utc)

        supported = close_claim(claim, [Evidence.from_dict(base)], policy=policy, now=now)
        refuted_raw = dict(base, evidence_id="ev-refuted", relationship="refutes")
        refuted = close_claim(claim, [Evidence.from_dict(refuted_raw)], policy=policy, now=now)
        conflicted_raw = dict(base, evidence_id="ev-conflict", relationship="refutes")
        conflicted = close_claim(
            claim,
            [Evidence.from_dict(base), Evidence.from_dict(conflicted_raw)],
            policy=policy,
            now=now,
        )
        stale = close_claim(
            claim,
            [Evidence.from_dict(base)],
            policy=policy,
            now=datetime(2028, 8, 22, tzinfo=timezone.utc),
        )
        unverifiable = close_claim(claim, [], policy=policy, now=now)

        self.assertEqual("SUPPORTED", supported["state"])
        self.assertEqual("REFUTED", refuted["state"])
        self.assertEqual("CONFLICTED", conflicted["state"])
        self.assertEqual("STALE", stale["state"])
        self.assertEqual("UNVERIFIABLE", unverifiable["state"])

    def test_wrong_authority_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["authority"].__setitem__("owner", "other-repository"))

    def test_cross_claim_reuse_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["subject"].__setitem__("claim_id", "other-claim"))

    def test_claim_digest_drift_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["subject"].__setitem__("claim_digest", "0" * 64))

    def test_closure_digest_drift_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["verdict"].__setitem__("closure_digest", "0" * 64))

    def test_environment_widening_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value.__setitem__("environment", "PRODUCTION"))

    def test_domain_verdict_cannot_be_rewritten(self) -> None:
        self.assert_rejected(lambda value: value["verdict"].__setitem__("state", "REFUTED"))

    def test_evidence_ceiling_cannot_be_promoted(self) -> None:
        self.assert_rejected(lambda value: value["verdict"].__setitem__("evidence_ceiling", "USER_OUTCOME"))

    def test_raw_source_disclosure_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["disclosure"].__setitem__("raw_source_included", True))

    def test_internal_reasoning_disclosure_is_rejected(self) -> None:
        self.assert_rejected(
            lambda value: value["disclosure"].__setitem__("internal_reasoning_included", True),
        )

    def test_user_outcome_promotion_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["evidence_boundary"].__setitem__("user_outcome", "PASS"))

    def test_merge_authority_promotion_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["evidence_boundary"].__setitem__("merge_release", "PASS"))

    def test_unknown_raw_evidence_field_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value.__setitem__("raw_evidence", {"quote": "hidden"}))

    def test_policy_blob_drift_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["policy"].__setitem__("closure_engine_blob", "0" * 40))

    def test_secret_like_material_is_rejected(self) -> None:
        self.assert_rejected(lambda value: value["policy"].__setitem__("policy_version", "Bearer example"))

    def test_external_locator_is_rejected(self) -> None:
        self.assert_rejected(
            lambda value: value["policy"].__setitem__("policy_version", "https://example.invalid"),
        )


if __name__ == "__main__":
    unittest.main()
