from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest

from harness.lake import EvidenceLake
from harness.model import Claim, ContractError, Evidence, sha256_bytes, sha256_text
from harness.orchestrator import run_live_verification
from harness.policy import RiskRequirement, SourcePolicy
from harness.providers import ProviderReceipt, ProviderRun
from harness.retriever import FetchedSource
from harness.semantic import (
    SemanticDispatcher,
    SemanticJudgeRequest,
    SemanticReview,
    SemanticReviewRequest,
    VerifierAttemptStream,
    VerifierIdentity,
    VerifierReceipt,
    VerifierRun,
)


NOW = datetime(2026, 8, 12, 6, 30, tzinfo=timezone.utc)


def claim(*, risk: str = "medium", temporality: str = "versioned") -> Claim:
    return Claim.from_dict(
        {
            "claim_id": "claim-1",
            "statement": "Example SDK 4.2 is generally available.",
            "risk": risk,
            "temporality": temporality,
            "freshness_sla_seconds": 86400,
            "scope": {"package": "example-sdk", "version": "4.2"},
        }
    )


def evidence() -> Evidence:
    quote = "Example SDK 4.2 is generally available."
    return Evidence.from_dict(
        {
            "evidence_id": "evidence-1",
            "claim_id": "claim-1",
            "source_uri": "https://docs.example.invalid/releases/4.2",
            "source_class": "official_release",
            "relationship": "supports",
            "quote": quote,
            "retrieved_at": NOW.isoformat(),
            "content_sha256": "a" * 64,
            "quote_sha256": sha256_text(quote),
            "capture_scope": "full_source",
            "provider_receipt_sha256": "b" * 64,
            "citation": {
                "quote_verified": True,
                "snapshot_id": "snapshot-1",
            },
        }
    )


class SemanticReviewContractTests(unittest.TestCase):
    def test_request_contains_only_scoped_claim_and_pinned_capture(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        self.assertEqual(
            request.to_dict(),
            {
                "schema": "tvl.semantic-review-request.v1",
                "request_id": "semantic-evidence-1",
                "claim": {
                    "claim_id": "claim-1",
                    "statement": "Example SDK 4.2 is generally available.",
                    "scope": {"package": "example-sdk", "version": "4.2"},
                },
                "evidence": {
                    "evidence_id": "evidence-1",
                    "quote": "Example SDK 4.2 is generally available.",
                    "quote_sha256": sha256_text(
                        "Example SDK 4.2 is generally available."
                    ),
                    "relationship_proposal": "supports",
                    "source_receipt": {
                        "source_uri": (
                            "https://docs.example.invalid/releases/4.2"
                        ),
                        "content_sha256": "a" * 64,
                        "capture_scope": "full_source",
                        "snapshot_id": "snapshot-1",
                        "receipt_sha256": (
                            "c0f59c49ddda535ac77e23d50d9e205e"
                            "acc44883d4b4ffe904e4e8d3739e2a32"
                        ),
                    },
                },
            },
        )

    def test_versioned_json_schemas_publish_the_review_contract(self) -> None:
        schema_dir = Path(__file__).parents[1] / "schemas"
        schemas = {
            name: json.loads((schema_dir / name).read_text(encoding="utf-8"))
            for name in (
                "semantic-review-request.v1.schema.json",
                "semantic-judge-request.v1.schema.json",
                "semantic-review.v1.schema.json",
                "semantic-verifier-receipt.v1.schema.json",
                "semantic-dispatch.v1.schema.json",
            )
        }

        self.assertEqual(
            {
                name: schema["properties"]["schema"]["const"]
                for name, schema in schemas.items()
            },
            {
                "semantic-review-request.v1.schema.json": (
                    "tvl.semantic-review-request.v1"
                ),
                "semantic-judge-request.v1.schema.json": (
                    "tvl.semantic-judge-request.v1"
                ),
                "semantic-review.v1.schema.json": "tvl.semantic-review.v1",
                "semantic-verifier-receipt.v1.schema.json": (
                    "tvl.semantic-verifier-receipt.v1"
                ),
                "semantic-dispatch.v1.schema.json": "tvl.semantic-dispatch.v1",
            },
        )
        self.assertTrue(
            {
                "provider",
                "provider_version",
                "model",
                "prompt_sha256",
                "instruction_hashes",
                "output_sha256",
                "usage",
            }.issubset(
                schemas["semantic-verifier-receipt.v1.schema.json"]["required"]
            )
        )
        evidence_schema = json.loads(
            (schema_dir / "evidence.v1.schema.json").read_text(encoding="utf-8")
        )
        citation_properties = evidence_schema["properties"]["citation"]["properties"]
        self.assertIn("semantic_review", citation_properties)
        self.assertIn("semantic_review_receipt_sha256s", citation_properties)

        request_schema = schemas["semantic-review-request.v1.schema.json"]
        judge_schema = schemas["semantic-judge-request.v1.schema.json"]
        self.assertEqual(
            judge_schema["properties"]["claim"],
            request_schema["properties"]["claim"],
        )
        self.assertEqual(
            judge_schema["properties"]["evidence"],
            request_schema["properties"]["evidence"],
        )
        dispatch_schema = schemas["semantic-dispatch.v1.schema.json"]
        run_schema = dispatch_schema["properties"]["runs"]["items"]
        self.assertFalse(run_schema["additionalProperties"])
        self.assertTrue(
            {"disposition", "reason"}.issubset(run_schema["required"])
        )
        self.assertFalse(
            run_schema["properties"]["attempt_receipts"]["items"][
                "additionalProperties"
            ]
        )
        self.assertFalse(
            dispatch_schema["properties"]["aggregates"]["additionalProperties"][
                "additionalProperties"
            ]
        )
        self.assertEqual(
            dispatch_schema["properties"]["totals"]["additionalProperties"],
            {"type": "number", "minimum": 0},
        )
        receipt_schema = schemas["semantic-verifier-receipt.v1.schema.json"]
        self.assertEqual(len(receipt_schema["allOf"]), 3)
        self.assertEqual(
            receipt_schema["properties"]["usage"]["additionalProperties"],
            {"type": "number", "minimum": 0},
        )
        self.assertEqual(
            dispatch_schema["$defs"]["receipt"]["properties"]["stream_capture"],
            receipt_schema["properties"]["stream_capture"],
        )

    def test_review_rejects_an_unpinned_verifier_receipt(self) -> None:
        with self.assertRaisesRegex(ContractError, "receipt"):
            SemanticReview(
                request_id="semantic-evidence-1",
                evidence_id="evidence-1",
                family="independent-family-a",
                verdict="ENTAILS",
                rationale_summary="The quote entails the claim.",
                verifier_receipt_sha256="not-a-digest",
            )

    def test_verifier_timeout_status_and_flag_cannot_disagree(self) -> None:
        with self.assertRaisesRegex(ContractError, "timed_out"):
            VerifierReceipt(
                family="independent-family-a",
                provider="fixture-verifier-a",
                provider_version="1.0",
                model="semantic-a",
                prompt_sha256="a" * 64,
                instruction_hashes=(),
                output_sha256="b" * 64,
                started_at=NOW,
                ended_at=NOW + timedelta(seconds=1),
                status="succeeded",
                exit_code=0,
                timed_out=True,
                usage={},
            )

    def test_runtime_receipts_and_reviews_reject_wrong_schema_versions(self) -> None:
        receipt = EntailingVerifier().run(
            (SemanticReviewRequest.from_evidence(claim(), evidence()),)
        ).receipt
        with self.assertRaisesRegex(ContractError, "schema"):
            replace(receipt, schema="tvl.semantic-verifier-receipt.v2")
        review = EntailingVerifier().run(
            (SemanticReviewRequest.from_evidence(claim(), evidence()),)
        ).reviews[0]
        with self.assertRaisesRegex(ContractError, "schema"):
            replace(review, schema="tvl.semantic-review.v2")

    def test_receipt_timestamps_must_be_timezone_aware(self) -> None:
        receipt = EntailingVerifier().run(
            (SemanticReviewRequest.from_evidence(claim(), evidence()),)
        ).receipt

        with self.assertRaisesRegex(ContractError, "timezone"):
            replace(receipt, started_at=NOW.replace(tzinfo=None))

    def test_large_integer_usage_remains_a_valid_exact_counter(self) -> None:
        receipt = EntailingVerifier().run(
            (SemanticReviewRequest.from_evidence(claim(), evidence()),)
        ).receipt

        updated = replace(receipt, usage={"input_tokens": 10**1000})

        self.assertEqual(updated.usage["input_tokens"], 10**1000)

    def test_identity_rejects_non_canonical_whitespace(self) -> None:
        with self.assertRaisesRegex(ContractError, "canonical"):
            VerifierIdentity(provider="fixture-verifier ", model="semantic-a")

    def test_request_rejects_forged_quote_and_source_receipt_digests(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "quote_sha256"):
            replace(request, quote_sha256="0" * 64)
        with self.assertRaisesRegex(ContractError, "source_receipt_sha256"):
            replace(request, source_receipt_sha256="0" * 64)


class EntailingVerifier:
    family = "independent-family-a"
    identity = VerifierIdentity(provider="fixture-verifier-a", model="semantic-a")

    def __init__(self) -> None:
        self.received: tuple[SemanticReviewRequest, ...] = ()

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        self.received = requests
        receipt = VerifierReceipt(
            family=self.family,
            provider="fixture-verifier-a",
            provider_version="1.0",
            model="semantic-a",
            prompt_sha256="c" * 64,
            instruction_hashes=("d" * 64,),
            output_sha256="e" * 64,
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=2),
            status="succeeded",
            exit_code=0,
            timed_out=False,
            usage={"input_tokens": 10, "output_tokens": 3, "cost_usd": 0.01},
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                SemanticReview(
                    request_id=request.request_id,
                    evidence_id=request.evidence_id,
                    family=self.family,
                    verdict="ENTAILS",
                    rationale_summary="The quote directly states the scoped claim.",
                    verifier_receipt_sha256=receipt.digest,
                )
                for request in requests
            ),
        )


class NonEntailingVerifier(EntailingVerifier):
    family = "independent-family-b"
    identity = VerifierIdentity(provider="fixture-verifier-b", model="semantic-b")

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        entailing_run = super().run(requests)
        receipt = replace(
            entailing_run.receipt,
            provider="fixture-verifier-b",
            model="semantic-b",
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                SemanticReview(
                    request_id=request.request_id,
                    evidence_id=request.evidence_id,
                    family=self.family,
                    verdict="DOES_NOT_ENTAIL",
                    rationale_summary="The quote does not establish general availability.",
                    verifier_receipt_sha256=receipt.digest,
                )
                for request in requests
            ),
        )


class StreamingEntailingVerifier(EntailingVerifier):
    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        run = super().run(requests)
        stdout = b'{"schema":"fixture-semantic-output"}'
        stderr = b"fixture diagnostic"
        receipt = replace(
            run.receipt,
            output_sha256=sha256_bytes(stdout),
            stderr_sha256=sha256_bytes(stderr),
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                replace(
                    review,
                    verifier_receipt_sha256=receipt.digest,
                )
                for review in run.reviews
            ),
            attempt_streams=(
                VerifierAttemptStream(
                    receipt_sha256=receipt.digest,
                    stdout=stdout,
                    stderr=stderr,
                ),
            ),
        )


class MismatchedStreamVerifier(EntailingVerifier):
    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        run = super().run(requests)
        return replace(
            run,
            attempt_streams=(
                VerifierAttemptStream(
                    receipt_sha256=run.receipt.digest,
                    stdout=b"not the receipted stdout",
                    stderr=b"",
                ),
            ),
        )


class MissingRawStreamVerifier(StreamingEntailingVerifier):
    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        run = super().run(requests)
        receipt = replace(
            run.receipt,
            stdout_captured_bytes=len(run.attempt_streams[0].stdout),
            stderr_captured_bytes=len(run.attempt_streams[0].stderr),
            stdout_truncated=False,
            stderr_truncated=False,
            stream_limit_bytes=1_048_576,
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                replace(review, verifier_receipt_sha256=receipt.digest)
                for review in run.reviews
            ),
        )


class AbstainingVerifier(EntailingVerifier):
    family = "abstaining-family"
    identity = VerifierIdentity(provider="fixture-verifier-b", model="semantic-b")

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        entailing_run = super().run(requests)
        receipt = replace(
            entailing_run.receipt,
            provider="fixture-verifier-b",
            model="semantic-b",
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                SemanticReview(
                    request_id=request.request_id,
                    evidence_id=request.evidence_id,
                    family=self.family,
                    verdict="ABSTAIN",
                    rationale_summary="The quote is ambiguous at this scope.",
                    verifier_receipt_sha256=receipt.digest,
                )
                for request in requests
            ),
        )


class IndependentEntailingVerifierB(NonEntailingVerifier):
    family = "independent-entailing-family-b"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        non_entailing = super().run(requests)
        return replace(
            non_entailing,
            reviews=tuple(
                replace(
                    review,
                    verdict="ENTAILS",
                    rationale_summary="The quote entails the proposal.",
                )
                for review in non_entailing.reviews
            ),
        )


class AliasEntailingVerifier(EntailingVerifier):
    family = "alias-family"


class AliasContradictingVerifier(EntailingVerifier):
    family = "z-alias-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        entailing_run = super().run(requests)
        return VerifierRun(
            receipt=entailing_run.receipt,
            reviews=tuple(
                replace(
                    review,
                    verdict="DOES_NOT_ENTAIL",
                    rationale_summary="A correlated alias returned the opposite verdict.",
                )
                for review in entailing_run.reviews
            ),
        )


class SearchFamilyVerifier(EntailingVerifier):
    family = "antigravity-cli"


class RenamedSearchVerifier(EntailingVerifier):
    family = "renamed-search-family"
    identity = VerifierIdentity(provider="antigravity-cli", model="search-model")

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        original = super().run(requests)
        receipt = replace(
            original.receipt,
            provider="antigravity-cli",
            model="search-model",
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                replace(review, verifier_receipt_sha256=receipt.digest)
                for review in original.reviews
            ),
        )


class ForgedIdentityVerifier(EntailingVerifier):
    family = "forged-identity-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        original = super().run(requests)
        receipt = replace(
            original.receipt,
            provider="forged-provider",
            model="forged-model",
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                replace(review, verifier_receipt_sha256=receipt.digest)
                for review in original.reviews
            ),
        )


class TimeoutVerifier:
    family = "timeout-family"
    identity = VerifierIdentity(provider="fixture-timeout", model="semantic-timeout")

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        return VerifierRun(
            receipt=VerifierReceipt(
                family=self.family,
                provider="fixture-timeout",
                provider_version="1.0",
                model="semantic-timeout",
                prompt_sha256="3" * 64,
                instruction_hashes=("4" * 64,),
                output_sha256="5" * 64,
                started_at=NOW,
                ended_at=NOW + timedelta(seconds=3),
                status="timeout",
                exit_code=None,
                timed_out=True,
                usage={"input_tokens": 7, "cost_usd": 0.02},
            ),
            reviews=(),
        )


class MissingReviewVerifier(EntailingVerifier):
    family = "missing-review-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        successful = super().run(requests)
        return VerifierRun(receipt=successful.receipt, reviews=())


class InjectedOutputVerifier(EntailingVerifier):
    family = "injection-resistant-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        legitimate = super().run(requests)
        return VerifierRun(
            receipt=legitimate.receipt,
            reviews=tuple(
                replace(review, family="page-injected-family")
                for review in legitimate.reviews
            ),
        )


class MutatingVerifier(EntailingVerifier):
    family = "mutating-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        requests[0].claim_scope["version"] = "poisoned"
        return super().run(requests)


class ScopeRecordingVerifier(EntailingVerifier):
    family = "scope-recording-family"

    def __init__(self) -> None:
        super().__init__()
        self.observed_version: str | None = None

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        self.observed_version = str(requests[0].claim_scope["version"])
        return super().run(requests)


class RecoveryEntailingVerifier(EntailingVerifier):
    family = "recovery-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        first = super().run(requests)
        receipt = replace(first.receipt, attempt_kind="recovery")
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                replace(review, verifier_receipt_sha256=receipt.digest)
                for review in first.reviews
            ),
        )


class RecoveredAfterTimeoutVerifier(RecoveryEntailingVerifier):
    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        initial_recovery = super().run(requests)
        recovery_receipt = replace(
            initial_recovery.receipt,
            started_at=NOW + timedelta(seconds=4),
            ended_at=NOW + timedelta(seconds=6),
        )
        recovered = VerifierRun(
            receipt=recovery_receipt,
            reviews=tuple(
                replace(review, verifier_receipt_sha256=recovery_receipt.digest)
                for review in initial_recovery.reviews
            ),
        )
        timeout = replace(
            TimeoutVerifier().run(requests).receipt,
            family=self.family,
            provider=recovered.receipt.provider,
            model=recovered.receipt.model,
            started_at=NOW + timedelta(seconds=1),
            ended_at=NOW + timedelta(seconds=4),
            attempt_kind="recovery",
        )
        failed = replace(
            timeout,
            prompt_sha256="8" * 64,
            output_sha256="9" * 64,
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            status="failed",
            exit_code=1,
            timed_out=False,
            attempt_kind="primary",
            usage={"input_tokens": 2, "cost_usd": 0.03},
        )
        return VerifierRun(
            receipt=recovered.receipt,
            reviews=recovered.reviews,
            prior_attempt_receipts=(failed, timeout),
        )


class MisorderedAttemptVerifier(RecoveredAfterTimeoutVerifier):
    family = "misordered-attempt-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        run = super().run(requests)
        return replace(
            run,
            prior_attempt_receipts=tuple(reversed(run.prior_attempt_receipts)),
        )


class ResolvingJudge(EntailingVerifier):
    family = "fresh-judge"
    identity = VerifierIdentity(provider="fixture-judge", model="bounded-judge")

    def __init__(self) -> None:
        super().__init__()
        self.judge_requests: tuple[SemanticJudgeRequest, ...] = ()

    def run(self, requests: tuple[SemanticJudgeRequest, ...]) -> VerifierRun:
        self.judge_requests = requests
        receipt = VerifierReceipt(
            family=self.family,
            provider="fixture-judge",
            provider_version="1.0",
            model="bounded-judge",
            prompt_sha256="f" * 64,
            instruction_hashes=("1" * 64,),
            output_sha256="2" * 64,
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            status="succeeded",
            exit_code=0,
            timed_out=False,
            usage={"input_tokens": 5, "output_tokens": 1},
        )
        return VerifierRun(
            receipt=receipt,
            reviews=tuple(
                SemanticReview(
                    request_id=request.request_id,
                    evidence_id=request.evidence_id,
                    family=self.family,
                    verdict="ENTAILS",
                    rationale_summary="The scoped wording is directly entailed.",
                    verifier_receipt_sha256=receipt.digest,
                )
                for request in requests
            ),
        )


class DuplicateJudge(ResolvingJudge):
    family = "duplicate-judge"

    def run(self, requests: tuple[SemanticJudgeRequest, ...]) -> VerifierRun:
        resolved = super().run(requests)
        first = resolved.reviews[0]
        return VerifierRun(
            receipt=resolved.receipt,
            reviews=(
                first,
                replace(
                    first,
                    verdict="DOES_NOT_ENTAIL",
                    rationale_summary="Conflicting duplicate output.",
                ),
            ),
        )


class FailedIdentityVerifier(TimeoutVerifier):
    family = "failed-identity-family"
    identity = VerifierIdentity(
        provider="discarded-provider", model="discarded-model"
    )

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        run = super().run(requests)
        receipt = replace(
            run.receipt,
            provider=self.identity.provider,
            model=self.identity.model,
            status="failed",
            exit_code=1,
            timed_out=False,
        )
        return replace(run, receipt=receipt)


class DiscardedIdentityJudge(ResolvingJudge):
    family = "discarded-identity-judge"
    identity = FailedIdentityVerifier.identity


class NegativeUsageVerifier(EntailingVerifier):
    family = "negative-usage-family"

    def run(self, requests: tuple[SemanticReviewRequest, ...]) -> VerifierRun:
        run = super().run(requests)
        receipt = replace(run.receipt, usage={"cost_usd": -0.01})
        return replace(
            run,
            receipt=receipt,
            reviews=tuple(
                replace(review, verifier_receipt_sha256=receipt.digest)
                for review in run.reviews
            ),
        )


class SemanticDispatcherTests(unittest.TestCase):
    def test_one_independent_family_can_satisfy_medium_review(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())
        verifier = EntailingVerifier()

        result = SemanticDispatcher([verifier]).dispatch(
            [request], minimum_families=1, search_provider_family="antigravity-cli"
        )

        self.assertEqual(verifier.received, (request,))
        self.assertEqual(result.aggregates["evidence-1"].verdict, "ENTAILS")
        self.assertEqual(
            result.aggregates["evidence-1"].accepted_families,
            ("independent-family-a",),
        )
        self.assertTrue(result.aggregates["evidence-1"].policy_satisfied)
        self.assertEqual(result.totals["attempts"], 1)
        self.assertEqual(result.totals["input_tokens"], 10)
        self.assertEqual(result.totals["latency_seconds"], 2.0)

    def test_only_disagreements_reach_an_anonymized_bounded_judge(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())
        judge = ResolvingJudge()

        result = SemanticDispatcher(
            [EntailingVerifier(), NonEntailingVerifier()]
        ).dispatch(
            [request],
            minimum_families=2,
            search_provider_family="antigravity-cli",
            judge=judge,
            max_judge_requests=1,
        )

        self.assertEqual(len(judge.judge_requests), 1)
        judge_payload = judge.judge_requests[0].to_dict()
        self.assertEqual(
            judge_payload["positions"],
            [
                {
                    "verdict": "DOES_NOT_ENTAIL",
                    "rationale_summary": (
                        "The quote does not establish general availability."
                    ),
                },
                {
                    "verdict": "ENTAILS",
                    "rationale_summary": (
                        "The quote directly states the scoped claim."
                    ),
                },
            ],
        )
        self.assertNotIn("family", str(judge_payload))
        self.assertNotIn("sealed", str(judge_payload).lower())
        aggregate = result.aggregates["evidence-1"]
        self.assertEqual(aggregate.verdict, "ENTAILS")
        self.assertEqual(aggregate.judge_family, "fresh-judge")
        self.assertTrue(aggregate.policy_satisfied)
        self.assertEqual(result.totals["attempts"], 3)
        self.assertEqual(result.totals["judge_attempts"], 1)

    def test_timeout_discarded_and_recovery_attempts_remain_in_totals(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        result = SemanticDispatcher(
            [SearchFamilyVerifier(), RecoveredAfterTimeoutVerifier()]
        ).dispatch(
            [request], minimum_families=1, search_provider_family="antigravity-cli"
        )

        self.assertTrue(result.aggregates["evidence-1"].policy_satisfied)
        self.assertEqual(
            result.aggregates["evidence-1"].accepted_families,
            ("recovery-family",),
        )
        self.assertEqual(result.totals["attempts"], 4)
        self.assertEqual(result.totals["failed_attempts"], 1)
        self.assertEqual(result.totals["timeout_attempts"], 1)
        self.assertEqual(result.totals["discarded_attempts"], 1)
        self.assertEqual(result.totals["recovery_attempts"], 2)
        self.assertEqual(result.totals["input_tokens"], 29)
        self.assertEqual(result.totals["cost_usd"], 0.07)
        self.assertEqual(result.totals["latency_seconds"], 8.0)

    def test_abstention_is_not_a_disagreement_or_an_accepted_family(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())
        judge = ResolvingJudge()

        result = SemanticDispatcher(
            [EntailingVerifier(), AbstainingVerifier()], judge=judge
        ).dispatch(
            [request], minimum_families=2, search_provider_family="antigravity-cli"
        )

        aggregate = result.aggregates["evidence-1"]
        self.assertEqual(aggregate.verdict, "ENTAILS")
        self.assertEqual(aggregate.accepted_families, ("independent-family-a",))
        self.assertFalse(aggregate.policy_satisfied)
        self.assertEqual(judge.judge_requests, ())
        self.assertEqual(result.totals.get("judge_attempts", 0), 0)

    def test_successful_verifier_must_explicitly_review_every_request(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "exactly one review"):
            SemanticDispatcher([MissingReviewVerifier()]).dispatch(
                [request],
                minimum_families=1,
                search_provider_family="antigravity-cli",
            )

    def test_judge_must_return_exactly_one_resolution_per_disagreement(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())

        with self.assertRaisesRegex(ContractError, "exactly one judge review"):
            SemanticDispatcher(
                [EntailingVerifier(), NonEntailingVerifier()], judge=DuplicateJudge()
            ).dispatch(
                [request],
                minimum_families=2,
                search_provider_family="antigravity-cli",
            )

    def test_each_verifier_receives_an_isolated_request_batch(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())
        observer = ScopeRecordingVerifier()

        SemanticDispatcher([MutatingVerifier(), observer]).dispatch(
            [request],
            minimum_families=1,
            search_provider_family="antigravity-cli",
        )

        self.assertEqual(observer.observed_version, "4.2")
        self.assertEqual(request.claim_scope["version"], "4.2")

    def test_renaming_the_same_provider_and_model_does_not_add_independence(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())

        result = SemanticDispatcher(
            [EntailingVerifier(), AliasEntailingVerifier()]
        ).dispatch(
            [request],
            minimum_families=2,
            search_provider_family="antigravity-cli",
        )

        aggregate = result.aggregates["evidence-1"]
        self.assertEqual(aggregate.accepted_families, ("alias-family",))
        self.assertFalse(aggregate.policy_satisfied)
        self.assertEqual(result.totals["discarded_attempts"], 1)

    def test_conflicting_aliases_of_one_identity_fail_closed(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        result = SemanticDispatcher(
            [EntailingVerifier(), AliasContradictingVerifier()]
        ).dispatch(
            [request],
            minimum_families=1,
            search_provider_family="antigravity-cli",
        )

        aggregate = result.aggregates["evidence-1"]
        self.assertEqual(aggregate.verdict, "ABSTAIN")
        self.assertEqual(aggregate.accepted_families, ())
        self.assertFalse(aggregate.policy_satisfied)
        self.assertEqual(
            {item["reason"] for item in result.to_dict()["runs"]},
            {"correlated_identity_conflict"},
        )

    def test_adapter_receipt_must_match_its_configured_identity(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "configured identity"):
            SemanticDispatcher([ForgedIdentityVerifier()]).dispatch(
                [request], minimum_families=1
            )

    def test_attempt_chain_must_be_chronological(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "attempt chain"):
            SemanticDispatcher([MisorderedAttemptVerifier()]).dispatch(
                [request], minimum_families=1
            )

    def test_attempt_stream_must_match_its_receipt_digest(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "stdout stream"):
            SemanticDispatcher([MismatchedStreamVerifier()]).dispatch(
                [request], minimum_families=1
            )

    def test_capture_metadata_requires_every_raw_attempt_stream(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "cover every attempt"):
            SemanticDispatcher([MissingRawStreamVerifier()]).dispatch(
                [request], minimum_families=1
            )

    def test_discarded_verifier_identity_cannot_be_reused_as_judge(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())

        with self.assertRaisesRegex(ContractError, "fresh and independent"):
            SemanticDispatcher(
                [EntailingVerifier(), NonEntailingVerifier(), FailedIdentityVerifier()],
                judge=DiscardedIdentityJudge(),
            ).dispatch([request], minimum_families=2)

    def test_negative_or_non_finite_usage_fails_closed(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        with self.assertRaisesRegex(ContractError, "usage"):
            SemanticDispatcher([NegativeUsageVerifier()]).dispatch(
                [request], minimum_families=1
            )
        with self.assertRaisesRegex(ContractError, "usage"):
            replace(
                EntailingVerifier().run((request,)).receipt,
                usage={"cost_usd": math.inf},
            )

    def test_search_provider_identity_is_excluded_even_when_family_is_renamed(self) -> None:
        request = SemanticReviewRequest.from_evidence(claim(), evidence())

        result = SemanticDispatcher([RenamedSearchVerifier()]).dispatch(
            [request],
            minimum_families=1,
            search_provider_identity=VerifierIdentity(
                provider="antigravity-cli", model="search-model"
            ),
        )

        aggregate = result.aggregates["evidence-1"]
        self.assertEqual(aggregate.accepted_families, ())
        self.assertFalse(aggregate.policy_satisfied)
        self.assertEqual(result.totals["discarded_attempts"], 1)
        run_payload = result.to_dict()["runs"][0]
        self.assertEqual(run_payload["disposition"], "discarded")
        self.assertEqual(run_payload["reason"], "search_provider_identity")


class FixtureSearchProvider:
    def __init__(
        self,
        *,
        relationship: str = "supports",
        quote: str = "Example SDK 4.2 is generally available.",
    ) -> None:
        self.relationship = relationship
        self.quote = quote

    def run(self, prompt: str, **kwargs: object) -> ProviderRun:
        _ = (prompt, kwargs)
        envelope = {
            "schema": "tvl.search-result.v1",
            "query": "Example SDK 4.2 availability",
            "candidates": [
                {
                    "source_uri": "https://docs.example.invalid/releases/4.2",
                    "relationship": self.relationship,
                    "quote": self.quote,
                }
            ],
        }
        raw = (json.dumps({"event": "result", "result": envelope}) + "\n").encode()
        receipt = ProviderReceipt(
            provider="antigravity-cli",
            binary="fixture-search",
            binary_version="1.0",
            model="search-model",
            effort="low",
            output_format="stream-json",
            output_schema_sha256="6" * 64,
            prompt_sha256="7" * 64,
            instruction_hashes=(),
            command_redacted=("fixture-search",),
            cwd=".",
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            exit_code=0,
            timed_out=False,
            provider_print_timeout_seconds=30,
            outer_timeout_seconds=40,
            stdout_sha256=sha256_text(raw.decode()),
            stderr_sha256=sha256_text(""),
            environment_keys=(),
            environment_fingerprint=sha256_text("{}"),
            usage={"input_tokens": 4, "output_tokens": 2},
        )
        return ProviderRun(receipt=receipt, stdout=raw, stderr=b"", events=({"event": "result", "result": envelope},))


class FixtureRetriever:
    def __init__(
        self, text: str = "Example SDK 4.2 is generally available."
    ) -> None:
        self.text = text

    def fetch(self, uri: str) -> FetchedSource:
        raw = self.text.encode()
        return FetchedSource(
            requested_uri=uri,
            final_uri=uri,
            media_type="text/plain",
            charset="utf-8",
            raw=raw,
            normalized_text=raw.decode(),
            retrieved_at=NOW.isoformat().replace("+00:00", "Z"),
            status_code=200,
        )


class SemanticOrchestratorTests(unittest.TestCase):
    def test_live_verification_uses_independent_dispatch_for_medium_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lake = EvidenceLake(Path(directory) / "lake")

            result = run_live_verification(
                claim(temporality="dynamic"),
                lake=lake,
                policy=SourcePolicy(
                    domain_classes={
                        "docs.example.invalid": "official_release"
                    }
                ),
                provider=FixtureSearchProvider(),
                retriever=FixtureRetriever(),
                semantic_dispatcher=SemanticDispatcher([EntailingVerifier()]),
                cwd=Path(directory),
                model_knowledge_cutoff=None,
            )

            stored = lake.evidence_for_claim("claim-1")
            self.assertEqual(result["closure"]["state"], "SUPPORTED")
            self.assertTrue(result["closure"]["closed"])
            self.assertEqual(
                stored[0].citation["semantic_verifier_families"],
                ["independent-family-a"],
            )
            self.assertNotIn(
                "antigravity-cli",
                stored[0].citation["semantic_verifier_families"],
            )
            self.assertEqual(result["semantic_dispatch"]["totals"]["attempts"], 1)
            self.assertEqual(lake.verify_integrity(), [])

    def test_semantic_attempt_streams_are_preserved_in_cold_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lake = EvidenceLake(Path(directory) / "lake")

            run_live_verification(
                claim(temporality="dynamic"),
                lake=lake,
                policy=SourcePolicy(
                    domain_classes={
                        "docs.example.invalid": "official_release"
                    }
                ),
                provider=FixtureSearchProvider(),
                retriever=FixtureRetriever(),
                semantic_dispatcher=SemanticDispatcher(
                    [StreamingEntailingVerifier()]
                ),
                cwd=Path(directory),
                model_knowledge_cutoff=None,
            )

            receipts = [
                event["payload"]
                for event in lake.read_ledger("bronze", "blob-receipts")
                if event["payload"]["source_uri"].startswith(
                    "urn:tvl:semantic-verifier-stream:"
                )
            ]

            self.assertEqual(len(receipts), 2)
            by_channel = {
                receipt["source_uri"].rsplit(":", 1)[-1]: receipt
                for receipt in receipts
            }
            self.assertEqual(
                lake.blob_path(by_channel["stdout"]["content_sha256"]).read_bytes(),
                b'{"schema":"fixture-semantic-output"}',
            )
            self.assertEqual(
                lake.blob_path(by_channel["stderr"]["content_sha256"]).read_bytes(),
                b"fixture diagnostic",
            )
            self.assertEqual(lake.verify_integrity(), [])

    def test_high_risk_closure_uses_two_families_and_fresh_judge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lake = EvidenceLake(Path(directory) / "lake")
            judge = ResolvingJudge()

            result = run_live_verification(
                claim(risk="high", temporality="dynamic"),
                lake=lake,
                policy=SourcePolicy(
                    domain_classes={
                        "docs.example.invalid": "official_release"
                    },
                    risk_requirements={
                        "high": RiskRequirement(True, 0, True, 2)
                    },
                ),
                provider=FixtureSearchProvider(),
                retriever=FixtureRetriever(),
                semantic_dispatcher=SemanticDispatcher(
                    [EntailingVerifier(), NonEntailingVerifier()],
                    judge=judge,
                    max_judge_requests=1,
                ),
                cwd=Path(directory),
                model_knowledge_cutoff=None,
            )

            stored = lake.evidence_for_claim("claim-1")[0]
            self.assertEqual(result["closure"]["state"], "SUPPORTED")
            self.assertEqual(
                stored.citation["semantic_verifier_families"],
                ["independent-family-a", "independent-family-b"],
            )
            self.assertEqual(
                stored.citation["semantic_review"]["judge_family"],
                "fresh-judge",
            )

    def test_entailing_a_refutation_proposal_produces_refuted_closure(self) -> None:
        quote = "Example SDK 4.2 is not generally available."
        with tempfile.TemporaryDirectory() as directory:
            result = run_live_verification(
                claim(temporality="dynamic"),
                lake=EvidenceLake(Path(directory) / "lake"),
                policy=SourcePolicy(
                    domain_classes={
                        "docs.example.invalid": "official_release"
                    }
                ),
                provider=FixtureSearchProvider(
                    relationship="refutes", quote=quote
                ),
                retriever=FixtureRetriever(quote),
                semantic_dispatcher=SemanticDispatcher([EntailingVerifier()]),
                cwd=Path(directory),
                model_knowledge_cutoff=None,
            )

            self.assertEqual(result["closure"]["state"], "REFUTED")
            self.assertTrue(result["closure"]["closed"])


class SemanticAdversarialFixtureTests(unittest.TestCase):
    def test_adversarial_cases_remain_data_only_and_fail_closed(self) -> None:
        fixture_path = (
            Path(__file__).parent / "fixtures" / "semantic-review-cases.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases = {case["id"]: case for case in fixture["cases"]}

        correlated = cases["correlated-error"]
        with self.assertRaisesRegex(ContractError, "unique"):
            SemanticDispatcher(
                [EntailingVerifier() for _ in range(correlated["duplicate_count"])]
            )
        correlated_result = SemanticDispatcher(
            [EntailingVerifier(), AliasEntailingVerifier()]
        ).dispatch(
            [SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())],
            minimum_families=2,
            search_provider_family="antigravity-cli",
        )
        self.assertEqual(
            sorted(correlated["renamed_families"]),
            sorted([EntailingVerifier.family, AliasEntailingVerifier.family]),
        )
        self.assertEqual(
            len(correlated_result.aggregates["evidence-1"].accepted_families),
            correlated["expected_independent_identities"],
        )
        self.assertFalse(
            correlated_result.aggregates["evidence-1"].policy_satisfied
        )

        injected = cases["prompt-injection"]
        injected_payload = evidence().to_dict()
        injected_payload["quote"] = injected["quote"]
        injected_payload["quote_sha256"] = sha256_text(injected["quote"])
        request_payload = SemanticReviewRequest.from_evidence(
            claim(), Evidence.from_dict(injected_payload)
        ).to_dict()
        self.assertEqual(
            sorted(request_payload), sorted(injected["expected_top_level_keys"])
        )
        self.assertEqual(request_payload["evidence"]["quote"], injected["quote"])
        with self.assertRaisesRegex(ContractError, "family"):
            SemanticDispatcher([InjectedOutputVerifier()]).dispatch(
                [
                    SemanticReviewRequest.from_evidence(
                        claim(), Evidence.from_dict(injected_payload)
                    )
                ],
                minimum_families=1,
                search_provider_family="antigravity-cli",
            )

        unanimous = cases["unanimous-wrong"]
        with tempfile.TemporaryDirectory() as directory:
            result = run_live_verification(
                claim(temporality="dynamic"),
                lake=EvidenceLake(Path(directory) / "lake"),
                policy=SourcePolicy(
                    domain_classes={
                        "docs.example.invalid": unanimous["source_class"]
                    }
                ),
                provider=FixtureSearchProvider(),
                retriever=FixtureRetriever(),
                semantic_dispatcher=SemanticDispatcher(
                    [EntailingVerifier(), IndependentEntailingVerifierB()]
                ),
                cwd=Path(directory),
                model_knowledge_cutoff=None,
            )
        closure = result["closure"]
        self.assertEqual(closure["state"], unanimous["expected_state"])
        self.assertFalse(closure["gates"]["G3_PRIMARY_AUTHORITY"])
        self.assertTrue(closure["gates"]["G7_SEMANTIC_REVIEW"])
        self.assertEqual(
            closure["authority"]["semantic_verifier_families"],
            sorted(unanimous["families"]),
        )

        leakage = cases["judge-leakage"]
        judge = ResolvingJudge()
        SemanticDispatcher(
            [EntailingVerifier(), NonEntailingVerifier()], judge=judge
        ).dispatch(
            [SemanticReviewRequest.from_evidence(claim(risk="high"), evidence())],
            minimum_families=2,
            search_provider_family="antigravity-cli",
        )
        judge_text = json.dumps(judge.judge_requests[0].to_dict())
        for forbidden in leakage["forbidden_terms"]:
            self.assertNotIn(forbidden, judge_text)


if __name__ == "__main__":
    unittest.main()
