from datetime import datetime, timedelta, timezone
import unittest

from harness.closure import close_claim
from harness.model import Claim, Evidence, sha256_text
from harness.policy import SourcePolicy

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)


def claim(**overrides):
    data = {
        "claim_id": "c-closure",
        "statement": "Example SDK 4.2 is generally available.",
        "risk": "low",
        "temporality": "static",
        "freshness_sla_seconds": 86400,
    }
    data.update(overrides)
    return Claim.from_dict(data)


def evidence(
    evidence_id="ev-1",
    relationship="supports",
    source_class="community",
    source_uri="https://community.example.invalid/post",
    retrieved_at=NOW,
    capture_scope="full_source",
    families=None,
    quote="Example SDK 4.2 is generally available.",
):
    citation = {"quote_verified": True}
    if families is not None:
        citation["semantic_verifier_families"] = list(families)
    return Evidence.from_dict({
        "evidence_id": evidence_id,
        "claim_id": "c-closure",
        "source_uri": source_uri,
        "source_class": source_class,
        "relationship": relationship,
        "quote": quote,
        "retrieved_at": retrieved_at.isoformat(),
        "content_sha256": "a" * 64,
        "quote_sha256": sha256_text(quote),
        "capture_scope": capture_scope,
        "provider_receipt_sha256": "b" * 64,
        "citation": citation,
    })


class ClosureTests(unittest.TestCase):
    def test_low_risk_support_closes(self):
        result = close_claim(claim(), [evidence()], policy=SourcePolicy(), now=NOW)
        self.assertEqual(result["state"], "SUPPORTED")
        self.assertTrue(result["closed"])

    def test_low_risk_refutation_closes(self):
        result = close_claim(
            claim(), [evidence(relationship="refutes")], policy=SourcePolicy(), now=NOW
        )
        self.assertEqual(result["state"], "REFUTED")
        self.assertTrue(result["closed"])

    def test_support_and_refutation_remain_conflicted(self):
        items = [
            evidence(evidence_id="ev-support"),
            evidence(evidence_id="ev-refute", relationship="refutes", source_uri="https://other.example.invalid/a"),
        ]
        result = close_claim(claim(), items, policy=SourcePolicy(), now=NOW)
        self.assertEqual(result["state"], "CONFLICTED")
        self.assertFalse(result["gates"]["G8_NO_UNRESOLVED_CONFLICT"])

    def test_only_expired_evidence_is_stale(self):
        item = evidence(retrieved_at=NOW - timedelta(days=2))
        result = close_claim(claim(), [item], policy=SourcePolicy(), now=NOW)
        self.assertEqual(result["state"], "STALE")
        self.assertFalse(result["closed"])

    def test_medium_risk_requires_semantic_review(self):
        item = evidence(
            source_class="official_doc",
            source_uri="https://docs.example.invalid/a",
        )
        result = close_claim(claim(risk="medium"), [item], policy=SourcePolicy(), now=NOW)
        self.assertFalse(result["gates"]["G7_SEMANTIC_REVIEW"])
        self.assertEqual(result["state"], "UNVERIFIABLE")

    def test_high_risk_one_model_family_cannot_close(self):
        items = [
            evidence(
                evidence_id="ev-official",
                source_class="official_doc",
                source_uri="https://docs.example.invalid/a",
                families=("antigravity-cli",),
            ),
            evidence(
                evidence_id="ev-independent",
                source_class="independent",
                source_uri="https://analysis.example.org/a",
                families=("antigravity-cli",),
            ),
        ]
        result = close_claim(claim(risk="high"), items, policy=SourcePolicy(), now=NOW)
        self.assertFalse(result["gates"]["G7_SEMANTIC_REVIEW"])
        self.assertFalse(result["closed"])

    def test_medium_risk_rejects_snippet_only_capture(self):
        item = evidence(
            source_class="official_doc",
            source_uri="https://docs.example.invalid/a",
            capture_scope="agent_grounded_snippet",
            families=("verifier-a",),
        )
        result = close_claim(claim(risk="medium"), [item], policy=SourcePolicy(), now=NOW)
        self.assertFalse(result["gates"]["G6_FULL_SOURCE_CAPTURE"])
        self.assertFalse(result["closed"])


if __name__ == "__main__":
    unittest.main()
