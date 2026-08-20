"""End-to-end live-search verification orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import uuid

from .closure import close_claim
from .documents import DocumentSnapshot, chunk_document, chunk_for_span
from .lake import EvidenceLake
from .model import Claim, Evidence, canonical_json, format_timestamp, sha256_text, utc_now
from .policy import SourcePolicy, decide_live_search
from .providers import AgyProvider, ProviderError, build_search_prompt, extract_search_envelope
from .retriever import RetrievalError, SafeHttpRetriever, locate_quote
from .semantic import SemanticDispatcher, SemanticReviewRequest, VerifierIdentity


class HarnessError(RuntimeError):
    """Raised when the live loop cannot satisfy a fail-closed gate."""


def _parse_optional_published_at(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        normalized += "T00:00:00Z"
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_evidence_id(claim: Claim, uri: str, quote: str, relationship: str) -> str:
    material = canonical_json(
        {
            "claim_id": claim.claim_id,
            "source_uri": uri,
            "quote": quote,
            "relationship": relationship,
        }
    )
    return f"ev-{sha256_text(material)[:24]}"


def run_live_verification(
    claim: Claim,
    *,
    lake: EvidenceLake,
    policy: SourcePolicy,
    provider: AgyProvider,
    retriever: SafeHttpRetriever,
    cwd: Path | str,
    model_knowledge_cutoff: str | datetime | None,
    outer_timeout_seconds: float = 330.0,
    instruction_files: tuple[Path, ...] = (),
    semantic_dispatcher: SemanticDispatcher | None = None,
    evaluation_time: datetime | None = None,
) -> dict[str, Any]:
    evaluation_clock = evaluation_time or utc_now()
    if evaluation_clock.tzinfo is None:
        raise HarnessError("evaluation_time must be timezone-aware")
    evaluation_clock = evaluation_clock.astimezone(timezone.utc)

    lake.initialize()
    lake.upsert_claim(claim)
    decision = decide_live_search(
        claim,
        model_knowledge_cutoff=model_knowledge_cutoff,
    )
    lake.append_ledger(
        "bronze",
        "retrieval-events",
        {
            "phase": "DECIDE",
            "claim_id": claim.claim_id,
            "decision": decision.to_dict(),
        },
    )
    if not decision.required:
        existing = lake.evidence_for_claim(claim.claim_id)
        closure = close_claim(
            claim,
            existing,
            policy=policy,
            now=evaluation_clock,
        )
        lake.record_closure(closure)
        lake.write_manifest()
        return {"decision": decision.to_dict(), "closure": closure, "retrievals": []}

    prompt = build_search_prompt(claim)
    provider_run = provider.run(
        prompt,
        cwd=cwd,
        outer_timeout_seconds=outer_timeout_seconds,
        instruction_files=instruction_files,
    )
    receipt_bytes = canonical_json(provider_run.receipt.to_dict()).encode("utf-8")
    receipt_blob = lake.store_blob(
        receipt_bytes,
        source_uri="urn:tvl:provider-receipt:antigravity-cli",
        media_type="application/json",
        capture_scope="provider_receipt",
        retrieved_at=provider_run.receipt.ended_at,
    )
    stdout_blob = lake.store_blob(
        provider_run.stdout,
        source_uri="urn:tvl:provider-stream:stdout",
        media_type="application/x-ndjson",
        capture_scope="provider_stream",
        retrieved_at=provider_run.receipt.ended_at,
    )
    stderr_blob = lake.store_blob(
        provider_run.stderr,
        source_uri="urn:tvl:provider-stream:stderr",
        media_type="text/plain",
        capture_scope="provider_stream",
        retrieved_at=provider_run.receipt.ended_at,
    )
    lake.append_ledger(
        "bronze",
        "agent-sessions",
        {
            "claim_id": claim.claim_id,
            "receipt": provider_run.receipt.to_dict(),
            "receipt_sha256": receipt_blob["content_sha256"],
            "stdout_sha256": stdout_blob["content_sha256"],
            "stderr_sha256": stderr_blob["content_sha256"],
        },
    )
    if provider_run.receipt.timed_out:
        raise HarnessError("search provider timed out; receipt was preserved")
    if provider_run.receipt.exit_code != 0:
        raise HarnessError(
            f"search provider exited with code {provider_run.receipt.exit_code}; receipt was preserved"
        )
    try:
        envelope = extract_search_envelope(provider_run.events)
    except ProviderError as exc:
        raise HarnessError(str(exc)) from exc

    retrievals: list[dict[str, Any]] = []
    accepted: list[Evidence] = []
    for candidate in envelope.candidates:
        attempt_id = str(uuid.uuid4())
        try:
            fetched = retriever.fetch(candidate.source_uri)
            captured = lake.store_blob(
                fetched.raw,
                source_uri=fetched.final_uri,
                media_type=fetched.media_type,
                capture_scope="full_source",
                retrieved_at=datetime.fromisoformat(fetched.retrieved_at.replace("Z", "+00:00")),
            )
            quote_span = locate_quote(candidate.quote, fetched.normalized_text)
            verified = quote_span is not None
            source_class = policy.classify(fetched.final_uri, claim=claim)
            snapshot = DocumentSnapshot.from_capture(
                source_uri=fetched.final_uri,
                source_type=source_class,
                authority_class=source_class,
                media_type=fetched.media_type,
                content_sha256=captured["content_sha256"],
                retrieved_at=fetched.retrieved_at,
                capture_scope="full_source",
                title=candidate.title,
                scope=claim.scope,
                metadata={"status_code": fetched.status_code},
            )
            previous = lake.current_document_for_uri(snapshot.source_uri)
            if previous and previous.get("snapshot_id") != snapshot.snapshot_id:
                snapshot = replace(snapshot, supersedes_snapshot_id=previous.get("snapshot_id"))
            chunks = (
                chunk_document(snapshot, fetched.normalized_text)
                if fetched.normalized_text is not None
                else []
            )
            lake.upsert_document(snapshot, chunks)
            cited_chunk = (
                chunk_for_span(chunks, quote_span[0], quote_span[1]) if quote_span is not None else None
            )
            event = {
                "phase": "CAPTURE",
                "attempt_id": attempt_id,
                "claim_id": claim.claim_id,
                "requested_uri": candidate.source_uri,
                "final_uri": fetched.final_uri,
                "status_code": fetched.status_code,
                "media_type": fetched.media_type,
                "content_sha256": captured["content_sha256"],
                "source_class": source_class,
                "document_id": snapshot.document_id,
                "snapshot_id": snapshot.snapshot_id,
                "chunk_count": len(chunks),
                "quote_verified": verified,
                "outcome": "ACCEPTED" if verified else "QUOTE_MISMATCH",
            }
            lake.append_ledger("bronze", "retrieval-events", event)
            retrievals.append(event)
            if not verified:
                continue
            citation = {
                "quote_verified": True,
                "capture_media_type": fetched.media_type,
                "capture_scope": "full_source",
                "document_id": snapshot.document_id,
                "snapshot_id": snapshot.snapshot_id,
                "chunk_id": cited_chunk.chunk_id if cited_chunk else None,
                "start": quote_span[0] if quote_span else None,
                "end": quote_span[1] if quote_span else None,
            }
            if semantic_dispatcher is None:
                citation["semantic_verifier_families"] = [
                    provider_run.receipt.provider
                ]
            evidence = Evidence.from_dict(
                {
                    "evidence_id": _stable_evidence_id(
                        claim, fetched.final_uri, candidate.quote, candidate.relationship
                    ),
                    "claim_id": claim.claim_id,
                    "source_uri": fetched.final_uri,
                    "source_class": source_class,
                    "relationship": candidate.relationship,
                    "quote": candidate.quote,
                    "retrieved_at": fetched.retrieved_at,
                    "content_sha256": captured["content_sha256"],
                    "quote_sha256": sha256_text(candidate.quote),
                    "capture_scope": "full_source",
                    "provider_receipt_sha256": receipt_blob["content_sha256"],
                    "title": candidate.title,
                    "published_at": _parse_optional_published_at(candidate.published_at),
                    "citation": citation,
                }
            )
            accepted.append(evidence)
        except RetrievalError as exc:
            event = {
                "phase": "CAPTURE",
                "attempt_id": attempt_id,
                "claim_id": claim.claim_id,
                "requested_uri": candidate.source_uri,
                "outcome": "REJECTED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            lake.append_ledger("bronze", "retrieval-events", event)
            retrievals.append(event)

    semantic_dispatch_payload: dict[str, Any] | None = None
    if semantic_dispatcher is not None and accepted:
        requirement = policy.requirement_for(claim.risk)
        dispatch = semantic_dispatcher.dispatch(
            [SemanticReviewRequest.from_evidence(claim, item) for item in accepted],
            minimum_families=max(
                1, requirement.min_semantic_verifier_families
            ),
            search_provider_identity=VerifierIdentity(
                provider=provider_run.receipt.provider,
                model=provider_run.receipt.model,
            ),
        )
        semantic_dispatch_payload = dispatch.to_dict()
        for run in dispatch.runs:
            receipts_by_digest = {
                receipt.digest: receipt for receipt in run.attempt_receipts
            }
            for receipt in run.attempt_receipts:
                lake.store_blob(
                    canonical_json(receipt.to_dict()).encode("utf-8"),
                    source_uri=(
                        "urn:tvl:semantic-verifier-receipt:" + receipt.family
                    ),
                    media_type="application/json",
                    capture_scope="semantic_verifier_receipt",
                    retrieved_at=receipt.ended_at,
                )
            for stream in run.attempt_streams:
                receipt = receipts_by_digest.get(stream.receipt_sha256)
                if receipt is None:
                    raise HarnessError(
                        "semantic attempt stream does not match a verifier receipt"
                    )
                for channel, raw in (
                    ("stdout", stream.stdout),
                    ("stderr", stream.stderr),
                ):
                    lake.store_blob(
                        raw,
                        source_uri=(
                            "urn:tvl:semantic-verifier-stream:"
                            + stream.receipt_sha256
                            + ":"
                            + channel
                        ),
                        media_type=(
                            "application/json"
                            if channel == "stdout"
                            else "text/plain"
                        ),
                        capture_scope="semantic_verifier_stream",
                        retrieved_at=receipt.ended_at,
                    )
        lake.append_ledger(
            "silver",
            "semantic-reviews",
            {
                "claim_id": claim.claim_id,
                "dispatch": semantic_dispatch_payload,
            },
        )
        reviewed: list[Evidence] = []
        for item in accepted:
            aggregate = dispatch.aggregates[item.evidence_id]
            citation = dict(item.citation)
            citation["semantic_review"] = aggregate.to_dict()
            citation["semantic_review_receipt_sha256s"] = sorted(
                {
                    review.verifier_receipt_sha256
                    for review in dispatch.reviews
                    if review.evidence_id == item.evidence_id
                }
            )
            relationship = item.relationship
            if aggregate.verdict == "ENTAILS" and aggregate.policy_satisfied:
                citation["semantic_verifier_families"] = list(
                    aggregate.accepted_families
                )
            else:
                citation.pop("semantic_verifier_families", None)
                relationship = "context"
            payload = item.to_dict()
            payload["relationship"] = relationship
            payload["citation"] = citation
            reviewed.append(Evidence.from_dict(payload))
        accepted = reviewed

    for evidence in accepted:
        lake.upsert_evidence(evidence)

    all_evidence = lake.evidence_for_claim(claim.claim_id)
    closure = close_claim(
        claim,
        all_evidence,
        policy=policy,
        now=evaluation_clock,
    )
    closure["run"] = {
        "provider": provider_run.receipt.provider,
        "provider_receipt_sha256": receipt_blob["content_sha256"],
        "prompt_sha256": provider_run.receipt.prompt_sha256,
        "model_knowledge_cutoff": format_timestamp(decision.model_knowledge_cutoff),
        "search_envelope_query": envelope.query,
        "accepted_in_this_run": [item.evidence_id for item in accepted],
        "evaluation_time": format_timestamp(evaluation_clock),
    }
    lake.record_closure(closure)
    lake.append_ledger(
        "gold",
        "coverage-ledger",
        {
            "claim_id": claim.claim_id,
            "state": closure["state"],
            "gates": closure["gates"],
            "coverage": closure["coverage"],
            "retrieval_attempts": len(retrievals),
        },
    )
    manifest = lake.write_manifest()
    return {
        "decision": decision.to_dict(),
        "closure": closure,
        "retrievals": retrievals,
        "semantic_dispatch": semantic_dispatch_payload,
        "manifest": manifest.as_posix(),
    }
