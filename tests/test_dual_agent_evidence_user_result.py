from __future__ import annotations

from copy import deepcopy
import unittest

from harness.dual_agent_evidence.contract import DualAgentEvidenceError
from harness.dual_agent_evidence.user_result import verify_user_result
from harness.model import canonical_json, sha256_text
from tests.test_dual_agent_evidence_contract import fixed_bundle


def _set_payload(receipt: dict, payload: dict) -> None:
    receipt["payload"] = payload
    receipt["payload_digest"] = sha256_text(canonical_json(payload))


def fixed_user_bundle() -> dict:
    bundle = fixed_bundle()
    provider = next(item for item in bundle["receipts"] if item["family"] == "PROVIDER_RUNTIME")
    _set_payload(
        provider,
        {
            "provider_result_digest": "a" * 64,
            "task_state": "NOT_EXERCISED",
            "user_result_claimed": False,
        },
    )
    route = next(item for item in bundle["receipts"] if item["family"] == "ROUTE_OBSERVATION")
    route["lane"] = "API"
    _set_payload(
        route,
        {
            "route_kind": "API",
            "evidence_lane": "API",
            "observation_digest": "b" * 64,
            "result_digest": "c" * 64,
            "provider_result_digest": "a" * 64,
            "user_result_claimed": False,
        },
    )
    user = next(item for item in bundle["receipts"] if item["family"] == "USER_RESULT")
    user["lane"] = "USER"
    _set_payload(
        user,
        {
            "expected_route": "API",
            "evidence_lane": "USER",
            "route_observation_digest": "b" * 64,
            "result_digest": "c" * 64,
            "user_observed": True,
            "backend_completion": "COMPLETED",
        },
    )
    cleanup = next(item for item in bundle["receipts"] if item["family"] == "CLEANUP")
    _set_payload(
        cleanup,
        {
            "independent_receipt": True,
            "related_result_digest": "c" * 64,
            "cleanup_state": "CLEAN",
            "residue": [],
        },
    )
    human = next(item for item in bundle["receipts"] if item["family"] == "HUMAN")
    _set_payload(human, {"inferred_from_deterministic": False})
    release = next(item for item in bundle["receipts"] if item["family"] == "RELEASE")
    _set_payload(release, {"inferred_from_deterministic": False})
    return bundle


class UserResultVerificationTest(unittest.TestCase):
    def assert_code(self, code: str, bundle: dict) -> None:
        with self.assertRaises(DualAgentEvidenceError) as caught:
            verify_user_result(bundle)
        self.assertEqual(caught.exception.code, code)

    def test_user_result_is_independent_from_backend_completion(self) -> None:
        finding = verify_user_result(fixed_user_bundle())
        self.assertTrue(finding["gate"])
        self.assertEqual(finding["route_kind"], "API")
        self.assertEqual(finding["live_user_result_state"], "NOT_EXERCISED")
        self.assertEqual(finding["release_state"], "NOT_PERFORMED")

    def test_backend_completion_cannot_proxy_user_observation(self) -> None:
        bundle = fixed_user_bundle()
        user = next(item for item in bundle["receipts"] if item["family"] == "USER_RESULT")
        payload = dict(user["payload"])
        payload["user_observed"] = False
        _set_payload(user, payload)
        self.assert_code("BACKEND_COMPLETE_AS_USER_SUCCESS", bundle)

    def test_browser_receipt_cannot_proxy_api_evidence(self) -> None:
        bundle = fixed_user_bundle()
        route = next(item for item in bundle["receipts"] if item["family"] == "ROUTE_OBSERVATION")
        route["lane"] = "BROWSER"
        self.assert_code("ROUTE_EVIDENCE_SUBSTITUTION", bundle)

    def test_api_lane_cannot_proxy_browser_route(self) -> None:
        bundle = fixed_user_bundle()
        route = next(item for item in bundle["receipts"] if item["family"] == "ROUTE_OBSERVATION")
        payload = dict(route["payload"])
        payload["route_kind"] = "BROWSER"
        _set_payload(route, payload)
        self.assert_code("ROUTE_EVIDENCE_SUBSTITUTION", bundle)

    def test_provider_cannot_claim_user_result(self) -> None:
        bundle = fixed_user_bundle()
        provider = next(item for item in bundle["receipts"] if item["family"] == "PROVIDER_RUNTIME")
        payload = dict(provider["payload"])
        payload["user_result_claimed"] = True
        _set_payload(provider, payload)
        self.assert_code("PROVIDER_AS_USER_RESULT", bundle)

    def test_route_cannot_claim_user_result(self) -> None:
        bundle = fixed_user_bundle()
        route = next(item for item in bundle["receipts"] if item["family"] == "ROUTE_OBSERVATION")
        payload = dict(route["payload"])
        payload["user_result_claimed"] = True
        _set_payload(route, payload)
        self.assert_code("ROUTE_AS_USER_RESULT", bundle)

    def test_provider_route_disagreement_is_visible(self) -> None:
        bundle = fixed_user_bundle()
        route = next(item for item in bundle["receipts"] if item["family"] == "ROUTE_OBSERVATION")
        payload = dict(route["payload"])
        payload["provider_result_digest"] = "d" * 64
        _set_payload(route, payload)
        self.assert_code("PROVIDER_ROUTE_DISAGREEMENT", bundle)

    def test_route_user_result_disagreement_is_visible(self) -> None:
        bundle = fixed_user_bundle()
        user = next(item for item in bundle["receipts"] if item["family"] == "USER_RESULT")
        payload = dict(user["payload"])
        payload["result_digest"] = "e" * 64
        _set_payload(user, payload)
        self.assert_code("USER_RESULT_ROUTE_DISAGREEMENT", bundle)

    def test_cleanup_failure_cannot_be_hidden(self) -> None:
        bundle = fixed_user_bundle()
        cleanup = next(item for item in bundle["receipts"] if item["family"] == "CLEANUP")
        payload = dict(cleanup["payload"])
        payload["cleanup_state"] = "UNKNOWN"
        _set_payload(cleanup, payload)
        self.assert_code("CLEANUP_NOT_CLOSED", bundle)

    def test_cleanup_residue_cannot_be_hidden(self) -> None:
        bundle = fixed_user_bundle()
        cleanup = next(item for item in bundle["receipts"] if item["family"] == "CLEANUP")
        payload = dict(cleanup["payload"])
        payload["residue"] = ["fixture-resource"]
        _set_payload(cleanup, payload)
        self.assert_code("CLEANUP_NOT_CLOSED", bundle)

    def test_task_success_cannot_infer_cleanup(self) -> None:
        bundle = fixed_user_bundle()
        cleanup = next(item for item in bundle["receipts"] if item["family"] == "CLEANUP")
        payload = dict(cleanup["payload"])
        payload["independent_receipt"] = False
        _set_payload(cleanup, payload)
        self.assert_code("CLEANUP_INFERRED_FROM_SUCCESS", bundle)

    def test_human_state_cannot_be_inferred(self) -> None:
        bundle = fixed_user_bundle()
        human = next(item for item in bundle["receipts"] if item["family"] == "HUMAN")
        payload = dict(human["payload"])
        payload["inferred_from_deterministic"] = True
        _set_payload(human, payload)
        self.assert_code("HUMAN_INFERRED_FROM_DETERMINISTIC", bundle)

    def test_release_state_cannot_be_inferred(self) -> None:
        bundle = fixed_user_bundle()
        release = next(item for item in bundle["receipts"] if item["family"] == "RELEASE")
        payload = dict(release["payload"])
        payload["inferred_from_deterministic"] = True
        _set_payload(release, payload)
        self.assert_code("RELEASE_INFERRED_FROM_DETERMINISTIC", bundle)


if __name__ == "__main__":
    unittest.main()
