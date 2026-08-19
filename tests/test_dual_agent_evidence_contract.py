from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness.dual_agent_evidence.contract import (
    BUNDLE_SCHEMA,
    CLOSURE_SCHEMA,
    REQUIRED_FAMILIES,
    DualAgentEvidenceError,
    compile_contract_closure,
    mutated_copy,
    validate_bundle,
)
from harness.model import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]


def _producer(seed: str = "a") -> dict:
    return {
        "repository": "example/runtime",
        "commit": seed * 40,
        "tree": "b" * 40,
        "schema": "example.receipt.v1",
        "version": "v1",
        "digest": "c" * 64,
    }


def _receipt(index: int, family: str) -> dict:
    payload = {"family": family, "observation": f"fixture-{index}"}
    state = "OBSERVED"
    lane = "LOCAL" if index < 4 else "CLOUD"
    if family == "ROUTE_OBSERVATION":
        lane = "API"
    elif family == "USER_RESULT":
        lane = "USER"
    elif family == "HUMAN":
        lane = "HUMAN"
        state = "NOT_EXERCISED"
    elif family == "RELEASE":
        lane = "RELEASE"
        state = "NOT_PERFORMED"
    return {
        "receipt_id": f"receipt-{index:02d}",
        "family": family,
        "lane": lane,
        "run_id": "run-dual-agent-001",
        "job_id": "job-dual-agent-001",
        "tenant_scope": "tenant-public-fixture",
        "attempt_id": "attempt-0" if index < 7 else "attempt-1",
        "sequence": index,
        "state": state,
        "producer": _producer(),
        "payload": payload,
        "payload_digest": sha256_text(canonical_json(payload)),
        "evidence_class": "DETERMINISTIC_FIXTURE",
        "observed_at": "2026-08-19T00:00:00Z",
        "canonical_write": "OBSERVATION_ONLY",
    }


def fixed_bundle() -> dict:
    return {
        "schema": BUNDLE_SCHEMA,
        "bundle_id": "bundle-dual-agent-001",
        "claim_id": "claim-dual-agent-user-result",
        "run_id": "run-dual-agent-001",
        "job_id": "job-dual-agent-001",
        "tenant_scope": "tenant-public-fixture",
        "requested_closure_state": "UNVERIFIABLE",
        "required_families": list(REQUIRED_FAMILIES),
        "receipts": [_receipt(i, family) for i, family in enumerate(REQUIRED_FAMILIES)],
        "external_states": {
            "task": "NOT_EXERCISED",
            "effect": "NOT_EXERCISED",
            "human": "NOT_EXERCISED",
            "release": "NOT_PERFORMED",
        },
    }


class DualAgentEvidenceContractTest(unittest.TestCase):
    def assert_code(self, code: str, fn) -> None:
        with self.assertRaises(DualAgentEvidenceError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_schema_is_json_and_matches_contract(self) -> None:
        schema = json.loads((ROOT / "schemas/dual-agent-evidence-bundle.v1.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema"]["const"], BUNDLE_SCHEMA)
        self.assertEqual(schema["properties"]["required_families"]["const"], list(REQUIRED_FAMILIES))

    def test_root_contract_is_deliberately_non_closing_and_schema_compatible(self) -> None:
        bundle = fixed_bundle()
        summary = validate_bundle(bundle)
        self.assertEqual(summary["receipt_count"], len(REQUIRED_FAMILIES))
        self.assertEqual(summary["attempt_count"], 2)
        closure = compile_contract_closure(bundle)
        closure_schema = json.loads((ROOT / "schemas/evidence-closure.v1.schema.json").read_text())
        self.assertTrue(set(closure_schema["required"]).issubset(closure))
        self.assertEqual(closure["schema"], CLOSURE_SCHEMA)
        self.assertEqual(closure["state"], "UNVERIFIABLE")
        self.assertFalse(closure["closed"])
        self.assertEqual(closure["as_of"], "2026-08-19T00:00:00Z")
        self.assertIsInstance(closure["as_of"], str)
        self.assertEqual(closure["run"]["authority"], "EVIDENCE_ONLY")
        self.assertEqual(closure["run"]["release_state"], "NOT_PERFORMED")

    def test_missing_observation_time_cannot_emit_schema_closure(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        for receipt in bundle["receipts"]:
            receipt["observed_at"] = None
        self.assert_code("CLOSURE_AS_OF_UNAVAILABLE", lambda: validate_bundle(bundle))

    def test_mutable_producer_subject_is_refused(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["receipts"][0]["producer"]["commit"] = "main"
        self.assert_code("MUTABLE_PRODUCER_SUBJECT", lambda: validate_bundle(bundle))

    def test_receipt_digest_mismatch_is_refused(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["receipts"][1]["payload"]["observation"] = "tampered"
        self.assert_code("RECEIPT_DIGEST_MISMATCH", lambda: validate_bundle(bundle))

    def test_missing_family_is_refused(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["receipts"][-1]["family"] = "SOURCE"
        self.assert_code("MISSING_RECEIPT_FAMILY", lambda: validate_bundle(bundle))

    def test_dropped_attempt_receipt_is_refused(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["receipts"].pop(5)
        self.assert_code("DROPPED_OR_REORDERED_RECEIPT", lambda: validate_bundle(bundle))

    def test_secret_value_key_is_refused_even_with_matching_digest(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        payload = {"raw_secret": "fixture-must-never-enter-evidence"}
        bundle["receipts"][2]["payload"] = payload
        bundle["receipts"][2]["payload_digest"] = sha256_text(canonical_json(payload))
        self.assert_code("SECRET_OR_PRIVATE_REASONING", lambda: validate_bundle(bundle))

    def test_private_reasoning_key_is_refused(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        payload = {"private_reasoning": "not durable evidence"}
        bundle["receipts"][2]["payload"] = payload
        bundle["receipts"][2]["payload_digest"] = sha256_text(canonical_json(payload))
        self.assert_code("SECRET_OR_PRIVATE_REASONING", lambda: validate_bundle(bundle))

    def test_deterministic_fixture_cannot_claim_human_pass(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        human = next(item for item in bundle["receipts"] if item["family"] == "HUMAN")
        human["state"] = "PASS"
        self.assert_code("DETERMINISTIC_AS_HUMAN_OR_RELEASE", lambda: validate_bundle(bundle))

    def test_verifier_cannot_promote_external_release(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["external_states"]["release"] = "PASS"
        self.assert_code("VERIFIER_SELF_PROMOTION", lambda: validate_bundle(bundle))

    def test_closure_vocabulary_cannot_fork(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["requested_closure_state"] = "TRUE"
        self.assert_code("CLOSURE_VOCABULARY_DRIFT", lambda: validate_bundle(bundle))

    def test_duplicate_receipt_identity_is_refused(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        bundle["receipts"][2]["receipt_id"] = bundle["receipts"][1]["receipt_id"]
        self.assert_code("DUPLICATE_RECEIPT_ID", lambda: validate_bundle(bundle))

    def test_one_attempt_cannot_hide_retry_denominator(self) -> None:
        bundle = mutated_copy(fixed_bundle())
        for item in bundle["receipts"]:
            item["attempt_id"] = "attempt-only"
        self.assert_code("ATTEMPT_DENOMINATOR_TOO_SMALL", lambda: validate_bundle(bundle))


if __name__ == "__main__":
    unittest.main()
