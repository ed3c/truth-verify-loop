"""Cold blobs, append-only warm ledgers, and the rebuildable hot index."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .model import ContractError, canonical_json, format_timestamp, sha256_bytes, utc_now

ZONE_STREAMS: dict[str, set[str]] = {
    "bronze": {"blobs", "blob-receipts", "agent-sessions", "retrieval-events"},
    "silver": {"claims", "evidence", "documents", "chunks", "revisions"},
    "gold": {"closures", "coverage-ledger"},
}


class LakeError(RuntimeError):
    """Raised when canonical lake state is missing, corrupt, or non-append-only."""


class LakeBase:
    """Filesystem/SQLite backend implementing the local conformance profile."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.hot_db = self.root / "hot" / "index.sqlite3"
        self._claim_fts_enabled = False
        self._document_fts_enabled = False

    def initialize(self) -> None:
        for zone in ("bronze", "silver", "gold", "hot"):
            (self.root / zone).mkdir(parents=True, exist_ok=True)
        (self.root / "bronze" / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS current_claims (
                    claim_id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    temporality TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    source_class TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS evidence_claim_idx ON evidence(claim_id);

                CREATE TABLE IF NOT EXISTS current_closures (
                    claim_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    closed INTEGER NOT NULL,
                    expires_at TEXT,
                    payload_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS current_documents (
                    document_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL,
                    source_uri TEXT NOT NULL UNIQUE,
                    product TEXT,
                    version TEXT,
                    authority_class TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    structural_path_json TEXT NOT NULL,
                    text TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS document_chunks_doc_idx
                    ON document_chunks(document_id, ordinal);
                """
            )
            self._claim_fts_enabled = self._ensure_fts(
                conn,
                "claim_fts",
                "claim_id UNINDEXED, statement, scope",
            )
            self._document_fts_enabled = self._ensure_fts(
                conn,
                "document_fts",
                "chunk_id UNINDEXED, document_id UNINDEXED, text, symbols",
            )

    @staticmethod
    def _ensure_fts(conn: sqlite3.Connection, name: str, columns: str) -> bool:
        try:
            conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING fts5({columns})")
        except sqlite3.OperationalError:
            return False
        return True

    def _connect(self) -> sqlite3.Connection:
        self.hot_db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.hot_db)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def blob_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ContractError("blob digest must be a lowercase SHA-256 value")
        return self.root / "bronze" / "blobs" / "sha256" / digest[:2] / digest

    def store_blob(
        self,
        data: bytes,
        *,
        source_uri: str,
        media_type: str,
        capture_scope: str,
        retrieved_at: datetime | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        digest = sha256_bytes(data)
        target = self.blob_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256_bytes(target.read_bytes()) != digest:
                raise LakeError(f"existing blob has wrong digest: {target}")
        else:
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(data)
            if sha256_bytes(temporary.read_bytes()) != digest:
                temporary.unlink(missing_ok=True)
                raise LakeError("blob changed while being written")
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        receipt = {
            "content_sha256": digest,
            "size_bytes": len(data),
            "source_uri": source_uri,
            "media_type": media_type,
            "capture_scope": capture_scope,
            "retrieved_at": format_timestamp(retrieved_at or utc_now()),
            "relative_path": target.relative_to(self.root).as_posix(),
        }
        self.append_ledger("bronze", "blob-receipts", receipt)
        return receipt

    def ledger_path(self, zone: str, stream: str) -> Path:
        if zone not in ZONE_STREAMS:
            raise ContractError(f"unknown lake zone: {zone}")
        if stream not in ZONE_STREAMS[zone]:
            raise ContractError(f"stream {stream!r} is not registered in zone {zone!r}")
        return self.root / zone / f"{stream}.jsonl"

    @staticmethod
    def _event_hash(event_without_hash: dict[str, Any]) -> str:
        return sha256_bytes(canonical_json(event_without_hash).encode("utf-8"))

    def append_ledger(self, zone: str, stream: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        if not isinstance(payload, dict):
            raise ContractError("ledger payload must be an object")
        path = self.ledger_path(zone, stream)
        previous_hash: str | None = None
        sequence = 1
        if path.exists() and path.stat().st_size:
            existing_failures = self.verify_ledger(zone, stream)
            if existing_failures:
                raise LakeError(existing_failures[0])
            last: dict[str, Any] | None = None
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        last = json.loads(line)
            if last is None:
                raise LakeError(f"ledger contains no parseable event: {path}")
            previous_hash = last.get("event_hash")
            sequence = int(last.get("sequence", 0)) + 1
        event_without_hash = {
            "schema": "tvl.ledger-event.v1",
            "zone": zone,
            "stream": stream,
            "sequence": sequence,
            "recorded_at": format_timestamp(utc_now()),
            "previous_hash": previous_hash,
            "payload": payload,
        }
        event = dict(event_without_hash)
        event["event_hash"] = self._event_hash(event_without_hash)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
        return event

    def read_ledger(self, zone: str, stream: str) -> list[dict[str, Any]]:
        path = self.ledger_path(zone, stream)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LakeError(f"invalid JSON in {path}:{line_number}") from exc
                if not isinstance(value, dict):
                    raise LakeError(f"non-object event in {path}:{line_number}")
                events.append(value)
        return events

    def verify_ledger(self, zone: str, stream: str) -> list[str]:
        failures: list[str] = []
        previous: str | None = None
        for expected_sequence, event in enumerate(self.read_ledger(zone, stream), start=1):
            actual_hash = event.get("event_hash")
            unsigned = {key: value for key, value in event.items() if key != "event_hash"}
            expected_hash = self._event_hash(unsigned)
            if event.get("sequence") != expected_sequence:
                failures.append(f"{zone}/{stream}: sequence mismatch at {expected_sequence}")
            if event.get("previous_hash") != previous:
                failures.append(f"{zone}/{stream}: hash-chain mismatch at {expected_sequence}")
            if actual_hash != expected_hash:
                failures.append(f"{zone}/{stream}: event digest mismatch at {expected_sequence}")
            previous = actual_hash if isinstance(actual_hash, str) else None
        return failures

    def iter_canonical_files(self) -> Iterable[Path]:
        for zone in ("bronze", "silver", "gold"):
            zone_path = self.root / zone
            if not zone_path.exists():
                continue
            for path in sorted(zone_path.rglob("*")):
                if path.is_file() and not path.name.endswith(".tmp"):
                    yield path

    def write_manifest(self) -> Path:
        self.initialize()
        lines = []
        for path in self.iter_canonical_files():
            digest = sha256_bytes(path.read_bytes())
            lines.append(f"{digest}  {path.relative_to(self.root).as_posix()}")
        target = self.root / "MANIFEST.sha256"
        temporary = target.with_suffix(".tmp")
        temporary.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        temporary.replace(target)
        return target

    def verify_manifest(self) -> list[str]:
        path = self.root / "MANIFEST.sha256"
        if not path.exists():
            return ["MANIFEST.sha256 is missing"]
        failures: list[str] = []
        listed: set[str] = set()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                digest, relative = line.split("  ", 1)
            except ValueError:
                failures.append(f"manifest line {line_number} is malformed")
                continue
            listed.add(relative)
            target = (self.root / relative).resolve()
            try:
                target.relative_to(self.root)
            except ValueError:
                failures.append(f"manifest path escapes lake root: {relative}")
                continue
            if not target.is_file():
                failures.append(f"manifest target is missing: {relative}")
            elif sha256_bytes(target.read_bytes()) != digest:
                failures.append(f"manifest digest mismatch: {relative}")
        current = {path.relative_to(self.root).as_posix() for path in self.iter_canonical_files()}
        for relative in sorted(current - listed):
            failures.append(f"canonical file is absent from manifest: {relative}")
        return failures

    def verify_integrity(self, *, require_manifest: bool = True) -> list[str]:
        failures: list[str] = []
        blob_root = self.root / "bronze" / "blobs" / "sha256"
        if blob_root.exists():
            for path in sorted(blob_root.rglob("*")):
                if not path.is_file():
                    continue
                if path.name != sha256_bytes(path.read_bytes()):
                    failures.append(f"blob digest mismatch: {path.relative_to(self.root)}")
        for zone, streams in ZONE_STREAMS.items():
            for stream in sorted(streams):
                failures.extend(self.verify_ledger(zone, stream))
        if require_manifest:
            failures.extend(self.verify_manifest())
        return failures
