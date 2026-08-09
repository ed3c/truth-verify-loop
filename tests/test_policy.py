from datetime import datetime, timedelta, timezone
import unittest

from harness.model import Claim
from harness.policy import SourcePolicy, decide_live_search

NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)


def claim(**overrides):
    data = {
        "claim_id": "c-policy",
        "statement": "Pinned fact.",
        "risk": "low",
        "temporality": "static",
        "freshness_sla_seconds": 86400,
        "last_verified_at": (NOW - timedelta(hours=1)).isoformat(),
    }
    data.update(overrides)
    return Claim.from_dict(data)


class PolicyTests(unittest.TestCase):
    def test_dynamic_claim_requires_live_search(self):
        result = decide_live_search(claim(temporality="dynamic"), model_knowledge_cutoff=None, now=NOW)
        self.assertTrue(result.required)
        self.assertIn("dynamic claim", " ".join(result.reasons))

    def test_fresh_static_low_risk_can_use_offline_memory(self):
        result = decide_live_search(
            claim(), model_knowledge_cutoff="2025-12-01T00:00:00Z", now=NOW
        )
        self.assertFalse(result.required)
        self.assertEqual(result.mode, "OFFLINE_MEMORY_OK")

    def test_unknown_cutoff_fails_closed_for_high_risk(self):
        result = decide_live_search(claim(risk="high"), model_knowledge_cutoff=None, now=NOW)
        self.assertTrue(result.required)
        self.assertIn("unknown", " ".join(result.reasons))

    def test_unpinned_version_requires_live_search(self):
        result = decide_live_search(
            claim(temporality="versioned", scope={"version": "latest"}),
            model_knowledge_cutoff="2026-08-09T00:00:00Z",
            now=NOW,
        )
        self.assertTrue(result.required)
        self.assertIn("not pinned", " ".join(result.reasons))

    def test_only_standing_policy_can_assign_authority(self):
        policy = SourcePolicy(
            domain_classes={"example.org": "first_party", "docs.example.org": "official_doc"}
        )
        self.assertEqual(policy.classify("https://v1.docs.example.org/a"), "official_doc")
        trusted = claim(trusted_domains=["trusted.invalid"])
        self.assertEqual(
            policy.classify("https://docs.trusted.invalid/a", claim=trusted),
            "unclassified",
        )


if __name__ == "__main__":
    unittest.main()
