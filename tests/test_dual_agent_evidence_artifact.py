from __future__ import annotations

from copy import deepcopy
import unittest

from harness.dual_agent_evidence.artifact import source_digest, verify_source_artifacts
from harness.dual_agent_evidence.contract import DualAgentEvidenceError
from harness.model import canonical_json, sha256_bytes, sha256_text
from tests.test_dual_agent_evidence_contract import fixed_bundle

SOURCE_BYTES = b"dual-agent source fixture bytes\n"
RESULT_BYTES = b'{"ok":true}\n'
SCREENSHOT_BYTES = b"not-a-real-png-but-stable-fixture"


def _set_payload(receipt: dict, payload: dict) -> None:
    receipt["payload"] = payload
    receipt["payload_digest"] = sha256_text(canonical_json(payload))


def fixed_artifact_bundle() -> tuple[dict, bytes, dict[str, bytes]]:
    bundle = fixed_bundle()
    subject = {
        "repository": "example/source-repo",
        "commit": "d" * 40,
        "tree": "e" * 40,
    }
    subject_hash = source_digest(subject)
    source = next(item for item in bundle["receipts"] if item["family"] == "SOURCE")
    _set_payload(
        source,
        {
            "source_subject": subject,
            "source_subject_digest": subject_hash,
            "expected_source_subject_digest": subject_hash,
            "captured_bytes_digest": sha256_bytes(SOURCE_BYTES),
            "bytes_present": True,
            "capture_scope": "repository_blob",
            "semantic_support_claimed": False,
            "temporary_path": None,
        },
    )

    artifacts = next(item for item in bundle["receipts"] if item["family"] == "ARTIFACT")
    result_digest = sha256_bytes(RESULT_BYTES)
    screenshot_digest = sha256_bytes(SCREENSHOT_BYTES)
    _set_payload(
        artifacts,
        {
            "source_subject_digest": subject_hash,
            "artifacts": [
                {
                    "logical_name": "result.json",
                    "declared_digest": result_digest,
                    "readback_digest": result_digest,
                    "bytes_present": True,
                    "bytes": len(RESULT_BYTES),
                    "durable_ref": f"sha256:{result_digest}",
                    "temporary_path": None,
                    "media_type": "application/json",
                    "semantic_proof": False,
                },
                {
                    "logical_name": "screenshot.png",
                    "declared_digest": screenshot_digest,
                    "readback_digest": screenshot_digest,
                    "bytes_present": True,
                    "bytes": len(SCREENSHOT_BYTES),
                    "durable_ref": f"sha256:{screenshot_digest}",
                    "temporary_path": None,
                    "media_type": "image/png",
                    "semantic_proof": False,
                },
            ],
        },
    )
    return bundle, SOURCE_BYTES, {"result.json": RESULT_BYTES, "screenshot.png": SCREENSHOT_BYTES}


class SourceArtifactVerificationTest(unittest.TestCase):
    def assert_code(self, code: str, bundle: dict, source_bytes: bytes, artifact_bytes: dict[str, bytes]) -> None:
        with self.assertRaises(DualAgentEvidenceError) as caught:
            verify_source_artifacts(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes)
        self.assertEqual(caught.exception.code, code)

    def test_exact_source_and_artifact_bytes_are_read_back(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        finding = verify_source_artifacts(bundle, source_bytes=source_bytes, artifact_bytes=artifact_bytes)
        self.assertTrue(finding["gate"])
        self.assertEqual(len(finding["artifacts"]), 2)
        self.assertEqual(finding["semantic_state"], "NOT_EXERCISED")

    def test_source_digest_without_matching_bytes_is_refused(self) -> None:
        bundle, _, artifact_bytes = fixed_artifact_bundle()
        self.assert_code("SOURCE_BYTE_READBACK_MISMATCH", bundle, b"changed source", artifact_bytes)

    def test_artifact_digest_without_bytes_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        artifact_bytes.pop("result.json")
        self.assert_code("ARTIFACT_BYTES_MISSING", bundle, source_bytes, artifact_bytes)

    def test_changed_artifact_bytes_are_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        artifact_bytes["result.json"] = b"changed"
        self.assert_code("ARTIFACT_READBACK_DISAGREEMENT", bundle, source_bytes, artifact_bytes)

    def test_duplicate_logical_name_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "ARTIFACT")
        payload = deepcopy(receipt["payload"])
        payload["artifacts"].append(deepcopy(payload["artifacts"][0]))
        _set_payload(receipt, payload)
        self.assert_code("DUPLICATE_ARTIFACT_LOGICAL_NAME", bundle, source_bytes, artifact_bytes)

    def test_mutable_source_subject_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "SOURCE")
        payload = deepcopy(receipt["payload"])
        payload["source_subject"]["commit"] = "main"
        _set_payload(receipt, payload)
        self.assert_code("MUTABLE_SOURCE_SUBJECT", bundle, source_bytes, artifact_bytes)

    def test_screenshot_presence_is_not_semantic_proof(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "ARTIFACT")
        payload = deepcopy(receipt["payload"])
        screenshot = next(item for item in payload["artifacts"] if item["logical_name"] == "screenshot.png")
        screenshot["semantic_proof"] = True
        _set_payload(receipt, payload)
        self.assert_code("SCREENSHOT_AS_SEMANTIC_PROOF", bundle, source_bytes, artifact_bytes)

    def test_temporary_path_is_not_durable_evidence(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "ARTIFACT")
        payload = deepcopy(receipt["payload"])
        payload["artifacts"][0]["temporary_path"] = "/tmp/result.json"
        _set_payload(receipt, payload)
        self.assert_code("TEMPORARY_PATH_AS_DURABLE_EVIDENCE", bundle, source_bytes, artifact_bytes)

    def test_stale_source_binding_is_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "SOURCE")
        payload = deepcopy(receipt["payload"])
        payload["expected_source_subject_digest"] = "9" * 64
        _set_payload(receipt, payload)
        self.assert_code("STALE_SOURCE_BINDING", bundle, source_bytes, artifact_bytes)

    def test_capture_does_not_self_authorize_semantics(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "SOURCE")
        payload = deepcopy(receipt["payload"])
        payload["semantic_support_claimed"] = True
        _set_payload(receipt, payload)
        self.assert_code("SOURCE_CAPTURE_AS_SEMANTIC_PROOF", bundle, source_bytes, artifact_bytes)

    def test_undeclared_readback_bytes_are_refused(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        artifact_bytes["hidden.bin"] = b"hidden"
        self.assert_code("UNDECLARED_ARTIFACT_BYTES", bundle, source_bytes, artifact_bytes)

    def test_size_must_match_readback_bytes(self) -> None:
        bundle, source_bytes, artifact_bytes = fixed_artifact_bundle()
        receipt = next(item for item in bundle["receipts"] if item["family"] == "ARTIFACT")
        payload = deepcopy(receipt["payload"])
        payload["artifacts"][0]["bytes"] += 1
        _set_payload(receipt, payload)
        self.assert_code("ARTIFACT_SIZE_READBACK_MISMATCH", bundle, source_bytes, artifact_bytes)


if __name__ == "__main__":
    unittest.main()
