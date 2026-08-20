from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from harness.dual_agent_evidence.contract import DualAgentEvidenceError

ROOT = Path(__file__).resolve().parents[1]
SUBTREE = ROOT / "harness/dual_agent_evidence"

EXPECTED_NODES = {
    "DA-TV-C": {
        "issue": 31,
        "pr": 39,
        "head": "944af8fc0230a9aae31ad47d6cb6051e10521bc7",
        "tree": "1bb3589e20c157136a2597a51db15599226f4c6a",
        "targeted_run": 32297448276,
        "repository_verify_run": 32297448445,
        "state": "DETERMINISTIC_PASS",
    },
    "DA-TV-DLV": {
        "issue": 32,
        "pr": 40,
        "head": "1faf6f818ecb9c70d122461421edf3b720e0f18e",
        "tree": "120f9e496923c428cb8c3ccd53009b2e0c92175a",
        "targeted_run": 32297590276,
        "repository_verify_run": 32297590291,
        "state": "DETERMINISTIC_PASS",
    },
    "DA-TV-EF": {
        "issue": 33,
        "pr": 41,
        "head": "84170be2faac66fadadb1e74ef605c7006b7e898",
        "tree": "01c380ff49a3274cecda8c233db676f45b73c777",
        "targeted_run": 32297636307,
        "repository_verify_run": 32297636445,
        "state": "DETERMINISTIC_PASS",
    },
    "DA-TV-ART": {
        "issue": 34,
        "pr": 42,
        "head": "080f623cdc7f163ca941ec31838ee6171d8bf999",
        "tree": "cd70a2875dc022a3af5d07512cf15b3345444b11",
        "targeted_run": 32297675577,
        "repository_verify_run": 32297675560,
        "state": "DETERMINISTIC_PASS",
    },
    "DA-TV-USER": {
        "issue": 35,
        "pr": 43,
        "head": "781388d84490a902d4cad414673164b40c3927d2",
        "tree": "6ff6a9df8d69a5dd35c42eddbb053bbc2be5be4a",
        "targeted_run": 32297728757,
        "repository_verify_run": 32297728719,
        "state": "DETERMINISTIC_PASS",
    },
    "DA-TV-E": {
        "issue": 36,
        "pr": 44,
        "head": "55d13fe61eec88cd1cd5f04f0670a83ebc366953",
        "tree": "e8f5194b91814d26e3c87cc194cf8789a87db4b5",
        "targeted_run": 32298186985,
        "repository_verify_run": 32298186805,
        "state": "COMPLETE_DETERMINISTIC_MATRIX_PASS",
    },
}

EXPECTED_CEILING = "COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY"


class DocsTraceError(DualAgentEvidenceError):
    pass


def _refuse(code: str, detail: str = "") -> None:
    raise DocsTraceError(code, detail)


def verify_docs(index: dict, readme: str, agents: str, preflight: dict) -> None:
    if index.get("schema") != "tvl.dual-agent-evidence-stack-index.v1":
        _refuse("STACK_INDEX_SCHEMA_DRIFT")
    if index.get("parent_issue") != 22 or index.get("docs_issue") != 37 or index.get("docs_pr") != 45:
        _refuse("DOCS_ROUTE_DRIFT")
    if index.get("docs_subject_state") != "CANDIDATE_SUBJECT_PENDING":
        _refuse("DOCS_SELF_PROMOTION")

    baseline = index.get("green_baseline", {})
    if baseline != {
        "pr": 29,
        "head": "c01254547672a9ad03345c9013b20d3d1049e274",
        "tree": "577213165a091aee389e9c7028570eb8cf6da1c7",
        "repository_verify_run": 32252254820,
    }:
        _refuse("GREEN_BASELINE_DRIFT")

    nodes = index.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != len(EXPECTED_NODES):
        _refuse("EXACT_NODE_SET_DRIFT")
    by_atom = {node.get("atom"): node for node in nodes if isinstance(node, dict)}
    if set(by_atom) != set(EXPECTED_NODES):
        _refuse("EXACT_NODE_SET_DRIFT")
    for atom, expected in EXPECTED_NODES.items():
        node = by_atom[atom]
        for key, value in expected.items():
            if node.get(key) != value:
                _refuse("EXACT_SUBJECT_OR_RUN_DRIFT", f"{atom}.{key}")

    failures = index.get("retained_failures")
    if not isinstance(failures, list):
        _refuse("FAILURE_HISTORY_ERASED")
    failure_pairs = {(item.get("pr"), item.get("run")) for item in failures if isinstance(item, dict)}
    if not {(38, 32295680345), (38, 32295801844)}.issubset(failure_pairs):
        _refuse("FAILURE_HISTORY_ERASED")
    as_of_finding = any(
        item.get("finding") == "SHADOW_SCHEMA_REVIEW_CLOSURE_AS_OF_WAS_NULL"
        and item.get("resolution_head") == "944af8fc0230a9aae31ad47d6cb6051e10521bc7"
        for item in failures
        if isinstance(item, dict)
    )
    if not as_of_finding:
        _refuse("FAILURE_HISTORY_ERASED", "as_of")

    authority = index.get("authority", {})
    if authority.get("truth_vocabulary_owner") != "existing-truth-verify-loop-closure-plane":
        _refuse("TRUTH_VOCABULARY_OWNER_DRIFT")
    if authority.get("technical_matrix_canonical_write") != "NONE":
        _refuse("TECHNICAL_WRITER_WIDENING")
    if authority.get("execution_authority") != "EXTERNAL" or authority.get("workflow_authority") != "EXTERNAL" or authority.get("effect_authority") != "EXTERNAL":
        _refuse("EXECUTION_AUTHORITY_DRIFT")
    if authority.get("semantic_claim_direction_owner") != "existing-truth-verify-loop-semantic-plane":
        _refuse("SEMANTIC_OWNER_DRIFT")
    if authority.get("human_admission") != "EXTERNAL" or authority.get("release") != "EXTERNAL":
        _refuse("HUMAN_RELEASE_OWNER_DRIFT")

    if index.get("evidence_ceiling") != EXPECTED_CEILING:
        _refuse("EVIDENCE_CEILING_DRIFT")

    live = index.get("live_frontier", {})
    expected_live = {
        "physical_local_cloud_local_run": "NOT_EXERCISED",
        "live_provider_network": "NOT_EXERCISED",
        "private_source_evidence": "NOT_EXERCISED",
        "semantic_claim_closure": "NOT_EXERCISED_BY_DA_TV_MATRIX",
        "live_user_result": "NOT_EXERCISED",
        "human": "NOT_EXERCISED",
        "release": "NOT_PERFORMED",
    }
    if live != expected_live:
        _refuse("LIVE_OR_RELEASE_PROMOTION")

    if preflight.get("schema") != "tvl.dual-agent-verification-matrix-preflight.v1":
        _refuse("MATRIX_PREFLIGHT_DRIFT")
    parent = preflight.get("parent", {})
    root = EXPECTED_NODES["DA-TV-C"]
    if parent.get("pr") != root["pr"] or parent.get("head") != root["head"] or parent.get("tree") != root["tree"] or parent.get("targeted_run") != root["targeted_run"] or parent.get("repository_verify_run") != root["repository_verify_run"]:
        _refuse("MATRIX_PREFLIGHT_DRIFT", "parent")
    expected_siblings = {"DA-TV-DLV", "DA-TV-EF", "DA-TV-ART", "DA-TV-USER"}
    siblings = preflight.get("siblings")
    if not isinstance(siblings, list) or {item.get("atom") for item in siblings} != expected_siblings:
        _refuse("MATRIX_PREFLIGHT_DRIFT", "siblings")
    for sibling in siblings:
        atom = sibling["atom"]
        expected = EXPECTED_NODES[atom]
        for key in ("pr", "head", "tree", "targeted_run", "repository_verify_run"):
            if sibling.get(key) != expected[key]:
                _refuse("MATRIX_PREFLIGHT_DRIFT", f"{atom}.{key}")
    if preflight.get("evidence_ceiling") != EXPECTED_CEILING:
        _refuse("MATRIX_PREFLIGHT_DRIFT", "ceiling")

    readme_tokens = [
        "existing `tvl.evidence-closure.v1`",
        "UNVERIFIABLE",
        "COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY",
        "canonical_write=NONE",
        "real local→cloud→local physical run",
        "Screenshot presence is not semantic proof",
        "Backend completion is not user-visible success",
    ]
    for token in readme_tokens:
        if token not in readme:
            _refuse("README_TRACE_INCOMPLETE", token)

    agents_tokens = [
        "SUPPORTED",
        "REFUTED",
        "CONFLICTED",
        "STALE",
        "UNVERIFIABLE",
        "canonical_write=NONE",
        "Technical verifier PASS cannot emit SUPPORTED/REFUTED by itself.",
        "Shadow stop conditions",
        "DA-TV-D / issue #37",
        "DA-TV-ART must hash independently supplied captured/read-back bytes.",
    ]
    for token in agents_tokens:
        if token not in agents:
            _refuse("AGENT_ROUTE_INCOMPLETE", token)


class DualAgentDocsTraceabilityTest(unittest.TestCase):
    def load(self) -> tuple[dict, str, str, dict]:
        index = json.loads((SUBTREE / "stack-index.json").read_text())
        readme = (SUBTREE / "README.md").read_text()
        agents = (SUBTREE / "AGENTS.md").read_text()
        preflight = json.loads((SUBTREE / "matrix-preflight.json").read_text())
        return index, readme, agents, preflight

    def assert_code(self, code: str, fn) -> None:
        with self.assertRaises(DocsTraceError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_current_read_route_is_exact_and_non_promoting(self) -> None:
        verify_docs(*self.load())

    def test_exact_subject_drift_is_refused(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["nodes"][0]["head"] = "0" * 40
        self.assert_code("EXACT_SUBJECT_OR_RUN_DRIFT", lambda: verify_docs(changed, readme, agents, preflight))

    def test_run_drift_is_refused(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["nodes"][-1]["targeted_run"] += 1
        self.assert_code("EXACT_SUBJECT_OR_RUN_DRIFT", lambda: verify_docs(changed, readme, agents, preflight))

    def test_failure_history_erasure_is_refused(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["retained_failures"] = changed["retained_failures"][1:]
        self.assert_code("FAILURE_HISTORY_ERASED", lambda: verify_docs(changed, readme, agents, preflight))

    def test_docs_cannot_self_promote(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["docs_subject_state"] = "RELEASED"
        self.assert_code("DOCS_SELF_PROMOTION", lambda: verify_docs(changed, readme, agents, preflight))

    def test_live_state_cannot_be_promoted(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["live_frontier"]["live_user_result"] = "PASS"
        self.assert_code("LIVE_OR_RELEASE_PROMOTION", lambda: verify_docs(changed, readme, agents, preflight))

    def test_truth_vocabulary_owner_cannot_drift(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["authority"]["truth_vocabulary_owner"] = "dual-agent-subtree"
        self.assert_code("TRUTH_VOCABULARY_OWNER_DRIFT", lambda: verify_docs(changed, readme, agents, preflight))

    def test_technical_matrix_cannot_become_writer(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["authority"]["technical_matrix_canonical_write"] = "TASK_AND_EFFECT"
        self.assert_code("TECHNICAL_WRITER_WIDENING", lambda: verify_docs(changed, readme, agents, preflight))

    def test_semantic_owner_cannot_move_into_matrix(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["authority"]["semantic_claim_direction_owner"] = "DA-TV-E"
        self.assert_code("SEMANTIC_OWNER_DRIFT", lambda: verify_docs(changed, readme, agents, preflight))

    def test_evidence_ceiling_cannot_widen(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(index)
        changed["evidence_ceiling"] = "LIVE_SEMANTIC_TRUTH_PASS"
        self.assert_code("EVIDENCE_CEILING_DRIFT", lambda: verify_docs(changed, readme, agents, preflight))

    def test_matrix_preflight_must_match_stack_index(self) -> None:
        index, readme, agents, preflight = self.load()
        changed = deepcopy(preflight)
        changed["siblings"][0]["targeted_run"] += 1
        self.assert_code("MATRIX_PREFLIGHT_DRIFT", lambda: verify_docs(index, readme, agents, changed))


if __name__ == "__main__":
    unittest.main()
