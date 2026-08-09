"""Temporal and source policy for deciding when live verification is mandatory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .model import Claim, ContractError, RISK_LEVELS, SOURCE_CLASSES, format_timestamp, parse_timestamp, utc_now

PRIMARY_CLASSES = {"official_doc", "official_release", "standard", "source_code", "first_party"}


@dataclass(frozen=True)
class VerificationDecision:
    required: bool
    mode: str
    reasons: tuple[str, ...]
    decided_at: datetime
    model_knowledge_cutoff: datetime | None
    freshness_deadline: datetime | None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["decided_at"] = format_timestamp(self.decided_at)
        result["model_knowledge_cutoff"] = format_timestamp(self.model_knowledge_cutoff)
        result["freshness_deadline"] = format_timestamp(self.freshness_deadline)
        result["reasons"] = list(self.reasons)
        return result


@dataclass(frozen=True)
class RiskRequirement:
    require_primary: bool
    min_independent_sources: int
    require_full_source_capture: bool
    min_semantic_verifier_families: int


class SourcePolicy:
    """Classifies domains independently of the search model's labels."""

    def __init__(
        self,
        *,
        domain_classes: Mapping[str, str] | None = None,
        risk_requirements: Mapping[str, RiskRequirement] | None = None,
        default_source_class: str = "unclassified",
        https_only: bool = True,
    ) -> None:
        if default_source_class not in SOURCE_CLASSES:
            raise ContractError(f"unknown default source class: {default_source_class}")
        classes: dict[str, str] = {}
        for domain, source_class in (domain_classes or {}).items():
            normalized = domain.lower().strip().strip(".")
            if not normalized or "/" in normalized:
                raise ContractError(f"invalid policy domain: {domain!r}")
            if source_class not in SOURCE_CLASSES:
                raise ContractError(f"unknown source class for {domain}: {source_class}")
            classes[normalized] = source_class
        self.domain_classes = classes
        self.default_source_class = default_source_class
        self.https_only = https_only
        defaults = {
            "low": RiskRequirement(False, 0, False, 0),
            "medium": RiskRequirement(True, 0, True, 1),
            "high": RiskRequirement(True, 1, True, 2),
            "critical": RiskRequirement(True, 2, True, 2),
        }
        defaults.update(risk_requirements or {})
        self.risk_requirements = defaults

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourcePolicy":
        domain_classes = data.get("domain_classes", {})
        if not isinstance(domain_classes, dict):
            raise ContractError("domain_classes must be an object")
        raw_risks = data.get("risk_requirements", {})
        if not isinstance(raw_risks, dict):
            raise ContractError("risk_requirements must be an object")
        requirements: dict[str, RiskRequirement] = {}
        for risk, raw in raw_risks.items():
            if risk not in RISK_LEVELS or not isinstance(raw, dict):
                raise ContractError(f"invalid risk requirement: {risk}")
            independent = raw.get("min_independent_sources", 0)
            if not isinstance(independent, int) or independent < 0:
                raise ContractError(f"{risk}.min_independent_sources must be a non-negative integer")
            semantic_families = raw.get("min_semantic_verifier_families", 0)
            if not isinstance(semantic_families, int) or semantic_families < 0:
                raise ContractError(
                    f"{risk}.min_semantic_verifier_families must be a non-negative integer"
                )
            require_primary = raw.get("require_primary", False)
            require_full_capture = raw.get("require_full_source_capture", False)
            if not isinstance(require_primary, bool):
                raise ContractError(f"{risk}.require_primary must be boolean")
            if not isinstance(require_full_capture, bool):
                raise ContractError(f"{risk}.require_full_source_capture must be boolean")
            requirements[risk] = RiskRequirement(
                require_primary=require_primary,
                min_independent_sources=independent,
                require_full_source_capture=require_full_capture,
                min_semantic_verifier_families=semantic_families,
            )
        https_only = data.get("https_only", True)
        if not isinstance(https_only, bool):
            raise ContractError("https_only must be boolean")
        return cls(
            domain_classes=domain_classes,
            risk_requirements=requirements,
            default_source_class=str(data.get("default_source_class", "unclassified")),
            https_only=https_only,
        )

    @classmethod
    def load(cls, path: Path) -> "SourcePolicy":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def classify(self, uri: str, *, claim: Claim | None = None) -> str:
        parsed = urlsplit(uri)
        if not parsed.hostname:
            return "unclassified"
        if self.https_only and parsed.scheme != "https":
            return "unclassified"
        hostname = parsed.hostname.lower().strip(".")
        candidates = sorted(self.domain_classes, key=len, reverse=True)
        for domain in candidates:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return self.domain_classes[domain]
        if claim and any(hostname == d or hostname.endswith(f".{d}") for d in claim.trusted_domains):
            # Claim-level trust is an explicit owner assertion when no global mapping exists.
            return "official_doc"
        return self.default_source_class

    def requirement_for(self, risk: str) -> RiskRequirement:
        try:
            return self.risk_requirements[risk]
        except KeyError as exc:
            raise ContractError(f"no source requirement configured for risk={risk}") from exc


def decide_live_search(
    claim: Claim,
    *,
    model_knowledge_cutoff: str | datetime | None,
    now: datetime | None = None,
) -> VerificationDecision:
    """Decide whether model memory can be used without a fresh retrieval.

    This is deliberately conservative: the model cutoff is provenance, not evidence. A
    current claim remains open until a source receipt satisfies its freshness contract.
    """

    current = now or utc_now()
    cutoff = parse_timestamp(model_knowledge_cutoff, field_name="model_knowledge_cutoff")
    reasons: list[str] = []
    deadline: datetime | None = None

    if claim.force_live_search:
        reasons.append("claim explicitly requires live search")
    if claim.temporality in {"dynamic", "ephemeral"}:
        reasons.append(f"{claim.temporality} claim cannot be closed from parametric memory")
    elif claim.temporality == "versioned":
        version = str(claim.scope.get("version", "")).strip().lower()
        if not version or version in {"latest", "current", "stable", "main", "head"}:
            reasons.append("versioned claim is not pinned to an immutable version")

    if claim.prior_state in {"CONFLICTED", "STALE", "UNVERIFIABLE"}:
        reasons.append(f"prior closure state is {claim.prior_state}")

    if claim.last_verified_at is None:
        reasons.append("claim has no prior verified timestamp")
    else:
        deadline = claim.last_verified_at + timedelta(seconds=claim.freshness_sla_seconds)
        if current > deadline:
            reasons.append("claim freshness SLA has expired")

    if cutoff is None:
        if RISK_LEVELS[claim.risk] >= RISK_LEVELS["high"]:
            reasons.append("model knowledge cutoff is unknown for a high-risk claim")
    elif cutoff < current and claim.temporality != "static":
        reasons.append("claim may have changed after the model knowledge cutoff")

    if claim.risk == "critical":
        reasons.append("critical claims always require fresh primary evidence")

    # Keep the reason set stable for deterministic manifests.
    reasons = list(dict.fromkeys(reasons))
    required = bool(reasons)
    if not required:
        mode = "OFFLINE_MEMORY_OK"
    elif claim.risk in {"high", "critical"} or claim.prior_state == "CONFLICTED":
        mode = "LIVE_MULTI_SOURCE"
    elif claim.risk == "medium" or claim.required_source_classes:
        mode = "LIVE_PRIMARY"
    else:
        mode = "LIVE_SEARCH"
    return VerificationDecision(
        required=required,
        mode=mode,
        reasons=tuple(reasons),
        decided_at=current,
        model_knowledge_cutoff=cutoff,
        freshness_deadline=deadline,
    )
