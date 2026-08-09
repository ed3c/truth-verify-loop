"""Deterministic evidence-closure engine.

The engine never emits a scalar "truth score". It records explicit gates, missing
evidence, conflicts, and freshness so a later source revision can overturn the closure.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit

from .model import Claim, Evidence, ensure_unique_ids, format_timestamp, utc_now
from .policy import PRIMARY_CLASSES, SourcePolicy

FULL_CAPTURE_SCOPES = {"full_source", "full_http_response", "repository_blob", "standard_snapshot"}


def _domain(evidence: Evidence) -> str:
    return evidence.source_domain or (urlsplit(evidence.source_uri).hostname or "").lower()


def close_claim(
    claim: Claim,
    evidence_items: Iterable[Evidence],
    *,
    policy: SourcePolicy,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or utc_now()
    evidence = list(evidence_items)
    ensure_unique_ids(evidence)

    invalid: dict[str, list[str]] = {}
    stale: list[str] = []
    future_or_invalid_window: list[str] = []
    fresh_valid: list[Evidence] = []
    freshness_floor = current - timedelta(seconds=claim.freshness_sla_seconds)

    for item in evidence:
        failures = item.contract_failures()
        if item.claim_id != claim.claim_id:
            failures.append("evidence claim_id does not match closure claim")
        if failures:
            invalid[item.evidence_id] = failures
            continue
        if item.valid_from and current < item.valid_from:
            future_or_invalid_window.append(item.evidence_id)
            continue
        if item.valid_to and current > item.valid_to:
            stale.append(item.evidence_id)
            continue
        if item.retrieved_at < freshness_floor:
            stale.append(item.evidence_id)
            continue
        fresh_valid.append(item)

    supporting = [item for item in fresh_valid if item.relationship == "supports"]
    refuting = [item for item in fresh_valid if item.relationship == "refutes"]
    directional = supporting + refuting
    classes = {item.source_class for item in directional}
    requirement = policy.requirement_for(claim.risk)

    missing: list[str] = []
    primary_ok = not requirement.require_primary or any(
        item.source_class in PRIMARY_CLASSES for item in directional
    )
    if not primary_ok:
        missing.append("fresh primary or official evidence")

    independent_domains = {
        _domain(item) for item in directional if item.source_class == "independent" and _domain(item)
    }
    corroboration_ok = len(independent_domains) >= requirement.min_independent_sources
    if not corroboration_ok:
        missing.append(
            f"{requirement.min_independent_sources - len(independent_domains)} additional independent source domain(s)"
        )

    required_classes_ok = all(source_class in classes for source_class in claim.required_source_classes)
    for source_class in claim.required_source_classes:
        if source_class not in classes:
            missing.append(f"required source class: {source_class}")

    full_capture_ok = not requirement.require_full_source_capture or all(
        item.capture_scope in FULL_CAPTURE_SCOPES for item in directional
    )
    if directional and not full_capture_ok:
        missing.append("full deterministic source capture for every directional citation")

    citation_ok = bool(directional) and all(not item.contract_failures() for item in directional)
    if not citation_ok:
        missing.append("at least one citation with a valid quote digest")

    per_evidence_semantic_families: dict[str, set[str]] = {}
    semantic_families: set[str] = set()
    for item in directional:
        raw_families = item.citation.get("semantic_verifier_families", [])
        families = {
            family.strip()
            for family in raw_families
            if isinstance(family, str) and family.strip()
        }
        per_evidence_semantic_families[item.evidence_id] = families
        semantic_families.update(families)
    semantic_review_ok = (
        requirement.min_semantic_verifier_families == 0
        or (
            bool(directional)
            and all(per_evidence_semantic_families[item.evidence_id] for item in directional)
            and len(semantic_families) >= requirement.min_semantic_verifier_families
        )
    )
    if not semantic_review_ok:
        missing.append(
            f"{max(0, requirement.min_semantic_verifier_families - len(semantic_families))} "
            "additional independent semantic verifier family/families, with review coverage for every directional citation"
        )

    freshness_ok = bool(directional)
    if not freshness_ok:
        missing.append("fresh directional evidence within the claim SLA")

    conflict = bool(supporting and refuting)
    no_false_supported = not conflict

    gates = {
        "G1_CITATION_INTEGRITY": citation_ok,
        "G2_FRESHNESS": freshness_ok,
        "G3_PRIMARY_AUTHORITY": primary_ok,
        "G4_INDEPENDENT_CORROBORATION": corroboration_ok,
        "G5_REQUIRED_SOURCE_CLASSES": required_classes_ok,
        "G6_FULL_SOURCE_CAPTURE": full_capture_ok,
        "G7_SEMANTIC_REVIEW": semantic_review_ok,
        "G8_NO_UNRESOLVED_CONFLICT": no_false_supported,
    }

    authority_gates = all(
        gates[name]
        for name in (
            "G1_CITATION_INTEGRITY",
            "G2_FRESHNESS",
            "G3_PRIMARY_AUTHORITY",
            "G4_INDEPENDENT_CORROBORATION",
            "G5_REQUIRED_SOURCE_CLASSES",
            "G6_FULL_SOURCE_CAPTURE",
            "G7_SEMANTIC_REVIEW",
        )
    )

    if conflict:
        state = "CONFLICTED"
    elif supporting and authority_gates:
        state = "SUPPORTED"
    elif refuting and authority_gates:
        state = "REFUTED"
    elif not fresh_valid and stale:
        state = "STALE"
    else:
        state = "UNVERIFIABLE"

    closed = state in {"SUPPORTED", "REFUTED"} and all(gates.values())
    expires_at = current + timedelta(seconds=claim.freshness_sla_seconds) if closed else None
    missing = list(dict.fromkeys(missing))

    return {
        "schema": "tvl.evidence-closure.v1",
        "claim_id": claim.claim_id,
        "state": state,
        "closed": closed,
        "as_of": format_timestamp(current),
        "expires_at": format_timestamp(expires_at),
        "gates": gates,
        "missing_requirements": missing,
        "accepted_evidence_ids": [item.evidence_id for item in fresh_valid],
        "supporting_evidence_ids": [item.evidence_id for item in supporting],
        "refuting_evidence_ids": [item.evidence_id for item in refuting],
        "context_evidence_ids": [
            item.evidence_id for item in fresh_valid if item.relationship == "context"
        ],
        "stale_evidence_ids": stale,
        "future_or_invalid_window_evidence_ids": future_or_invalid_window,
        "invalid_evidence": invalid,
        "authority": {
            "source_classes": sorted(classes),
            "independent_domains": sorted(independent_domains),
            "required_primary": requirement.require_primary,
            "required_independent_sources": requirement.min_independent_sources,
            "required_full_source_capture": requirement.require_full_source_capture,
            "required_semantic_verifier_families": requirement.min_semantic_verifier_families,
            "semantic_verifier_families": sorted(semantic_families),
        },
        "coverage": {
            "directional_sources": len(directional),
            "supporting_sources": len(supporting),
            "refuting_sources": len(refuting),
            "fresh_sources": len(fresh_valid),
            "stale_sources": len(stale),
            "invalid_sources": len(invalid),
            "semantic_verifier_families": len(semantic_families),
            "semantic_reviewed_directional_sources": sum(
                1 for families in per_evidence_semantic_families.values() if families
            ),
        },
        "revision_contract": {
            "supersede_when": [
                "a cited source changes content hash",
                "the freshness deadline expires",
                "a higher-authority source conflicts",
                "claim scope or pinned version changes",
            ],
            "relation": "REVISES_OR_SUPERSEDES",
        },
    }
