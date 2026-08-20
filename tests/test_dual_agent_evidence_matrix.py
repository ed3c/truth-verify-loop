from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from harness.dual_agent_evidence.artifact import verify_source_artifacts
from harness.dual_agent_evidence.convergence import converge_findings, verify_complete_bundle
from harness.dual_agent_evidence.contract import REQUIRED_FAMILIES, DualAgentEvidenceError
from harness.dual_agent_evidence.delivery import verify_delivery_workflow
from harness.dual_agent_evidence.effect import verify_effect_lineage
from harness.dual_agent_evidence.user_result import verify_user_result
from harness.model import canonical_json, sha256_text
from tests.test_dual_agent_evidence_artifact import fixed_artifact_bundle
from tests.test_dual_agent_evidence_delivery import fixed_delivery_bundle
from tests.test_dual_agent_evidence_effect import fixed_effect_bundle
from tests.test_dual_agent_evidence_user_result import fixed_user_bundle

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "harness/dual_agent_evidence/matrix-preflight.json"


def _set_payload(receipt: dict, payload: dict) -> None:
    receipt["payload"] = payload
    receipt["payload_digest"] = sha256_text(canonical_json(payload))


def _copy_family_payload(target: dict, source: dict, family: str) -> None:
    dst = next(item for item in target["receipts"] if item["family"] == family)
    src = next(item for item in source["receipts"] if item["family"] == family)
    dst["lane"] = src["lane"]
    dst["state"] = src["state"]
    dst["payload"] = deepcopy(src["payload"])
    dst["payload_digest"] = src["payload_digest"]


def complete_fixture() -> tuple[dict, bytes, dict[str, bytes]]:
    bundle = fixed_delivery_bundle()

    effect_bundle = fixed_effect_bundle()
    _copy_family_payload(bundle, effect_bundle, "EFFECT")
    effect_resolution = deepcopy(effect_bundle["receipts"][-1])
    effect_resolution["receipt_id"] = "receipt-matrix-effect-resolution"
    effect_resolution["sequence"] = len(bundle["receipts"])
    bundle["receipts"].append(effect_resolution)

    artifact_bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
    for family in ("SOURCE", "ARTIFACT"):
        _copy_family_payload(bundle, artifact_bundle, family)

    user_bundle = fixed_user_bundle()
    for family in ("PROVIDER_RUNTIME", "ROUTE_OBSERVATION", "USER_RESULT", "CLEANUP", "HUMAN", "RELEASE"):
        _copy_family_payload(bundle, user_bundle, family)

    expected_producers: dict[str, str] = {}
    for family in REQUIRED_FAMILIES:
        if family == "BINDING":
            continue
        digests = {item["producer"]["digest"] for item in bundle["receipts"] if item["family"] == family}
        if len(digests) != 1:
            raise AssertionError(f"fixture producer conflict for {family}")
        expected_producers[family] = next(iter(digests))

    binding = next(item for item in bundle["receipts"] if item["family"] == "BINDING")
    _set_payload(
        binding,
        {
            "expected_producer_digests": expected_producers,
            "runtime_contract_digest": "d" * 64,
            "expected_runtime_contract_digest": "d" * 64,
            "policy_digest": "e" * 64,
            "expected_policy_digest": "e" * 64,
        },
    )
    return bundle, source_bytes, artifact_bytes


def complete_findings(bundle: dict, source_bytes: bytes, artifact_bytes: dict[str, bytes]) -> list[dict]:
    return [
        verify_delivery_workflow(bundle),
        verify_effect_lineage(bundle),
        verify_source_artifacts(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes),
        verify_user_result(bundle),
    ]


def _rehash_finding(finding: dict) -> None:
    body = dict(finding)
    body.pop("finding_digest", None)
    finding["finding_digest"] = sha256_text(canonical_json(body))


def verify_preflight(preflight: dict) -> None:
    if preflight.get("schema") != "tvl.dual-agent-verification-matrix-preflight.v1":
        raise DualAgentEvidenceError("PREFLIGHT_SCHEMA_DRIFT")
    expected_atoms = {"DA-TV-DLV", "DA-TV-EF", "DA-TV-ART", "DA-TV-USER"}
    siblings = preflight.get("siblings")
    if not isinstance(siblings, list) or {item.get("atom") for item in siblings} != expected_atoms:
        raise DualAgentEvidenceError("PREFLIGHT_VERIFIER_SET_DRIFT")
    for sibling in siblings:
        for path, expected_blob in sibling["files"].items():
            actual = subprocess.run(
                ["git", "hash-object", path],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            if actual != expected_blob:
                raise DualAgentEvidenceError("SIBLING_BLOB_DRIFT", path)
    failures = preflight.get("retained_failures")
    required_failures = {(38, 32295680345), (38, 32295801844)}
    observed = {(item.get("pr"), item.get("run")) for item in failures or []}
    if not required_failures.issubset(observed):
        raise DualAgentEvidenceError("FAILURE_HISTORY_ERASED")
    if preflight.get("evidence_ceiling") != "COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY":
        raise DualAgentEvidenceError("MATRIX_EVIDENCE_CEILING_DRIFT")
    external = preflight.get("external_states", {})
    if any(external.get(key) != "NOT_EXERCISED" for key in ("live_provider", "live_network", "live_user_result", "semantic_claim_closure", "human")):
        raise DualAgentEvidenceError("MATRIX_LIVE_PROMOTION")
    if external.get("release") != "NOT_PERFORMED":
        raise DualAgentEvidenceError("MATRIX_LIVE_PROMOTION")


class CompleteDualAgentVerificationMatrixTest(unittest.TestCase):
    def assert_code(self, code: str, fn) -> None:
        with self.assertRaises(DualAgentEvidenceError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_exact_sibling_blobs_and_failure_history_are_preserved(self) -> None:
        preflight = json.loads(PREFLIGHT_PATH.read_text())
        verify_preflight(preflight)

    def test_complete_technical_matrix_stops_at_unverifiable(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        closure = verify_complete_bundle(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes)
        schema = json.loads((ROOT / "schemas/evidence-closure.v1.schema.json").read_text())
        self.assertTrue(set(schema["required"]).issubset(closure))
        self.assertEqual(closure["state"], "UNVERIFIABLE")
        self.assertFalse(closure["closed"])
        self.assertTrue(closure["gates"]["DA7_NO_TECHNICAL_DISAGREEMENT"])
        self.assertFalse(closure["gates"]["G7_SEMANTIC_REVIEW"])
        self.assertEqual(closure["authority"]["canonical_write"], "NONE")
        self.assertEqual(closure["run"]["technical_matrix"], "PASS")
        self.assertEqual(closure["run"]["release_state"], "NOT_PERFORMED")

    def test_missing_verifier_family_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        findings = complete_findings(bundle, source_bytes, artifact_bytes)
        self.assert_code("MISSING_VERIFIER_FAMILY", lambda: converge_findings(bundle, findings[:-1]))

    def test_tampered_verifier_finding_digest_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        findings = complete_findings(bundle, source_bytes, artifact_bytes)
        findings[0]["task_state"] = "PASS"
        self.assert_code("VERIFIER_FINDING_DIGEST_MISMATCH", lambda: converge_findings(bundle, findings))

    def test_rehashed_verifier_cannot_self_promote(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        findings = complete_findings(bundle, source_bytes, artifact_bytes)
        findings[0]["task_state"] = "PASS"
        _rehash_finding(findings[0])
        self.assert_code("DELIVERY_VERIFIER_SELF_PROMOTION", lambda: converge_findings(bundle, findings))

    def test_verifier_evidence_ceiling_cannot_widen(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        findings = complete_findings(bundle, source_bytes, artifact_bytes)
        findings[1]["evidence_ceiling"] = "LIVE_EFFECT_PASS"
        _rehash_finding(findings[1])
        self.assert_code("VERIFIER_EVIDENCE_CEILING_WIDENING", lambda: converge_findings(bundle, findings))

    def test_stale_runtime_binding_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        binding = next(item for item in bundle["receipts"] if item["family"] == "BINDING")
        payload = deepcopy(binding["payload"])
        payload["expected_runtime_contract_digest"] = "f" * 64
        _set_payload(binding, payload)
        self.assert_code(
            "STALE_RUNTIME_BINDING",
            lambda: verify_complete_bundle(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes),
        )

    def test_stale_policy_binding_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        binding = next(item for item in bundle["receipts"] if item["family"] == "BINDING")
        payload = deepcopy(binding["payload"])
        payload["expected_policy_digest"] = "1" * 64
        _set_payload(binding, payload)
        self.assert_code(
            "STALE_POLICY_BINDING",
            lambda: verify_complete_bundle(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes),
        )

    def test_producer_subject_binding_cannot_drift(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        binding = next(item for item in bundle["receipts"] if item["family"] == "BINDING")
        payload = deepcopy(binding["payload"])
        payload["expected_producer_digests"]["EFFECT"] = "2" * 64
        _set_payload(binding, payload)
        self.assert_code(
            "STALE_OR_CONFLICTED_PRODUCER_BINDING",
            lambda: verify_complete_bundle(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes),
        )

    def test_technical_matrix_cannot_emit_supported_or_refuted(self) -> None:
        bundle, source_bytes, artifact_bytes = complete_fixture()
        bundle["requested_closure_state"] = "SUPPORTED"
        self.assert_code(
            "TECHNICAL_VERIFIER_SELF_CLOSURE",
            lambda: verify_complete_bundle(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes),
        )

    def test_failure_history_erasure_is_refused(self) -> None:
        preflight = json.loads(PREFLIGHT_PATH.read_text())
        preflight["retained_failures"] = preflight["retained_failures"][1:]
        self.assert_code("FAILURE_HISTORY_ERASED", lambda: verify_preflight(preflight))

    def test_sibling_blob_drift_is_refused(self) -> None:
        preflight = json.loads(PREFLIGHT_PATH.read_text())
        first = preflight["siblings"][0]
        path = next(iter(first["files"]))
        first["files"][path] = "0" * 40
        self.assert_code("SIBLING_BLOB_DRIFT", lambda: verify_preflight(preflight))

    def test_preflight_cannot_promote_live_state(self) -> None:
        preflight = json.loads(PREFLIGHT_PATH.read_text())
        preflight["external_states"]["live_user_result"] = "PASS"
        self.assert_code("MATRIX_LIVE_PROMOTION", lambda: verify_preflight(preflight))


if __name__ == "__main__":
    unittest.main()
