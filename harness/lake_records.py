"""Claim, evidence, and closure operations for warm and hot memory."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .model import Claim, ContractError, Evidence, canonical_json, sha256_bytes


class RecordLakeMixin:
    def upsert_claim(self, claim: Claim) -> dict[str, Any]:
        self.initialize()
        payload = claim.to_dict()
        event = self.append_ledger(
            "silver", "claims", {"operation": "UPSERT", "claim": payload}
        )
        scope_text = canonical_json(payload.get("scope", {}))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO current_claims
                    (claim_id, statement, risk, temporality, payload_json, event_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    statement=excluded.statement,
                    risk=excluded.risk,
                    temporality=excluded.temporality,
                    payload_json=excluded.payload_json,
                    event_hash=excluded.event_hash
                """,
                (
                    claim.claim_id,
                    claim.statement,
                    claim.risk,
                    claim.temporality,
                    canonical_json(payload),
                    event["event_hash"],
                ),
            )
            if self._claim_fts_enabled:
                conn.execute("DELETE FROM claim_fts WHERE claim_id = ?", (claim.claim_id,))
                conn.execute(
                    "INSERT INTO claim_fts(claim_id, statement, scope) VALUES (?, ?, ?)",
                    (claim.claim_id, claim.statement, scope_text),
                )
        return event

    def current_claim(self, claim_id: str) -> Claim | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM current_claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return Claim.from_dict(json.loads(row[0])) if row else None

    def upsert_evidence(self, evidence: Evidence) -> dict[str, Any]:
        self.initialize()
        failures = evidence.contract_failures()
        if failures:
            raise ContractError("invalid evidence: " + "; ".join(failures))
        for label, digest in (
            ("source", evidence.content_sha256),
            ("provider receipt", evidence.provider_receipt_sha256),
        ):
            path = self.blob_path(digest)
            if not path.is_file():
                raise ContractError(f"{label} blob is missing from bronze storage: {digest}")
            if sha256_bytes(path.read_bytes()) != digest:
                raise ContractError(f"{label} blob digest mismatch: {digest}")
        payload = evidence.to_dict()
        event = self.append_ledger(
            "silver", "evidence", {"operation": "UPSERT", "evidence": payload}
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence
                    (evidence_id, claim_id, source_uri, relationship, source_class,
                     retrieved_at, payload_json, event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    claim_id=excluded.claim_id,
                    source_uri=excluded.source_uri,
                    relationship=excluded.relationship,
                    source_class=excluded.source_class,
                    retrieved_at=excluded.retrieved_at,
                    payload_json=excluded.payload_json,
                    event_hash=excluded.event_hash
                """,
                (
                    evidence.evidence_id,
                    evidence.claim_id,
                    evidence.source_uri,
                    evidence.relationship,
                    evidence.source_class,
                    payload["retrieved_at"],
                    canonical_json(payload),
                    event["event_hash"],
                ),
            )
        return event

    def evidence_for_claim(self, claim_id: str) -> list[Evidence]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM evidence WHERE claim_id = ? ORDER BY retrieved_at, evidence_id",
                (claim_id,),
            ).fetchall()
        return [Evidence.from_dict(json.loads(row[0])) for row in rows]

    def record_closure(self, closure: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        claim_id = closure.get("claim_id")
        state = closure.get("state")
        closed = closure.get("closed")
        if not isinstance(claim_id, str) or not claim_id:
            raise ContractError("closure claim_id must be a non-empty string")
        if state not in {"SUPPORTED", "REFUTED", "CONFLICTED", "STALE", "UNVERIFIABLE"}:
            raise ContractError("closure state is invalid")
        if not isinstance(closed, bool):
            raise ContractError("closure closed must be boolean")
        event = self.append_ledger(
            "gold", "closures", {"operation": "UPSERT", "closure": closure}
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO current_closures
                    (claim_id, state, closed, expires_at, payload_json, event_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    state=excluded.state,
                    closed=excluded.closed,
                    expires_at=excluded.expires_at,
                    payload_json=excluded.payload_json,
                    event_hash=excluded.event_hash
                """,
                (
                    claim_id,
                    state,
                    1 if closed else 0,
                    closure.get("expires_at"),
                    canonical_json(closure),
                    event["event_hash"],
                ),
            )
        return event

    def current_closure(self, claim_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM current_closures WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def search_records(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        self.initialize()
        value = query.strip()
        if not value:
            return []
        claim_ids: list[str] = []
        with self._connect() as conn:
            if self._claim_fts_enabled:
                try:
                    claim_ids = [
                        row[0]
                        for row in conn.execute(
                            "SELECT claim_id FROM claim_fts WHERE claim_fts MATCH ? LIMIT ?",
                            (value, limit),
                        ).fetchall()
                    ]
                except sqlite3.OperationalError:
                    claim_ids = []
            if not claim_ids:
                claim_ids = [
                    row[0]
                    for row in conn.execute(
                        """
                        SELECT claim_id FROM current_claims
                        WHERE lower(statement) LIKE ? OR lower(payload_json) LIKE ?
                        LIMIT ?
                        """,
                        (f"%{value.lower()}%", f"%{value.lower()}%", limit),
                    ).fetchall()
                ]
            results: list[dict[str, Any]] = []
            for claim_id in claim_ids:
                claim_row = conn.execute(
                    "SELECT payload_json FROM current_claims WHERE claim_id = ?", (claim_id,)
                ).fetchone()
                closure_row = conn.execute(
                    "SELECT payload_json FROM current_closures WHERE claim_id = ?", (claim_id,)
                ).fetchone()
                evidence_rows = conn.execute(
                    "SELECT payload_json FROM evidence WHERE claim_id = ? ORDER BY retrieved_at DESC",
                    (claim_id,),
                ).fetchall()
                if claim_row:
                    results.append(
                        {
                            "claim": json.loads(claim_row[0]),
                            "closure": json.loads(closure_row[0]) if closure_row else None,
                            "evidence": [json.loads(row[0]) for row in evidence_rows],
                        }
                    )
        return results

    def search_hot(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        return {
            "records": self.search_records(query, limit=limit),
            "documents": self.search_documents(query, limit=limit),
        }
