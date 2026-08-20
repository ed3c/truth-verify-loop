from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "harness/dual_agent_evidence/stack-index.json"


class DualAgentDocsFailureHistoryTest(unittest.TestCase):
    def test_docs_trace_failure_and_resolution_are_retained(self) -> None:
        index = json.loads(INDEX.read_text())
        failures = index.get("retained_failures", [])
        expected = {
            "pr": 45,
            "head": "b6a9bcfd08bc59b5151cd4507313a1882dcec7fa",
            "run": 32298782739,
            "finding": "AGENT_ROUTE_INCOMPLETE_NORMATIVE_TOKEN",
            "resolution_head": "60c06a62af6a15149da2b3d49998a18d44e87f70",
        }
        self.assertIn(expected, failures)

    def test_failure_history_does_not_raise_evidence_ceiling(self) -> None:
        index = json.loads(INDEX.read_text())
        self.assertEqual(
            index["evidence_ceiling"],
            "COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY",
        )
        self.assertEqual(index["docs_subject_state"], "CANDIDATE_SUBJECT_PENDING")
        self.assertEqual(index["live_frontier"]["human"], "NOT_EXERCISED")
        self.assertEqual(index["live_frontier"]["release"], "NOT_PERFORMED")


if __name__ == "__main__":
    unittest.main()
