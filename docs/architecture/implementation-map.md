# Live verification implementation map

Status: MVP in draft PR #5

This map is the shortest route from a claim to the code, durable records, tests, and production follow-up.

## End-to-end path

```text
Claim contract
  -> temporal/freshness policy
  -> provider search receipt
  -> independent source capture
  -> versioned document snapshot + chunks
  -> evidence contract
  -> Evidence Closure gates
  -> cold/warm/hot memory
```

## Code ownership by boundary

| Boundary | Module | Canonical output |
|---|---|---|
| claim, evidence, provider result types | `harness/model.py` | versioned Python contracts matching `schemas/` |
| cutoff, temporality, freshness, authority, risk | `harness/policy.py` | `VerificationDecision`, `RiskRequirement` |
| Antigravity execution and receipt capture | `harness/providers.py` | `ProviderRun`, `ProviderReceipt`, `tvl.search-result.v1` |
| SSRF-safe independent HTTP capture | `harness/retriever.py` | raw source bytes, normalized text, quote span |
| stable document/snapshot/chunk identity | `harness/documents.py` | `DocumentSnapshot`, `DocumentChunk` |
| immutable blob and hash-chain primitives | `harness/lake_base.py` | cold blobs, warm ledger events, `MANIFEST.sha256` |
| claim/evidence/closure projection | `harness/lake_records.py` | current claim, evidence, closure, record search |
| document/chunk projection | `harness/lake_documents.py` | current snapshot and FTS/searchable chunks |
| storage facade | `harness/lake.py` | `EvidenceLake` |
| deterministic closure | `harness/closure.py` | `tvl.evidence-closure.v1` |
| live orchestration | `harness/orchestrator.py` | retrieval events, accepted evidence, closure, manifest |
| operator interface | `harness/cli.py` | `decide`, `run-fixture`, `run-agy`, `verify-lake`, `manifest`, `search-hot` |

## Durable record flow

```text
bronze/
  blobs/sha256/       immutable source/provider/session bytes
  blob-receipts.jsonl
  agent-sessions.jsonl
  retrieval-events.jsonl

silver/
  claims.jsonl
  evidence.jsonl
  documents.jsonl
  chunks.jsonl
  revisions.jsonl

gold/
  closures.jsonl
  coverage-ledger.jsonl

hot/index.sqlite3     disposable current-state and FTS projection
MANIFEST.sha256       digest list for canonical bronze/silver/gold files
```

Warm ledgers are append-only and hash chained. `hot/index.sqlite3` is not canonical and can be rebuilt. Evidence cannot be projected unless its source blob and provider-receipt blob exist and match their digests.

## Evidence Closure gates

1. `G1_CITATION_INTEGRITY` — exact quote and digest are valid.
2. `G2_FRESHNESS` — evidence is inside the claim SLA and validity interval.
3. `G3_PRIMARY_AUTHORITY` — the risk policy has enough primary/official evidence.
4. `G4_INDEPENDENT_CORROBORATION` — distinct independent domains meet policy.
5. `G5_REQUIRED_SOURCE_CLASSES` — claim-specific source classes are present.
6. `G6_FULL_SOURCE_CAPTURE` — snippet-only grounding cannot satisfy a full-capture tier.
7. `G7_SEMANTIC_REVIEW` — quote/claim entailment has enough independent verifier families.
8. `G8_NO_UNRESOLVED_CONFLICT` — fresh support and refutation do not coexist unresolved.

The state is categorical: `SUPPORTED`, `REFUTED`, `CONFLICTED`, `STALE`, or `UNVERIFIABLE`. Only `SUPPORTED` and `REFUTED` with every required gate green are closed.

## Test map

| Failure class | Test module |
|---|---|
| cutoff, stale memory, unpinned versions, source policy | `tests/test_policy.py` |
| unsafe flags, structured result extraction, usage receipts | `tests/test_providers.py` |
| SSRF and executable HTML bodies | `tests/test_retriever.py` |
| stable URI identity, content revisions, structural chunks | `tests/test_documents.py` |
| conflict, stale evidence, snippets, semantic-family gates | `tests/test_closure.py` |
| missing blobs, ledger tamper, manifest, hot projection | `tests/test_lake.py` |

Run all repository checks with:

```bash
bash verify.sh
```

## Production sequence

1. #9 — independent semantic verifier dispatch, because high-risk closure must not depend on one search family.
2. #11 — temporal/conflict/injection/provider A/B evaluation and release budgets.
3. #8 — PDF, commit-pinned Git, registry, and sandboxed browser capture.
4. #6 — Parquet/Iceberg storage adapter and time-travel publication.
5. #7 — W3C PROV, OpenLineage, and OpenTelemetry exporters.
6. #10 — egress isolation, signatures/object lock, multi-tenancy, and lifecycle governance.

This order first proves correctness, then broadens capture, then scales storage and governance. Storage scale must not outrun the ability to detect false support.
