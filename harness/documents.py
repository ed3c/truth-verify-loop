"""Versioned document-memory contracts and deterministic chunking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urldefrag, urlsplit, urlunsplit

from .model import ContractError, canonical_json, format_timestamp, parse_timestamp, sha256_text

SYMBOL_RE = re.compile(
    r"(?<![\w-])(?:--[a-z0-9][a-z0-9-]*|[A-Za-z_][A-Za-z0-9_]*(?:[.:/][A-Za-z_][A-Za-z0-9_-]*)+|[A-Z][A-Z0-9_]{2,})(?![\w-])"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def canonicalize_uri(uri: str) -> str:
    clean, _fragment = urldefrag(uri)
    parsed = urlsplit(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ContractError("document source_uri must be an absolute HTTP(S) URL")
    hostname = parsed.hostname.lower()
    port = parsed.port
    netloc = hostname
    if port and not ((parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)):
        netloc = f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


@dataclass(frozen=True)
class DocumentSnapshot:
    document_id: str
    snapshot_id: str
    source_uri: str
    source_type: str
    authority_class: str
    media_type: str
    content_sha256: str
    retrieved_at: datetime
    capture_scope: str
    title: str | None = None
    product: str | None = None
    version: str | None = None
    release_channel: str | None = None
    commit_sha: str | None = None
    language: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_snapshot_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_capture(
        cls,
        *,
        source_uri: str,
        source_type: str,
        authority_class: str,
        media_type: str,
        content_sha256: str,
        retrieved_at: str | datetime,
        capture_scope: str,
        title: str | None = None,
        scope: Mapping[str, Any] | None = None,
        supersedes_snapshot_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "DocumentSnapshot":
        canonical_uri = canonicalize_uri(source_uri)
        document_id = f"doc-{sha256_text(canonical_uri)[:24]}"
        snapshot_id = f"snap-{sha256_text(document_id + ':' + content_sha256)[:24]}"
        parsed_retrieved = parse_timestamp(retrieved_at, field_name="retrieved_at")
        assert parsed_retrieved is not None
        scope_data = dict(scope or {})
        return cls(
            document_id=document_id,
            snapshot_id=snapshot_id,
            source_uri=canonical_uri,
            source_type=source_type,
            authority_class=authority_class,
            media_type=media_type,
            content_sha256=content_sha256,
            retrieved_at=parsed_retrieved,
            capture_scope=capture_scope,
            title=title,
            product=_as_optional_string(scope_data.get("product")),
            version=_as_optional_string(scope_data.get("version")),
            release_channel=_as_optional_string(scope_data.get("channel")),
            commit_sha=_as_optional_string(scope_data.get("commit_sha")),
            language=_as_optional_string(scope_data.get("language")),
            valid_from=parse_timestamp(scope_data.get("valid_from"), field_name="valid_from"),
            valid_to=parse_timestamp(scope_data.get("valid_to"), field_name="valid_to"),
            supersedes_snapshot_id=supersedes_snapshot_id,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for name in ("retrieved_at", "valid_from", "valid_to"):
            result[name] = format_timestamp(getattr(self, name))
        return result


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    snapshot_id: str
    ordinal: int
    structural_path: tuple[str, ...]
    text: str
    text_sha256: str
    char_start: int
    char_end: int
    token_estimate: int
    symbols: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["structural_path"] = list(self.structural_path)
        result["symbols"] = list(self.symbols)
        return result


def _as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_symbols(text: str, *, limit: int = 40) -> tuple[str, ...]:
    values = sorted(dict.fromkeys(SYMBOL_RE.findall(text)))
    return tuple(values[:limit])


def _sections(text: str) -> list[tuple[tuple[str, ...], str]]:
    """Split Markdown-like text into heading-aware blocks without semantic inference."""

    heading_stack: list[str] = []
    blocks: list[tuple[tuple[str, ...], str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            value = "\n".join(paragraph).strip()
            if value:
                blocks.append((tuple(heading_stack), value))
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(title)
            continue
        if not line.strip():
            flush()
        else:
            paragraph.append(line)
    flush()
    if not blocks and text.strip():
        blocks.append(((), text.strip()))
    return blocks


def chunk_document(
    snapshot: DocumentSnapshot,
    text: str,
    *,
    max_chars: int = 1800,
    overlap_chars: int = 180,
) -> list[DocumentChunk]:
    if max_chars < 256:
        raise ContractError("max_chars must be at least 256")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ContractError("overlap_chars must be non-negative and smaller than max_chars")
    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[DocumentChunk] = []
    cursor = 0
    ordinal = 0
    for structural_path, block in _sections(normalized):
        search_from = cursor
        block_start = normalized.find(block, search_from)
        if block_start < 0:
            block_start = search_from
        offset = 0
        while offset < len(block):
            end = min(len(block), offset + max_chars)
            if end < len(block):
                break_at = block.rfind(" ", offset, end)
                if break_at > offset + max_chars // 2:
                    end = break_at
            piece = block[offset:end].strip()
            if piece:
                local_start = block.find(piece, offset, end + 1)
                char_start = block_start + max(local_start, offset)
                char_end = char_start + len(piece)
                material = canonical_json(
                    {
                        "snapshot_id": snapshot.snapshot_id,
                        "ordinal": ordinal,
                        "structural_path": structural_path,
                        "text": piece,
                    }
                )
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"chunk-{sha256_text(material)[:24]}",
                        document_id=snapshot.document_id,
                        snapshot_id=snapshot.snapshot_id,
                        ordinal=ordinal,
                        structural_path=structural_path,
                        text=piece,
                        text_sha256=sha256_text(piece),
                        char_start=char_start,
                        char_end=char_end,
                        token_estimate=max(1, (len(piece) + 3) // 4),
                        symbols=_extract_symbols(piece),
                    )
                )
                ordinal += 1
            if end >= len(block):
                break
            offset = max(offset + 1, end - overlap_chars)
        cursor = block_start + len(block)
    return chunks


def chunk_for_span(chunks: Iterable[DocumentChunk], start: int, end: int) -> DocumentChunk | None:
    best: DocumentChunk | None = None
    best_overlap = 0
    for chunk in chunks:
        overlap = max(0, min(end, chunk.char_end) - max(start, chunk.char_start))
        if overlap > best_overlap:
            best = chunk
            best_overlap = overlap
    return best
