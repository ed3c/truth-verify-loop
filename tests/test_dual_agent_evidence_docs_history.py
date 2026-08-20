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

        post_merge = {
            "pr": 46,
            "head": "5bec79cb02bf9fb413c317be4f3dc5a9c9e33a16",
            "run": 32325711166,
            "finding": "POST_MERGE_DOCS_TOKEN_AND_HISTORY_EXPECTATION_DRIFT",
            "resolution_head": "19ae75ec7e151fdb76ae7b78ac859ef39b790fd3",
        }
        self.assertIn(post_merge, failures)

    def test_failure_history_does_not_raise_evidence_ceiling(self) -> None:
        index = json.loads(INDEX.read_text())
        self.assertEqual(
            index["evidence_ceiling"],
            "COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY",
        )
        self.assertEqual(index["docs_subject_state"], "IMPLEMENTATION_MERGED_TO_MAIN")
        self.assertEqual(
            index["integration_main"],
            {
                "repository": "ed3c/truth-verify-loop",
                "branch": "main",
                "commit": "123bee539157331cb976c2926f4359352430bfd1",
                "tree": "507a4bda6e0df459fca1d71c838c9386cf3aff79",
                "merge_pr": 28,
                "merge_chain": [45, 44, 39, 29, 28],
                "state": "DETERMINISTIC_IMPLEMENTATION_IN_MAIN",
            },
        )
        self.assertEqual(index["live_frontier"]["human"], "NOT_EXERCISED")
        self.assertEqual(index["live_frontier"]["release"], "NOT_PERFORMED")
        self.assertEqual(index["local_handoff"]["state"], "HANDOFF_READY_NOT_EXERCISED")


if __name__ == "__main__":
    unittest.main()
