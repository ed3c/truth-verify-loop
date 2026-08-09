"""Typed contracts for the live truth-verification harness.

The module intentionally uses only the Python standard library so the MVP can run in
an isolated development container before a lakehouse backend is selected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

RISK_LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}
TEMPORALITY = {"static", "versioned", "dynamic", "ephemeral"}
RELATIONSHIPS = {"supports", "refutes", "context"}
CLOSURE_STATES = {"SUPPORTED", "REFUTED", "CONFLICTED", "STALE", "UNVERIFIABLE"}
SOURCE_CLASSES = {
    "official_doc",
    "official_release",
    "standard",
    "source_code",
    "first_party",
    "independent",
    "community",
    "unclassified",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when an input violates a standing harness contract."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ContractError(f"{field_name} must be an ISO-8601 timestamp") from exc
    else:
        raise ContractError(f"{field_name} must be a string timestamp or null")
    if parsed.tzinfo is None:
        raise ContractError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string or null")
    return value.strip()


@dataclass(frozen=True)
class Claim:
    claim_id: str
    statement: str
    risk: str
    temporality: str
    freshness_sla_seconds: int
    scope: dict[str, Any] = field(default_factory=dict)
    owner: str | None = None
    falsifier: str | None = None
    last_verified_at: datetime | None = None
    force_live_search: bool = False
    required_source_classes: tuple[str, ...] = ()
    trusted_domains: tuple[str, ...] = ()
    prior_state: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Claim":
        claim_id = _required_text(data, "claim_id")
        statement = _required_text(data, "statement")
        risk = _required_text(data, "risk").lower()
        temporality = _required_text(data, "temporality").lower()
        if risk not in RISK_LEVELS:
            raise ContractError(f"risk must be one of {sorted(RISK_LEVELS)}")
        if temporality not in TEMPORALITY:
            raise ContractError(f"temporality must be one of {sorted(TEMPORALITY)}")
        freshness = data.get("freshness_sla_seconds")
        if not isinstance(freshness, int) or isinstance(freshness, bool) or freshness <= 0:
            raise ContractError("freshness_sla_seconds must be a positive integer")
        scope = data.get("scope", {})
        if not isinstance(scope, dict):
            raise ContractError("scope must be an object")
        required = data.get("required_source_classes", [])
        if not isinstance(required, list) or not all(isinstance(x, str) and x for x in required):
            raise ContractError("required_source_classes must be an array of strings")
        invalid_classes = sorted(set(required) - SOURCE_CLASSES)
        if invalid_classes:
            raise ContractError(f"unknown required source classes: {invalid_classes}")
        domains = data.get("trusted_domains", [])
        if not isinstance(domains, list) or not all(isinstance(x, str) and x for x in domains):
            raise ContractError("trusted_domains must be an array of domain strings")
        prior_state = _optional_text(data, "prior_state")
        if prior_state is not None and prior_state not in CLOSURE_STATES:
            raise ContractError(f"prior_state must be one of {sorted(CLOSURE_STATES)}")
        force_live = data.get("force_live_search", False)
        if not isinstance(force_live, bool):
            raise ContractError("force_live_search must be boolean")
        return cls(
            claim_id=claim_id,
            statement=statement,
            risk=risk,
            temporality=temporality,
            freshness_sla_seconds=freshness,
            scope=dict(scope),
            owner=_optional_text(data, "owner"),
            falsifier=_optional_text(data, "falsifier"),
            last_verified_at=parse_timestamp(data.get("last_verified_at"), field_name="last_verified_at"),
            force_live_search=force_live,
            required_source_classes=tuple(required),
            trusted_domains=tuple(d.lower().strip(".") for d in domains),
            prior_state=prior_state,
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["last_verified_at"] = format_timestamp(self.last_verified_at)
        result["required_source_classes"] = list(self.required_source_classes)
        result["trusted_domains"] = list(self.trusted_domains)
        return result


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    claim_id: str
    source_uri: str
    source_class: str
    relationship: str
    quote: str
    retrieved_at: datetime
    content_sha256: str
    quote_sha256: str
    capture_scope: str
    provider_receipt_sha256: str
    title: str | None = None
    published_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_domain: str | None = None
    citation: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Evidence":
        source_uri = _required_text(data, "source_uri")
        parsed_uri = urlsplit(source_uri)
        if parsed_uri.scheme not in {"http", "https"} or not parsed_uri.hostname:
            raise ContractError("source_uri must be an absolute HTTP(S) URL")
        source_class = _required_text(data, "source_class")
        if source_class not in SOURCE_CLASSES:
            raise ContractError(f"source_class must be one of {sorted(SOURCE_CLASSES)}")
        relationship = _required_text(data, "relationship")
        if relationship not in RELATIONSHIPS:
            raise ContractError(f"relationship must be one of {sorted(RELATIONSHIPS)}")
        content_hash = _required_text(data, "content_sha256")
        quote_hash = _required_text(data, "quote_sha256")
        receipt_hash = _required_text(data, "provider_receipt_sha256")
        for key, value in {
            "content_sha256": content_hash,
            "quote_sha256": quote_hash,
            "provider_receipt_sha256": receipt_hash,
        }.items():
            if not SHA256_RE.fullmatch(value):
                raise ContractError(f"{key} must be a lowercase SHA-256 digest")
        quote = _required_text(data, "quote")
        citation = data.get("citation", {})
        if not isinstance(citation, dict):
            raise ContractError("citation must be an object")
        retrieved_at = parse_timestamp(data.get("retrieved_at"), field_name="retrieved_at")
        assert retrieved_at is not None
        return cls(
            evidence_id=_required_text(data, "evidence_id"),
            claim_id=_required_text(data, "claim_id"),
            source_uri=source_uri,
            source_class=source_class,
            relationship=relationship,
            quote=quote,
            retrieved_at=retrieved_at,
            content_sha256=content_hash,
            quote_sha256=quote_hash,
            capture_scope=_required_text(data, "capture_scope"),
            provider_receipt_sha256=receipt_hash,
            title=_optional_text(data, "title"),
            published_at=parse_timestamp(data.get("published_at"), field_name="published_at"),
            valid_from=parse_timestamp(data.get("valid_from"), field_name="valid_from"),
            valid_to=parse_timestamp(data.get("valid_to"), field_name="valid_to"),
            source_domain=(parsed_uri.hostname or "").lower(),
            citation=dict(citation),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for name in ("retrieved_at", "published_at", "valid_from", "valid_to"):
            result[name] = format_timestamp(getattr(self, name))
        return result

    def contract_failures(self) -> list[str]:
        failures: list[str] = []
        if sha256_text(self.quote) != self.quote_sha256:
            failures.append("quote digest does not match quote")
        if self.citation.get("quote_verified") is not True:
            failures.append("citation quote was not verified against captured source content")
        families = self.citation.get("semantic_verifier_families")
        if families is not None and (
            not isinstance(families, list)
            or not families
            or not all(isinstance(item, str) and item.strip() for item in families)
        ):
            failures.append("semantic_verifier_families must be a non-empty array of strings")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            failures.append("valid_from is after valid_to")
        return failures


@dataclass(frozen=True)
class SourceCandidate:
    source_uri: str
    quote: str
    relationship: str
    title: str | None = None
    published_at: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceCandidate":
        uri = _required_text(data, "source_uri")
        parsed = urlsplit(uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ContractError("candidate source_uri must be an absolute HTTP(S) URL")
        relationship = _required_text(data, "relationship")
        if relationship not in RELATIONSHIPS:
            raise ContractError(f"candidate relationship must be one of {sorted(RELATIONSHIPS)}")
        return cls(
            source_uri=uri,
            quote=_required_text(data, "quote"),
            relationship=relationship,
            title=_optional_text(data, "title"),
            published_at=_optional_text(data, "published_at"),
        )


@dataclass(frozen=True)
class SearchEnvelope:
    query: str
    candidates: tuple[SourceCandidate, ...]
    schema: str = "tvl.search-result.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SearchEnvelope":
        if data.get("schema") != "tvl.search-result.v1":
            raise ContractError("search envelope schema must be tvl.search-result.v1")
        raw_candidates = data.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise ContractError("search envelope candidates must be a non-empty array")
        return cls(
            query=_required_text(data, "query"),
            candidates=tuple(SourceCandidate.from_dict(item) for item in raw_candidates),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "query": self.query,
            "candidates": [asdict(candidate) for candidate in self.candidates],
        }


def ensure_unique_ids(items: Iterable[Evidence]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.evidence_id in seen:
            raise ContractError(f"duplicate evidence_id: {item.evidence_id}")
        seen.add(item.evidence_id)
