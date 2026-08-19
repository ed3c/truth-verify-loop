"""Independent source/artifact byte-readback verification.

Capture establishes provenance and byte identity only. It never upgrades a source or
screenshot into semantic support by itself. Manifest digests are not trusted as
readback: callers must supply the bytes that were independently captured/read back.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from harness.model import canonical_json, sha256_bytes, sha256_text

from .contract import DualAgentEvidenceError, validate_bundle

H40 = re.compile(r"^[0-9a-f]{40}$")
H64 = re.compile(r"^[0-9a-f]{64}$")
FULL_CAPTURE_SCOPES = {"repository_blob", "full_source", "full_http_response", "standard_snapshot"}


def _refuse(code: str, detail: str = "") -> None:
    raise DualAgentEvidenceError(code, detail)


def _h64(value: Any, code: str) -> str:
    if not isinstance(value, str) or not H64.fullmatch(value):
        _refuse(code)
    return value


def _payload(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = receipt.get("payload")
    if not isinstance(payload, Mapping):
        _refuse("ARTIFACT_PAYLOAD_INVALID")
    return payload


def source_digest(subject: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(dict(subject)))


def verify_source_artifacts(
    bundle: Mapping[str, Any],
    *,
    source_bytes: bytes,
    artifact_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    summary = validate_bundle(bundle)
    if not isinstance(source_bytes, bytes) or not source_bytes:
        _refuse("SOURCE_BYTES_MISSING")
    if not isinstance(artifact_bytes, Mapping):
        _refuse("ARTIFACT_READBACK_BYTES_INVALID")

    sources = [item for item in bundle["receipts"] if item["family"] == "SOURCE"]
    manifests = [item for item in bundle["receipts"] if item["family"] == "ARTIFACT"]
    if len(sources) != 1:
        _refuse("SOURCE_RECEIPT_CARDINALITY")
    if len(manifests) != 1:
        _refuse("ARTIFACT_RECEIPT_CARDINALITY")

    source_payload = _payload(sources[0])
    subject = source_payload.get("source_subject")
    if not isinstance(subject, Mapping):
        _refuse("SOURCE_SUBJECT_INVALID")
    repository = subject.get("repository")
    commit = subject.get("commit")
    tree = subject.get("tree")
    if not isinstance(repository, str) or "/" not in repository:
        _refuse("SOURCE_SUBJECT_INVALID")
    if not isinstance(commit, str) or not H40.fullmatch(commit) or not isinstance(tree, str) or not H40.fullmatch(tree):
        _refuse("MUTABLE_SOURCE_SUBJECT")
    subject_digest = _h64(source_payload.get("source_subject_digest"), "SOURCE_SUBJECT_DIGEST_INVALID")
    expected_digest = _h64(source_payload.get("expected_source_subject_digest"), "SOURCE_SUBJECT_DIGEST_INVALID")
    if subject_digest != expected_digest:
        _refuse("STALE_SOURCE_BINDING")
    capture_digest = _h64(source_payload.get("captured_bytes_digest"), "SOURCE_CAPTURE_DIGEST_INVALID")
    if source_payload.get("bytes_present") is not True:
        _refuse("SOURCE_BYTES_MISSING")
    if sha256_bytes(source_bytes) != capture_digest:
        _refuse("SOURCE_BYTE_READBACK_MISMATCH")
    if source_payload.get("capture_scope") not in FULL_CAPTURE_SCOPES:
        _refuse("SOURCE_CAPTURE_SCOPE_INCOMPLETE")
    if source_payload.get("semantic_support_claimed") is True:
        _refuse("SOURCE_CAPTURE_AS_SEMANTIC_PROOF")
    if source_payload.get("temporary_path") is not None:
        _refuse("TEMPORARY_PATH_AS_DURABLE_EVIDENCE")
    if subject_digest != source_digest(subject):
        _refuse("SOURCE_SUBJECT_DIGEST_MISMATCH")

    artifact_payload = _payload(manifests[0])
    artifacts = artifact_payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _refuse("ARTIFACT_DENOMINATOR_EMPTY")
    logical_names: set[str] = set()
    verified: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            _refuse("ARTIFACT_ENTRY_INVALID")
        name = artifact.get("logical_name")
        if not isinstance(name, str) or not name:
            _refuse("ARTIFACT_LOGICAL_NAME_INVALID")
        if name in logical_names:
            _refuse("DUPLICATE_ARTIFACT_LOGICAL_NAME", name)
        logical_names.add(name)
        declared = _h64(artifact.get("declared_digest"), "ARTIFACT_DIGEST_INVALID")
        readback = _h64(artifact.get("readback_digest"), "ARTIFACT_READBACK_DIGEST_INVALID")
        if artifact.get("bytes_present") is not True:
            _refuse("ARTIFACT_BYTES_MISSING", name)
        raw = artifact_bytes.get(name)
        if not isinstance(raw, bytes):
            _refuse("ARTIFACT_BYTES_MISSING", name)
        actual_digest = sha256_bytes(raw)
        if declared != readback or readback != actual_digest:
            _refuse("ARTIFACT_READBACK_DISAGREEMENT", name)
        size = artifact.get("bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            _refuse("ARTIFACT_SIZE_INVALID", name)
        if size != len(raw):
            _refuse("ARTIFACT_SIZE_READBACK_MISMATCH", name)
        durable_ref = artifact.get("durable_ref")
        if durable_ref != f"sha256:{actual_digest}":
            _refuse("ARTIFACT_DURABLE_REF_MISMATCH", name)
        if artifact.get("temporary_path") is not None:
            _refuse("TEMPORARY_PATH_AS_DURABLE_EVIDENCE", name)
        if artifact.get("semantic_proof") is True:
            if artifact.get("media_type") in {"image/png", "image/jpeg", "image/webp"}:
                _refuse("SCREENSHOT_AS_SEMANTIC_PROOF", name)
            _refuse("ARTIFACT_AS_SEMANTIC_PROOF", name)
        verified.append({"logical_name": name, "digest": actual_digest, "bytes": size})

    extra_readbacks = set(artifact_bytes) - logical_names
    if extra_readbacks:
        _refuse("UNDECLARED_ARTIFACT_BYTES", ",".join(sorted(extra_readbacks)))

    manifest_source = _h64(artifact_payload.get("source_subject_digest"), "ARTIFACT_SOURCE_BINDING_INVALID")
    if manifest_source != source_digest(subject):
        _refuse("ARTIFACT_SOURCE_BINDING_MISMATCH")

    finding = {
        "family": "DA-TV-ART",
        "gate": True,
        "bundle_digest": summary["bundle_digest"],
        "source_subject_digest": subject_digest,
        "captured_bytes_digest": capture_digest,
        "artifacts": sorted(verified, key=lambda item: item["logical_name"]),
        "receipt_ids": [sources[0]["receipt_id"], manifests[0]["receipt_id"]],
        "authority": "EVIDENCE_ONLY",
        "semantic_state": "NOT_EXERCISED",
        "user_result_state": "NOT_EXERCISED",
        "release_state": "NOT_PERFORMED",
        "evidence_ceiling": "DETERMINISTIC_SOURCE_ARTIFACT_READBACK_ONLY",
    }
    finding["finding_digest"] = sha256_text(canonical_json(finding))
    return finding
