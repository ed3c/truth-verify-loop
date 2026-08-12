"""Provider-neutral semantic review contracts and deterministic dispatch."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import math
from typing import Any, Iterable, Protocol, Sequence
from urllib.parse import urlsplit

from .model import (
    Claim,
    ContractError,
    Evidence,
    RELATIONSHIPS,
    SHA256_RE,
    canonical_json,
    format_timestamp,
    sha256_bytes,
    sha256_text,
)


SEMANTIC_VERDICTS = {"ENTAILS", "DOES_NOT_ENTAIL", "ABSTAIN"}
VERIFIER_STATUSES = {"succeeded", "failed", "timeout", "discarded"}
ATTEMPT_KINDS = {"primary", "recovery"}


def validate_verifier_usage(usage: dict[str, Any]) -> None:
    for key, value in usage.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))
            or value < 0
        ):
            raise ContractError(
                f"verifier usage {key} must be a finite non-negative number"
            )


@dataclass(frozen=True)
class SemanticReviewRequest:
    request_id: str
    claim_id: str
    statement: str
    claim_scope: dict[str, Any]
    evidence_id: str
    source_uri: str
    content_sha256: str
    quote: str
    quote_sha256: str
    capture_scope: str
    snapshot_id: str
    source_receipt_sha256: str
    relationship_proposal: str
    schema: str = "tvl.semantic-review-request.v1"

    def __post_init__(self) -> None:
        for name, value in (
            ("request_id", self.request_id),
            ("claim_id", self.claim_id),
            ("statement", self.statement),
            ("evidence_id", self.evidence_id),
            ("quote", self.quote),
            ("capture_scope", self.capture_scope),
            ("snapshot_id", self.snapshot_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"semantic request {name} must be non-empty")
        if self.schema != "tvl.semantic-review-request.v1":
            raise ContractError("semantic request schema must be tvl.semantic-review-request.v1")
        if not isinstance(self.claim_scope, dict):
            raise ContractError("semantic request claim_scope must be an object")
        parsed_uri = urlsplit(self.source_uri)
        if parsed_uri.scheme not in {"http", "https"} or not parsed_uri.hostname:
            raise ContractError("semantic request source_uri must be an absolute HTTP(S) URL")
        for name, digest in (
            ("content_sha256", self.content_sha256),
            ("quote_sha256", self.quote_sha256),
            ("source_receipt_sha256", self.source_receipt_sha256),
        ):
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                raise ContractError(
                    f"semantic request {name} must be a lowercase SHA-256 digest"
                )
        if sha256_text(self.quote) != self.quote_sha256:
            raise ContractError("semantic request quote_sha256 does not match quote")
        if self.relationship_proposal not in RELATIONSHIPS:
            raise ContractError(
                f"semantic request relationship_proposal must be one of {sorted(RELATIONSHIPS)}"
            )
        source_receipt = {
            "source_uri": self.source_uri,
            "content_sha256": self.content_sha256,
            "capture_scope": self.capture_scope,
            "snapshot_id": self.snapshot_id,
        }
        expected_receipt = sha256_text(canonical_json(source_receipt))
        if self.source_receipt_sha256 != expected_receipt:
            raise ContractError(
                "semantic request source_receipt_sha256 does not match source receipt"
            )

    @classmethod
    def from_evidence(
        cls, claim: Claim, evidence: Evidence
    ) -> "SemanticReviewRequest":
        if evidence.claim_id != claim.claim_id:
            raise ContractError("semantic review evidence does not match claim")
        snapshot_id = evidence.citation.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ContractError(
                "semantic review requires a pinned document snapshot receipt"
            )
        source_receipt = {
            "source_uri": evidence.source_uri,
            "content_sha256": evidence.content_sha256,
            "capture_scope": evidence.capture_scope,
            "snapshot_id": snapshot_id.strip(),
        }
        return cls(
            request_id=f"semantic-{evidence.evidence_id}",
            claim_id=claim.claim_id,
            statement=claim.statement,
            claim_scope=dict(claim.scope),
            evidence_id=evidence.evidence_id,
            source_uri=evidence.source_uri,
            content_sha256=evidence.content_sha256,
            quote=evidence.quote,
            quote_sha256=evidence.quote_sha256,
            capture_scope=evidence.capture_scope,
            snapshot_id=snapshot_id.strip(),
            source_receipt_sha256=sha256_text(canonical_json(source_receipt)),
            relationship_proposal=evidence.relationship,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "claim": {
                "claim_id": self.claim_id,
                "statement": self.statement,
                "scope": dict(self.claim_scope),
            },
            "evidence": {
                "evidence_id": self.evidence_id,
                "quote": self.quote,
                "quote_sha256": self.quote_sha256,
                "relationship_proposal": self.relationship_proposal,
                "source_receipt": {
                    "source_uri": self.source_uri,
                    "content_sha256": self.content_sha256,
                    "capture_scope": self.capture_scope,
                    "snapshot_id": self.snapshot_id,
                    "receipt_sha256": self.source_receipt_sha256,
                },
            },
        }


@dataclass(frozen=True)
class SemanticJudgeRequest:
    request: SemanticReviewRequest
    positions: tuple[dict[str, str], ...]
    schema: str = "tvl.semantic-judge-request.v1"

    @property
    def request_id(self) -> str:
        return self.request.request_id

    @property
    def evidence_id(self) -> str:
        return self.request.evidence_id

    def to_dict(self) -> dict[str, Any]:
        payload = self.request.to_dict()
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "claim": payload["claim"],
            "evidence": payload["evidence"],
            "positions": [dict(position) for position in self.positions],
        }


@dataclass(frozen=True)
class VerifierIdentity:
    provider: str
    model: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ContractError("verifier identity provider must be non-empty")
        if self.provider != self.provider.strip():
            raise ContractError("verifier identity provider must be canonical and trimmed")
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model.strip()
        ):
            raise ContractError("verifier identity model must be non-empty or null")
        if self.model is not None and self.model != self.model.strip():
            raise ContractError("verifier identity model must be canonical and trimmed")


@dataclass(frozen=True)
class VerifierReceipt:
    family: str
    provider: str
    provider_version: str | None
    model: str | None
    prompt_sha256: str
    instruction_hashes: tuple[str, ...]
    output_sha256: str
    started_at: datetime
    ended_at: datetime
    status: str
    exit_code: int | None
    timed_out: bool
    usage: dict[str, Any]
    attempt_kind: str = "primary"
    schema: str = "tvl.semantic-verifier-receipt.v1"
    command_sha256: str | None = None
    stderr_sha256: str | None = None
    failure_reason: str | None = None
    stdout_captured_bytes: int | None = None
    stderr_captured_bytes: int | None = None
    stdout_truncated: bool | None = None
    stderr_truncated: bool | None = None
    stream_limit_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.schema != "tvl.semantic-verifier-receipt.v1":
            raise ContractError(
                "verifier receipt schema must be tvl.semantic-verifier-receipt.v1"
            )
        if not self.family.strip():
            raise ContractError("verifier family must be a non-empty string")
        if not self.provider.strip():
            raise ContractError("verifier provider must be a non-empty string")
        if self.status not in VERIFIER_STATUSES:
            raise ContractError(f"verifier status must be one of {sorted(VERIFIER_STATUSES)}")
        if self.timed_out != (self.status == "timeout"):
            raise ContractError("timed_out must be true exactly when status is timeout")
        if self.status == "succeeded" and self.exit_code != 0:
            raise ContractError("succeeded verifier receipt must have exit_code 0")
        if self.status == "succeeded" and self.failure_reason is not None:
            raise ContractError("succeeded verifier receipt cannot have failure_reason")
        if self.failure_reason is not None and (
            not isinstance(self.failure_reason, str)
            or not self.failure_reason.strip()
            or self.failure_reason != self.failure_reason.strip()
        ):
            raise ContractError("verifier failure_reason must be canonical or null")
        if self.attempt_kind not in ATTEMPT_KINDS:
            raise ContractError(f"attempt_kind must be one of {sorted(ATTEMPT_KINDS)}")
        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None
            for timestamp in (self.started_at, self.ended_at)
        ):
            raise ContractError("verifier timestamps must include a timezone")
        if self.ended_at < self.started_at:
            raise ContractError("verifier ended_at is before started_at")
        validate_verifier_usage(self.usage)
        stream_metadata = (
            self.stdout_captured_bytes,
            self.stderr_captured_bytes,
            self.stdout_truncated,
            self.stderr_truncated,
            self.stream_limit_bytes,
        )
        if any(value is not None for value in stream_metadata):
            if any(value is None for value in stream_metadata):
                raise ContractError(
                    "verifier stream capture metadata must be complete or absent"
                )
            if (
                not isinstance(self.stdout_captured_bytes, int)
                or isinstance(self.stdout_captured_bytes, bool)
                or self.stdout_captured_bytes < 0
                or not isinstance(self.stderr_captured_bytes, int)
                or isinstance(self.stderr_captured_bytes, bool)
                or self.stderr_captured_bytes < 0
                or not isinstance(self.stream_limit_bytes, int)
                or isinstance(self.stream_limit_bytes, bool)
                or self.stream_limit_bytes <= 0
                or self.stdout_captured_bytes > self.stream_limit_bytes
                or self.stderr_captured_bytes > self.stream_limit_bytes
                or not isinstance(self.stdout_truncated, bool)
                or not isinstance(self.stderr_truncated, bool)
            ):
                raise ContractError("verifier stream capture metadata is invalid")
            if self.status == "succeeded" and (
                self.stdout_truncated or self.stderr_truncated
            ):
                raise ContractError("succeeded verifier streams cannot be truncated")
        digests = [
            ("prompt_sha256", self.prompt_sha256),
            ("output_sha256", self.output_sha256),
        ]
        if self.command_sha256 is not None:
            digests.append(("command_sha256", self.command_sha256))
        if self.stderr_sha256 is not None:
            digests.append(("stderr_sha256", self.stderr_sha256))
        digests.extend(
            ("instruction_hash", digest) for digest in self.instruction_hashes
        )
        for name, digest in digests:
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ContractError(f"{name} must be a lowercase SHA-256 digest")

    @property
    def latency_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    @property
    def identity(self) -> VerifierIdentity:
        return VerifierIdentity(provider=self.provider, model=self.model)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema": self.schema,
            "family": self.family,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "model": self.model,
            "prompt_sha256": self.prompt_sha256,
            "instruction_hashes": list(self.instruction_hashes),
            "output_sha256": self.output_sha256,
            "started_at": format_timestamp(self.started_at),
            "ended_at": format_timestamp(self.ended_at),
            "status": self.status,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "attempt_kind": self.attempt_kind,
            "usage": dict(self.usage),
        }
        if self.command_sha256 is not None:
            result["command_sha256"] = self.command_sha256
        if self.stderr_sha256 is not None:
            result["stderr_sha256"] = self.stderr_sha256
        if self.failure_reason is not None:
            result["failure_reason"] = self.failure_reason
        if self.stream_limit_bytes is not None:
            result["stream_capture"] = {
                "limit_bytes_per_channel": self.stream_limit_bytes,
                "stdout": {
                    "captured_bytes": self.stdout_captured_bytes,
                    "truncated": self.stdout_truncated,
                },
                "stderr": {
                    "captured_bytes": self.stderr_captured_bytes,
                    "truncated": self.stderr_truncated,
                },
            }
        return result

    @property
    def digest(self) -> str:
        return sha256_text(canonical_json(self.to_dict()))


@dataclass(frozen=True)
class SemanticReview:
    request_id: str
    evidence_id: str
    family: str
    verdict: str
    rationale_summary: str
    verifier_receipt_sha256: str
    schema: str = "tvl.semantic-review.v1"

    def __post_init__(self) -> None:
        if self.schema != "tvl.semantic-review.v1":
            raise ContractError("semantic review schema must be tvl.semantic-review.v1")
        for name, value in (
            ("request_id", self.request_id),
            ("evidence_id", self.evidence_id),
            ("family", self.family),
        ):
            if not value.strip():
                raise ContractError(f"semantic {name} must be a non-empty string")
        if self.verdict not in SEMANTIC_VERDICTS:
            raise ContractError(f"semantic verdict must be one of {sorted(SEMANTIC_VERDICTS)}")
        if not self.rationale_summary.strip():
            raise ContractError("semantic rationale_summary must be non-empty")
        digest = self.verifier_receipt_sha256
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ContractError(
                "semantic verifier receipt must be pinned by a lowercase SHA-256 digest"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "evidence_id": self.evidence_id,
            "family": self.family,
            "verdict": self.verdict,
            "rationale_summary": self.rationale_summary,
            "verifier_receipt_sha256": self.verifier_receipt_sha256,
        }


@dataclass(frozen=True)
class VerifierAttemptStream:
    receipt_sha256: str
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def __post_init__(self) -> None:
        if len(self.receipt_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.receipt_sha256
        ):
            raise ContractError(
                "verifier attempt stream requires a receipt SHA-256 digest"
            )
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise ContractError("verifier attempt streams must contain bytes")


@dataclass(frozen=True)
class VerifierRun:
    receipt: VerifierReceipt
    reviews: tuple[SemanticReview, ...]
    prior_attempt_receipts: tuple[VerifierReceipt, ...] = ()
    attempt_streams: tuple[VerifierAttemptStream, ...] = ()

    @property
    def attempt_receipts(self) -> tuple[VerifierReceipt, ...]:
        return self.prior_attempt_receipts + (self.receipt,)


class SemanticVerifier(Protocol):
    family: str
    identity: VerifierIdentity

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun: ...


class SemanticJudge(Protocol):
    family: str
    identity: VerifierIdentity

    def run(self, requests: tuple[SemanticJudgeRequest, ...]) -> VerifierRun: ...


@dataclass(frozen=True)
class SemanticAggregate:
    evidence_id: str
    verdict: str
    accepted_families: tuple[str, ...]
    policy_satisfied: bool
    judge_family: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "verdict": self.verdict,
            "accepted_families": list(self.accepted_families),
            "policy_satisfied": self.policy_satisfied,
            "judge_family": self.judge_family,
        }


@dataclass(frozen=True)
class SemanticDispatchResult:
    runs: tuple[VerifierRun, ...]
    run_dispositions: tuple[tuple[str, str], ...]
    reviews: tuple[SemanticReview, ...]
    aggregates: dict[str, SemanticAggregate]
    totals: dict[str, int | float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "tvl.semantic-dispatch.v1",
            "runs": [
                {
                    "receipt": run.receipt.to_dict(),
                    "receipt_sha256": run.receipt.digest,
                    "attempt_receipts": [
                        {
                            "receipt": receipt.to_dict(),
                            "receipt_sha256": receipt.digest,
                        }
                        for receipt in run.attempt_receipts
                    ],
                    "reviews": [review.to_dict() for review in run.reviews],
                    "disposition": disposition,
                    "reason": reason,
                }
                for run, (disposition, reason) in zip(
                    self.runs, self.run_dispositions, strict=True
                )
            ],
            "aggregates": {
                evidence_id: aggregate.to_dict()
                for evidence_id, aggregate in self.aggregates.items()
            },
            "totals": dict(self.totals),
        }


class SemanticDispatcher:
    def __init__(
        self,
        verifiers: Sequence[SemanticVerifier],
        *,
        judge: SemanticJudge | None = None,
        max_judge_requests: int = 8,
    ) -> None:
        self.verifiers = tuple(verifiers)
        self.judge = judge
        self.max_judge_requests = max_judge_requests
        families = [verifier.family.strip() for verifier in self.verifiers]
        if not families or any(not family for family in families):
            raise ContractError("semantic dispatch requires named verifier families")
        if len(families) != len(set(families)):
            raise ContractError("semantic verifier families must be unique")
        for verifier in self.verifiers:
            if not isinstance(getattr(verifier, "identity", None), VerifierIdentity):
                raise ContractError(
                    f"semantic verifier {verifier.family} requires a configured identity"
                )
        if self.judge is not None and not isinstance(
            getattr(self.judge, "identity", None), VerifierIdentity
        ):
            raise ContractError("semantic judge requires a configured identity")
        if max_judge_requests <= 0:
            raise ContractError("max_judge_requests must be positive")

    def dispatch(
        self,
        requests: Iterable[SemanticReviewRequest],
        *,
        minimum_families: int,
        search_provider_family: str | None = None,
        search_provider_identity: VerifierIdentity | None = None,
        judge: SemanticJudge | None = None,
        max_judge_requests: int | None = None,
    ) -> SemanticDispatchResult:
        batch = tuple(requests)
        if not batch:
            raise ContractError("semantic dispatch requires at least one request")
        if minimum_families <= 0:
            raise ContractError("minimum_families must be positive")
        active_judge = judge or self.judge
        judge_limit = (
            self.max_judge_requests
            if max_judge_requests is None
            else max_judge_requests
        )
        if judge_limit <= 0:
            raise ContractError("max_judge_requests must be positive")
        request_ids = {request.request_id: request for request in batch}
        if len(request_ids) != len(batch):
            raise ContractError("semantic request IDs must be unique")

        runs: list[VerifierRun] = []
        dispositions: dict[str, tuple[str, str]] = {}
        eligible_runs: list[VerifierRun] = []
        accepted_reviews: list[SemanticReview] = []
        totals: dict[str, int | float] = {
            "attempts": 0,
            "failed_attempts": 0,
            "timeout_attempts": 0,
            "discarded_attempts": 0,
            "recovery_attempts": 0,
            "latency_seconds": 0.0,
        }
        for verifier in self.verifiers:
            run = verifier.run(deepcopy(batch))
            if run.receipt.family != verifier.family:
                raise ContractError("verifier receipt family does not match adapter family")
            if run.receipt.identity != verifier.identity:
                raise ContractError(
                    "verifier receipt does not match adapter configured identity"
                )
            runs.append(run)
            self._validate_attempt_chain(run, verifier.identity, role="verifier")
            self._validate_attempt_streams(run)
            for receipt in run.attempt_receipts:
                self._accumulate_attempt(totals, receipt)
            if run.receipt.status != "succeeded":
                dispositions[run.receipt.digest] = (
                    "ineligible",
                    f"status_{run.receipt.status}",
                )
                continue
            if (
                search_provider_family
                and run.receipt.family == search_provider_family
            ) or (
                search_provider_identity is not None
                and run.receipt.identity == search_provider_identity
            ):
                totals["discarded_attempts"] += 1
                reason = (
                    "search_provider_identity"
                    if search_provider_identity is not None
                    and verifier.identity == search_provider_identity
                    else "search_provider_family"
                )
                dispositions[run.receipt.digest] = ("discarded", reason)
                continue
            seen_requests: set[str] = set()
            validated_reviews: list[SemanticReview] = []
            for review in run.reviews:
                request = request_ids.get(review.request_id)
                if request is None or review.evidence_id != request.evidence_id:
                    raise ContractError("semantic review does not match a dispatched request")
                if review.request_id in seen_requests:
                    raise ContractError("verifier returned duplicate reviews for one request")
                if review.family != run.receipt.family:
                    raise ContractError("semantic review family does not match receipt family")
                if review.verifier_receipt_sha256 != run.receipt.digest:
                    raise ContractError("semantic review receipt digest does not match verifier receipt")
                seen_requests.add(review.request_id)
                validated_reviews.append(review)
            if seen_requests != set(request_ids):
                raise ContractError(
                    "successful verifier must return exactly one review for every request"
                )
            eligible_runs.append(
                VerifierRun(receipt=run.receipt, reviews=tuple(validated_reviews))
            )

        runs_by_identity: dict[VerifierIdentity, list[VerifierRun]] = {}
        configured_verifier_identities = {
            verifier.identity for verifier in self.verifiers
        }
        for run in eligible_runs:
            runs_by_identity.setdefault(run.receipt.identity, []).append(run)
        reviewer_identities: set[VerifierIdentity] = set()
        for identity_runs in runs_by_identity.values():
            verdict_vectors = {
                tuple(
                    sorted(
                        (review.request_id, review.verdict)
                        for review in run.reviews
                    )
                )
                for run in identity_runs
            }
            if len(verdict_vectors) > 1:
                totals["discarded_attempts"] += len(identity_runs)
                for run in identity_runs:
                    dispositions[run.receipt.digest] = (
                        "discarded",
                        "correlated_identity_conflict",
                    )
                continue
            chosen = min(identity_runs, key=lambda run: run.receipt.family)
            accepted_reviews.extend(chosen.reviews)
            reviewer_identities.add(chosen.receipt.identity)
            totals["discarded_attempts"] += len(identity_runs) - 1
            dispositions[chosen.receipt.digest] = ("accepted", "accepted")
            for run in identity_runs:
                if run is not chosen:
                    dispositions[run.receipt.digest] = (
                        "discarded",
                        "duplicate_identity",
                    )

        aggregates: dict[str, SemanticAggregate] = {}
        reviews_by_request: dict[str, list[SemanticReview]] = {}
        for request in batch:
            reviews = [
                review for review in accepted_reviews if review.request_id == request.request_id
            ]
            opinions = [review for review in reviews if review.verdict != "ABSTAIN"]
            reviews_by_request[request.request_id] = opinions
            families = tuple(sorted({review.family for review in opinions}))
            verdicts = {review.verdict for review in opinions}
            if not verdicts:
                verdict = "ABSTAIN"
            elif len(verdicts) == 1:
                verdict = next(iter(verdicts))
            else:
                verdict = "DISAGREEMENT"
            aggregates[request.evidence_id] = SemanticAggregate(
                evidence_id=request.evidence_id,
                verdict=verdict,
                accepted_families=families,
                policy_satisfied=(
                    len(families) >= minimum_families
                    and verdict not in {"ABSTAIN", "DISAGREEMENT"}
                ),
            )

        disagreements = [
            request
            for request in batch
            if aggregates[request.evidence_id].verdict == "DISAGREEMENT"
        ]
        if (
            active_judge is not None
            and disagreements
            and len(disagreements) <= judge_limit
        ):
            reviewer_families = {verifier.family for verifier in self.verifiers}
            if (
                active_judge.family in reviewer_families
                or active_judge.family == search_provider_family
            ):
                raise ContractError("judge family must be fresh and independent")
            if not isinstance(
                getattr(active_judge, "identity", None), VerifierIdentity
            ):
                raise ContractError("semantic judge requires a configured identity")
            if (
                active_judge.identity in configured_verifier_identities
                or active_judge.identity == search_provider_identity
            ):
                raise ContractError(
                    "judge configured identity must be fresh and independent"
                )
            judge_requests = tuple(
                SemanticJudgeRequest(
                    request=request,
                    positions=tuple(
                        {
                            "verdict": review.verdict,
                            "rationale_summary": review.rationale_summary,
                        }
                        for review in sorted(
                            reviews_by_request[request.request_id],
                            key=lambda review: (
                                review.verdict,
                                review.rationale_summary,
                            ),
                        )
                    ),
                )
                for request in disagreements
            )
            judge_run = active_judge.run(deepcopy(judge_requests))
            if judge_run.receipt.family != active_judge.family:
                raise ContractError("judge receipt family does not match adapter family")
            if judge_run.receipt.identity != active_judge.identity:
                raise ContractError("judge receipt does not match adapter configured identity")
            runs.append(judge_run)
            totals["judge_attempts"] = totals.get("judge_attempts", 0) + 1
            self._validate_attempt_chain(judge_run, active_judge.identity, role="judge")
            self._validate_attempt_streams(judge_run)
            for receipt in judge_run.attempt_receipts:
                self._accumulate_attempt(totals, receipt)
            judge_is_correlated = (
                judge_run.receipt.identity in reviewer_identities
                or (
                    search_provider_identity is not None
                    and judge_run.receipt.identity == search_provider_identity
                )
            )
            if judge_is_correlated:
                totals["discarded_attempts"] += 1
                dispositions[judge_run.receipt.digest] = (
                    "discarded",
                    "judge_correlated_identity",
                )
            elif judge_run.receipt.status != "succeeded":
                dispositions[judge_run.receipt.digest] = (
                    "ineligible",
                    f"status_{judge_run.receipt.status}",
                )
            else:
                dispositions[judge_run.receipt.digest] = ("accepted", "accepted")
            if judge_run.receipt.status == "succeeded" and not judge_is_correlated:
                judge_request_ids = {request.request_id: request for request in judge_requests}
                seen_judge_requests: set[str] = set()
                for review in judge_run.reviews:
                    judge_request = judge_request_ids.get(review.request_id)
                    if judge_request is None or review.evidence_id != judge_request.evidence_id:
                        raise ContractError("judge review does not match a disagreement request")
                    if review.family != judge_run.receipt.family:
                        raise ContractError("judge review family does not match receipt family")
                    if review.verifier_receipt_sha256 != judge_run.receipt.digest:
                        raise ContractError("judge review receipt digest does not match receipt")
                    if review.request_id in seen_judge_requests:
                        raise ContractError(
                            "judge must return exactly one judge review per disagreement"
                        )
                    seen_judge_requests.add(review.request_id)
                    if review.verdict == "ABSTAIN":
                        continue
                    accepted_reviews.append(review)
                    prior = aggregates[review.evidence_id]
                    aggregates[review.evidence_id] = SemanticAggregate(
                        evidence_id=review.evidence_id,
                        verdict=review.verdict,
                        accepted_families=prior.accepted_families,
                        policy_satisfied=(
                            len(prior.accepted_families) >= minimum_families
                        ),
                        judge_family=active_judge.family,
                    )
                if seen_judge_requests != set(judge_request_ids):
                    raise ContractError(
                        "judge must return exactly one judge review per disagreement"
                    )

        return SemanticDispatchResult(
            runs=tuple(runs),
            run_dispositions=tuple(dispositions[run.receipt.digest] for run in runs),
            reviews=tuple(accepted_reviews),
            aggregates=aggregates,
            totals=totals,
        )

    @staticmethod
    def _validate_attempt_streams(run: VerifierRun) -> None:
        receipts = {
            receipt.digest: receipt for receipt in run.attempt_receipts
        }
        seen: set[str] = set()
        for stream in run.attempt_streams:
            receipt = receipts.get(stream.receipt_sha256)
            if receipt is None or stream.receipt_sha256 in seen:
                raise ContractError(
                    "verifier attempt stream must match one unique attempt receipt"
                )
            if sha256_bytes(stream.stdout) != receipt.output_sha256:
                raise ContractError(
                    "verifier stdout stream does not match its receipt digest"
                )
            if receipt.stderr_sha256 is None:
                raise ContractError(
                    "verifier raw streams require a stderr receipt digest"
                )
            if sha256_bytes(stream.stderr) != receipt.stderr_sha256:
                raise ContractError(
                    "verifier stderr stream does not match its receipt digest"
                )
            if receipt.stream_limit_bytes is not None and (
                receipt.stdout_captured_bytes != len(stream.stdout)
                or receipt.stderr_captured_bytes != len(stream.stderr)
                or receipt.stdout_truncated != stream.stdout_truncated
                or receipt.stderr_truncated != stream.stderr_truncated
            ):
                raise ContractError(
                    "verifier stream capture metadata does not match raw streams"
                )
            seen.add(stream.receipt_sha256)
        requires_streams = any(
            receipt.stream_limit_bytes is not None
            for receipt in run.attempt_receipts
        )
        if (run.attempt_streams or requires_streams) and seen != set(receipts):
            raise ContractError(
                "verifier attempt streams must cover every attempt receipt"
            )

    @staticmethod
    def _validate_attempt_chain(
        run: VerifierRun,
        expected_identity: VerifierIdentity,
        *,
        role: str,
    ) -> None:
        attempts = run.attempt_receipts
        for index, receipt in enumerate(attempts):
            if receipt.family != run.receipt.family:
                raise ContractError(f"{role} attempt chain families do not match")
            if receipt.identity != expected_identity:
                raise ContractError(f"{role} attempt chain identities do not match")
            expected_kind = "primary" if index == 0 else "recovery"
            if receipt.attempt_kind != expected_kind:
                raise ContractError(
                    f"{role} attempt chain must start primary and then use recovery attempts"
                )
            if index > 0:
                previous = attempts[index - 1]
                if previous.status == "succeeded":
                    raise ContractError(
                        f"{role} attempt chain cannot recover after success"
                    )
                if receipt.started_at < previous.ended_at:
                    raise ContractError(
                        f"{role} attempt chain timestamps must be chronological"
                    )

    @staticmethod
    def _accumulate_attempt(
        totals: dict[str, int | float], receipt: VerifierReceipt
    ) -> None:
        totals["attempts"] += 1
        totals["latency_seconds"] += receipt.latency_seconds
        if receipt.status == "failed":
            totals["failed_attempts"] += 1
        elif receipt.status == "timeout":
            totals["timeout_attempts"] += 1
        elif receipt.status == "discarded":
            totals["discarded_attempts"] += 1
        if receipt.attempt_kind == "recovery":
            totals["recovery_attempts"] += 1
        for key, value in receipt.usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                current = totals.get(key, 0)
                if isinstance(current, float) or isinstance(value, float):
                    totals[key] = float(Decimal(str(current)) + Decimal(str(value)))
                else:
                    totals[key] = current + value
