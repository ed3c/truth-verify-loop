"""Versioned document and structural-chunk projection operations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .model import ContractError, canonical_json, format_timestamp, sha256_bytes


class DocumentLakeMixin:
    def current_document_for_uri(self, source_uri: str) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM current_documents WHERE source_uri = ?", (source_uri,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def upsert_document(self, snapshot: Any, chunks: Iterable[Any]) -> dict[str, Any]:
        self.initialize()
        payload = snapshot.to_dict()
        source_blob = self.blob_path(payload["content_sha256"])
        if not source_blob.is_file():
            raise ContractError(
                f"document source blob is missing from bronze storage: {payload['content_sha256']}"
            )
        if sha256_bytes(source_blob.read_bytes()) != payload["content_sha256"]:
            raise ContractError("document source blob digest mismatch")
        chunk_values = list(chunks)
        for chunk in chunk_values:
            if chunk.document_id != snapshot.document_id or chunk.snapshot_id != snapshot.snapshot_id:
                raise ContractError("document chunk does not belong to the supplied snapshot")

        previous_payload = self.current_document_for_uri(snapshot.source_uri)
        revision_event: dict[str, Any] | None = None
        if previous_payload and previous_payload.get("snapshot_id") != snapshot.snapshot_id:
            previous_snapshot_id = previous_payload.get("snapshot_id")
            declared_superseded = payload.get("supersedes_snapshot_id")
            if declared_superseded not in {None, previous_snapshot_id}:
                raise ContractError(
                    "document supersedes_snapshot_id does not match the current hot projection"
                )
            payload["supersedes_snapshot_id"] = previous_snapshot_id
            revision_event = self.append_ledger(
                "silver",
                "revisions",
                {
                    "operation": "SUPERSEDE",
                    "entity_type": "document_snapshot",
                    "document_id": snapshot.document_id,
                    "source_uri": snapshot.source_uri,
                    "previous_snapshot_id": previous_snapshot_id,
                    "snapshot_id": snapshot.snapshot_id,
                    "relation": "REVISES_OR_SUPERSEDES",
                    "previous_content_sha256": previous_payload.get("content_sha256"),
                    "content_sha256": payload["content_sha256"],
                    "observed_at": payload["retrieved_at"],
                },
            )

        event = self.append_ledger(
            "silver", "documents", {"operation": "UPSERT", "document": payload}
        )
        chunk_events: list[tuple[Any, dict[str, Any]]] = []
        for chunk in chunk_values:
            chunk_payload = chunk.to_dict()
            chunk_event = self.append_ledger(
                "silver", "chunks", {"operation": "UPSERT", "chunk": chunk_payload}
            )
            chunk_events.append((chunk, chunk_event))
        with self._connect() as conn:
            previous = conn.execute(
                "SELECT snapshot_id FROM current_documents WHERE document_id = ?",
                (snapshot.document_id,),
            ).fetchone()
            if previous and previous[0] != snapshot.snapshot_id:
                old_ids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT chunk_id FROM document_chunks WHERE document_id = ?",
                        (snapshot.document_id,),
                    )
                ]
                if self._document_fts_enabled:
                    for chunk_id in old_ids:
                        conn.execute("DELETE FROM document_fts WHERE chunk_id = ?", (chunk_id,))
                conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (snapshot.document_id,))
            conn.execute(
                """
                INSERT INTO current_documents
                    (document_id, snapshot_id, source_uri, product, version, authority_class,
                     retrieved_at, payload_json, event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    snapshot_id=excluded.snapshot_id,
                    source_uri=excluded.source_uri,
                    product=excluded.product,
                    version=excluded.version,
                    authority_class=excluded.authority_class,
                    retrieved_at=excluded.retrieved_at,
                    payload_json=excluded.payload_json,
                    event_hash=excluded.event_hash
                """,
                (
                    snapshot.document_id,
                    snapshot.snapshot_id,
                    snapshot.source_uri,
                    snapshot.product,
                    snapshot.version,
                    snapshot.authority_class,
                    format_timestamp(snapshot.retrieved_at),
                    canonical_json(payload),
                    event["event_hash"],
                ),
            )
            for chunk, chunk_event in chunk_events:
                chunk_payload = chunk.to_dict()
                conn.execute(
                    """
                    INSERT INTO document_chunks
                        (chunk_id, document_id, snapshot_id, ordinal, structural_path_json,
                         text, symbols_json, payload_json, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        document_id=excluded.document_id,
                        snapshot_id=excluded.snapshot_id,
                        ordinal=excluded.ordinal,
                        structural_path_json=excluded.structural_path_json,
                        text=excluded.text,
                        symbols_json=excluded.symbols_json,
                        payload_json=excluded.payload_json,
                        event_hash=excluded.event_hash
                    """,
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.snapshot_id,
                        chunk.ordinal,
                        canonical_json(list(chunk.structural_path)),
                        chunk.text,
                        canonical_json(list(chunk.symbols)),
                        canonical_json(chunk_payload),
                        chunk_event["event_hash"],
                    ),
                )
                if self._document_fts_enabled:
                    conn.execute("DELETE FROM document_fts WHERE chunk_id = ?", (chunk.chunk_id,))
                    conn.execute(
                        "INSERT INTO document_fts(chunk_id, document_id, text, symbols) VALUES (?, ?, ?, ?)",
                        (chunk.chunk_id, chunk.document_id, chunk.text, " ".join(chunk.symbols)),
                    )
        return {
            "document_event_hash": event["event_hash"],
            "chunk_event_hashes": [item[1]["event_hash"] for item in chunk_events],
            "revision_event_hash": revision_event["event_hash"] if revision_event else None,
        }

    def search_documents(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        self.initialize()
        if not query.strip():
            return []
        with self._connect() as conn:
            rows: list[tuple[str]] = []
            if self._document_fts_enabled:
                try:
                    rows = conn.execute(
                        "SELECT chunk_id FROM document_fts WHERE document_fts MATCH ? LIMIT ?",
                        (query, limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                rows = conn.execute(
                    "SELECT chunk_id FROM document_chunks WHERE lower(text) LIKE ? LIMIT ?",
                    (f"%{query.lower()}%", limit),
                ).fetchall()
            results: list[dict[str, Any]] = []
            for (chunk_id,) in rows:
                row = conn.execute(
                    """
                    SELECT c.payload_json, d.payload_json
                    FROM document_chunks c
                    JOIN current_documents d ON d.document_id = c.document_id
                    WHERE c.chunk_id = ?
                    """,
                    (chunk_id,),
                ).fetchone()
                if row:
                    results.append({"chunk": json.loads(row[0]), "document": json.loads(row[1])})
        return results
