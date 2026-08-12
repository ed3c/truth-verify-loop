"""Deterministic replay of canonical ledgers into the disposable hot index."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .model import Claim, ContractError, Evidence, canonical_json, sha256_bytes, sha256_text


class RebuildLakeMixin:
    """Rebuild SQLite/FTS state without appending or rewriting canonical ledgers."""

    @staticmethod
    def _event_payload(event: Mapping[str, Any], stream: str) -> tuple[str, dict[str, Any]]:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ContractError(f"{stream} ledger event has no object payload")
        operation = payload.get("operation")
        if operation not in {"UPSERT", "DELETE"}:
            raise ContractError(f"{stream} ledger operation must be UPSERT or DELETE")
        event_hash = event.get("event_hash")
        if not isinstance(event_hash, str) or len(event_hash) != 64:
            raise ContractError(f"{stream} ledger event has no valid event_hash")
        return event_hash, payload

    def _require_blob(self, digest: str, *, label: str) -> None:
        path = self.blob_path(digest)
        if not path.is_file():
            raise ContractError(f"{label} blob is missing from bronze storage: {digest}")
        if sha256_bytes(path.read_bytes()) != digest:
            raise ContractError(f"{label} blob digest mismatch: {digest}")

    def _load_claim_projection(self) -> dict[str, tuple[Claim, str]]:
        current: dict[str, tuple[Claim, str]] = {}
        for event in self.read_ledger("silver", "claims"):
            event_hash, payload = self._event_payload(event, "claims")
            raw = payload.get("claim")
            if payload["operation"] == "DELETE":
                claim_id = payload.get("claim_id")
                if not isinstance(claim_id, str) or not claim_id:
                    raise ContractError("claims DELETE requires claim_id")
                current.pop(claim_id, None)
                continue
            if not isinstance(raw, dict):
                raise ContractError("claims UPSERT requires a claim object")
            claim = Claim.from_dict(raw)
            current[claim.claim_id] = (claim, event_hash)
        return current

    def _load_evidence_projection(self) -> dict[str, tuple[Evidence, str]]:
        current: dict[str, tuple[Evidence, str]] = {}
        for event in self.read_ledger("silver", "evidence"):
            event_hash, payload = self._event_payload(event, "evidence")
            if payload["operation"] == "DELETE":
                evidence_id = payload.get("evidence_id")
                if not isinstance(evidence_id, str) or not evidence_id:
                    raise ContractError("evidence DELETE requires evidence_id")
                current.pop(evidence_id, None)
                continue
            raw = payload.get("evidence")
            if not isinstance(raw, dict):
                raise ContractError("evidence UPSERT requires an evidence object")
            evidence = Evidence.from_dict(raw)
            failures = evidence.contract_failures()
            if failures:
                raise ContractError(
                    f"evidence {evidence.evidence_id} is invalid during replay: "
                    + "; ".join(failures)
                )
            self._require_blob(evidence.content_sha256, label="source")
            self._require_blob(evidence.provider_receipt_sha256, label="provider receipt")
            current[evidence.evidence_id] = (evidence, event_hash)
        return current

    def _load_document_projection(self) -> dict[str, tuple[dict[str, Any], str]]:
        current: dict[str, tuple[dict[str, Any], str]] = {}
        required = {
            "document_id",
            "snapshot_id",
            "source_uri",
            "authority_class",
            "retrieved_at",
            "content_sha256",
        }
        for event in self.read_ledger("silver", "documents"):
            event_hash, payload = self._event_payload(event, "documents")
            if payload["operation"] == "DELETE":
                document_id = payload.get("document_id")
                if not isinstance(document_id, str) or not document_id:
                    raise ContractError("documents DELETE requires document_id")
                current.pop(document_id, None)
                continue
            raw = payload.get("document")
            if not isinstance(raw, dict) or not required.issubset(raw):
                raise ContractError("documents UPSERT has an incomplete document object")
            document_id = raw["document_id"]
            snapshot_id = raw["snapshot_id"]
            digest = raw["content_sha256"]
            if not all(isinstance(value, str) and value for value in (document_id, snapshot_id, digest)):
                raise ContractError("document identity and content digest must be strings")
            self._require_blob(digest, label="document source")
            current[document_id] = (dict(raw), event_hash)
        return current

    def _load_chunk_projection(self) -> dict[str, tuple[dict[str, Any], str]]:
        current: dict[str, tuple[dict[str, Any], str]] = {}
        required = {
            "chunk_id",
            "document_id",
            "snapshot_id",
            "ordinal",
            "structural_path",
            "text",
            "text_sha256",
            "symbols",
        }
        for event in self.read_ledger("silver", "chunks"):
            event_hash, payload = self._event_payload(event, "chunks")
            if payload["operation"] == "DELETE":
                chunk_id = payload.get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id:
                    raise ContractError("chunks DELETE requires chunk_id")
                current.pop(chunk_id, None)
                continue
            raw = payload.get("chunk")
            if not isinstance(raw, dict) or not required.issubset(raw):
                raise ContractError("chunks UPSERT has an incomplete chunk object")
            chunk_id = raw["chunk_id"]
            text = raw["text"]
            if not isinstance(chunk_id, str) or not isinstance(text, str) or not text:
                raise ContractError("chunk identity and text must be non-empty strings")
            if raw.get("text_sha256") != sha256_text(text):
                raise ContractError(f"chunk text digest mismatch: {chunk_id}")
            current[chunk_id] = (dict(raw), event_hash)
        return current

    def _load_closure_projection(self) -> dict[str, tuple[dict[str, Any], str]]:
        current: dict[str, tuple[dict[str, Any], str]] = {}
        states = {"SUPPORTED", "REFUTED", "CONFLICTED", "STALE", "UNVERIFIABLE"}
        for event in self.read_ledger("gold", "closures"):
            event_hash, payload = self._event_payload(event, "closures")
            if payload["operation"] == "DELETE":
                claim_id = payload.get("claim_id")
                if not isinstance(claim_id, str) or not claim_id:
                    raise ContractError("closures DELETE requires claim_id")
                current.pop(claim_id, None)
                continue
            raw = payload.get("closure")
            if not isinstance(raw, dict):
                raise ContractError("closures UPSERT requires a closure object")
            claim_id = raw.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id:
                raise ContractError("closure claim_id must be a non-empty string")
            if raw.get("state") not in states or not isinstance(raw.get("closed"), bool):
                raise ContractError(f"closure is invalid during replay: {claim_id}")
            current[claim_id] = (dict(raw), event_hash)
        return current

    def rebuild_hot(self, *, require_manifest: bool = True) -> dict[str, Any]:
        """Validate canonical storage, then replay its latest state into a new SQLite file."""

        failures = self.verify_integrity(require_manifest=require_manifest)
        if failures:
            raise self._lake_error_type()("canonical lake integrity failed: " + failures[0])

        claims = self._load_claim_projection()
        evidence = self._load_evidence_projection()
        documents = self._load_document_projection()
        chunks = self._load_chunk_projection()
        closures = self._load_closure_projection()

        current_snapshot = {
            document_id: value[0]["snapshot_id"] for document_id, value in documents.items()
        }
        current_chunks = {
            chunk_id: value
            for chunk_id, value in chunks.items()
            if value[0].get("document_id") in current_snapshot
            and value[0].get("snapshot_id")
            == current_snapshot[value[0]["document_id"]]
        }

        for suffix in ("", "-wal", "-shm"):
            path = self.hot_db if not suffix else self.hot_db.with_name(self.hot_db.name + suffix)
            path.unlink(missing_ok=True)
        self.initialize()

        with self._connect() as conn:
            for claim, event_hash in claims.values():
                payload = claim.to_dict()
                conn.execute(
                    """
                    INSERT INTO current_claims
                        (claim_id, statement, risk, temporality, payload_json, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.claim_id,
                        claim.statement,
                        claim.risk,
                        claim.temporality,
                        canonical_json(payload),
                        event_hash,
                    ),
                )
                if self._claim_fts_enabled:
                    conn.execute(
                        "INSERT INTO claim_fts(claim_id, statement, scope) VALUES (?, ?, ?)",
                        (claim.claim_id, claim.statement, canonical_json(payload.get("scope", {}))),
                    )

            for item, event_hash in evidence.values():
                payload = item.to_dict()
                conn.execute(
                    """
                    INSERT INTO evidence
                        (evidence_id, claim_id, source_uri, relationship, source_class,
                         retrieved_at, payload_json, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.evidence_id,
                        item.claim_id,
                        item.source_uri,
                        item.relationship,
                        item.source_class,
                        payload["retrieved_at"],
                        canonical_json(payload),
                        event_hash,
                    ),
                )

            for closure, event_hash in closures.values():
                conn.execute(
                    """
                    INSERT INTO current_closures
                        (claim_id, state, closed, expires_at, payload_json, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        closure["claim_id"],
                        closure["state"],
                        1 if closure["closed"] else 0,
                        closure.get("expires_at"),
                        canonical_json(closure),
                        event_hash,
                    ),
                )

            for document, event_hash in documents.values():
                conn.execute(
                    """
                    INSERT INTO current_documents
                        (document_id, snapshot_id, source_uri, product, version, authority_class,
                         retrieved_at, payload_json, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document["document_id"],
                        document["snapshot_id"],
                        document["source_uri"],
                        document.get("product"),
                        document.get("version"),
                        document["authority_class"],
                        document["retrieved_at"],
                        canonical_json(document),
                        event_hash,
                    ),
                )

            for chunk, event_hash in current_chunks.values():
                conn.execute(
                    """
                    INSERT INTO document_chunks
                        (chunk_id, document_id, snapshot_id, ordinal, structural_path_json,
                         text, symbols_json, payload_json, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk["chunk_id"],
                        chunk["document_id"],
                        chunk["snapshot_id"],
                        chunk["ordinal"],
                        canonical_json(chunk["structural_path"]),
                        chunk["text"],
                        canonical_json(chunk["symbols"]),
                        canonical_json(chunk),
                        event_hash,
                    ),
                )
                if self._document_fts_enabled:
                    conn.execute(
                        "INSERT INTO document_fts(chunk_id, document_id, text, symbols) VALUES (?, ?, ?, ?)",
                        (
                            chunk["chunk_id"],
                            chunk["document_id"],
                            chunk["text"],
                            " ".join(chunk["symbols"]),
                        ),
                    )

        return {
            "status": "PASS",
            "claims": len(claims),
            "evidence": len(evidence),
            "closures": len(closures),
            "documents": len(documents),
            "chunks": len(current_chunks),
            "hot_db": self.hot_db.as_posix(),
        }

    @staticmethod
    def _lake_error_type():
        # Imported lazily to avoid a circular dependency with the facade module.
        from .lake_base import LakeError

        return LakeError
