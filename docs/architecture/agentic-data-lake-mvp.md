# Agentic Data Lake verification MVP

Status: implemented MVP contract

Last reviewed: 2026-08-09

## 1. Purpose

`truth-verify-loop` bridges two different kinds of knowledge:

1. **parametric memory** — what a model may remember up to a declared or unknown knowledge cutoff;
2. **observed evidence** — what an independently captured source said at a specific URI, content hash, and time.

The model cutoff is provenance, not evidence. A current technical claim is not closed merely because a model recalls it. The harness decides when live retrieval is mandatory, asks a fast search agent such as Antigravity CLI for candidate sources, captures those sources independently, validates exact quotations, and applies deterministic evidence gates.

The output is an **Evidence Closure**, not a scalar truth score:

- `SUPPORTED`
- `REFUTED`
- `CONFLICTED`
- `STALE`
- `UNVERIFIABLE`

A closure records scope, freshness, missing evidence, conflicts, and the conditions that supersede it.

## 2. Standards position

There is no single standards-body specification named “Agentic Data Lake.” This repository defines a small conformance profile from existing open specifications and current platform patterns.

| Concern | Alignment | MVP implementation |
|---|---|---|
| immutable history and time travel | Apache Iceberg snapshots, branches, tags, retention | content-addressed blobs plus deterministic manifests; Iceberg adapter deferred |
| run, job, input, and output lineage | OpenLineage events and facets | append-only run and retrieval ledgers with namespaced fields; exporter deferred |
| interoperable provenance | W3C PROV-O `Entity`, `Activity`, `Agent`, derivation, quotation, revision, invalidation | claim, source, receipt, evidence, and closure IDs with revision rules |
| trace naming and CLI execution | OpenTelemetry semantic conventions for GenAI and CLI programs | provider start/end, exit code, usage, hashes, timeout, and environment fingerprint |
| agent memory | episodic versus semantic memory; short-term versus long-term stores | cold session receipts, warm normalized facts, hot current projections |
| grounded search | first-party source lists, citations, and trusted-domain restrictions | search agent proposes candidates; deterministic retriever re-fetches and verifies them |

This profile keeps contracts portable. The local backend can later be replaced by Iceberg/Parquet, an OpenLineage service, an OTLP collector, or a governed memory service without changing claim or closure semantics.

## 3. System boundary

```text
                    declared / unknown model cutoff
                                  |
                                  v
claim -> temporal policy -> live-search decision -------------------+
                                  |                                  |
                                  v                                  |
                         Antigravity CLI (`agy`)                      |
                         candidate URLs + quotes                     |
                                  |                                  |
                           untrusted boundary                        |
                                  v                                  |
                       deterministic HTTP capture                    |
                   SSRF guard + byte cap + content hash              |
                                  |                                  |
                                  v                                  |
                    quote validation + source policy                 |
                                  |                                  |
                                  v                                  |
      +--------------------- Agentic Data Lake ----------------------+
      | bronze: raw blobs, provider streams, receipts, retrievals    |
      | silver: claims, evidence, revisions                          |
      | gold: closures, coverage ledger                              |
      | hot: SQLite current-state and full-text projection           |
      +--------------------------------------------------------------+
                                  |
                                  v
                 deterministic Evidence Closure gates
```

The search model never assigns final authority. Source labels are recalculated only from the standing `source-policy.example.json`. Claim-level `trusted_domains` may guide retrieval, but they cannot promote an unknown domain to `official_doc` or another primary class.

## 4. Memory structure

### 4.1 Cold memory: immutable receipts

Path: `bronze/blobs/sha256/<prefix>/<digest>`

Cold memory contains raw bytes that must remain reproducible:

- captured source responses;
- Antigravity `stdout` and `stderr` streams;
- provider run receipts;
- future browser recordings, repository blobs, PDFs, and sandbox artifacts.

Properties:

- content-addressed by SHA-256;
- write once and verify on reuse;
- not injected into every prompt;
- retained according to legal, privacy, and cost policy;
- listed in `MANIFEST.sha256`.

### 4.2 Warm memory: normalized evidence history

Paths:

- `bronze/*.jsonl`
- `silver/*.jsonl`
- `gold/*.jsonl`

Warm memory is append-only and hash chained. It stores:

- retrieval events and failures;
- exact agent and harness receipts;
- normalized document snapshots and structural chunks;
- normalized claim/evidence contracts;
- revisions and supersession events;
- closure results and coverage metrics.

Warm memory is the durable semantic and episodic history. It is suitable for later Parquet/Iceberg export.

### 4.3 Hot memory: current projection

Path: `hot/index.sqlite3`

Hot memory contains only rebuildable current state:

- latest document snapshot and searchable structural chunks;
- latest claim contract;
- latest evidence pointers;
- latest closure;
- source freshness;
- text-search projection.

Hot memory can be deleted and rebuilt from validated warm ledgers. Rebuild does not append or rewrite canonical records:

```bash
python3 -m harness.cli rebuild-hot --lake .tvlake
```

The replay validates blob references, claim/evidence contracts, document and chunk digests, closure states, ledger hash chains, and the manifest before replacing SQLite. Only chunks belonging to each current document snapshot enter the new FTS projection.

### 4.4 Promotion and demotion

```text
new source receipt
  -> cold blob
  -> normalized warm evidence
  -> closure gates pass
  -> hot current projection
  -> TTL expires or conflict appears
  -> hot state becomes STALE/CONFLICTED
  -> a new live run creates a revision
```

Promotion requires explicit gates. Retrieval frequency or repeated model agreement does not promote a claim by itself.

## 5. Claim contract

Schema: [`schemas/claim.v1.schema.json`](../../schemas/claim.v1.schema.json)

Each claim includes:

- stable `claim_id`;
- exact statement;
- scope such as product, version, platform, channel, environment, or region;
- risk: `low`, `medium`, `high`, `critical`;
- temporality: `static`, `versioned`, `dynamic`, `ephemeral`;
- freshness SLA;
- owner and falsifier;
- last verified time;
- required source classes and retrieval-domain hints;
- prior closure state.

### Live-search decision rules

Live search is required when any of these conditions apply:

- the claim is dynamic or ephemeral;
- a versioned claim says `latest`, `current`, `stable`, `main`, or has no immutable version;
- its freshness SLA expired or it was never verified;
- the prior state is `CONFLICTED`, `STALE`, or `UNVERIFIABLE`;
- a high-risk claim has no declared model cutoff;
- a non-static claim may have changed after the cutoff;
- a critical claim is evaluated.

The harness never guesses a model cutoff. Unknown stays unknown.

## 6. Search-provider contract

The Antigravity adapter invokes an argument vector, never a shell string:

```text
agy --print <prompt> \
  --output-format stream-json \
  --json-schema <tvl.search-result.v1-schema> \
  --print-timeout <provider-deadline> \
  [--model ...] [--effort ...]
```

The schema, output-format, provider deadline, model, effort, and permission-boundary flags cannot be overridden through generic extra arguments. The harness also applies an outer recovery watchdog. Its deadline must be strictly greater than `--print-timeout`; invalid relationships fail before version probing or provider execution. The provider therefore gets the first chance to emit its terminal result or its own timeout outcome, while the outer watchdog remains available to recover a wedged process.

The provider receipt records:

- binary and reported version;
- model and effort when supplied;
- redacted command vector;
- prompt, instruction-file, and output-schema hashes;
- working directory;
- start/end time, provider print timeout, outer recovery timeout, outer-timeout status, and exit code;
- `stdout` and `stderr` hashes;
- inherited environment key names and a non-reversible fingerprint;
- token and cache-read usage when present.

`timed_out=true` means the outer recovery watchdog killed the process. A provider that reaches its own print deadline exits normally from the subprocess perspective and is represented by its non-zero exit code. In both cases, the receipt accounts for usage already emitted on `stdout`; absence of a terminal result still fails closed.

The requested final payload is `tvl.search-result.v1`: candidate URLs, relationships, and short verbatim quotes. For typed streams, the parser accepts the current `event` discriminator and the legacy `type` discriminator, but rejects a stream that mixes them. It requires exactly one terminal `result` event containing exactly one distinct result envelope, and accepts the envelope only from that event. Identical `response` and `structured_output` mirrors are canonicalized and deduplicated; conflicting envelopes remain ambiguous and fail closed. The parser never scans `step_update`, tool output, or fetched-page payloads for a final envelope; those events remain available for usage accounting. A missing or ambiguous terminal result, malformed schema, or non-zero provider exit fails closed.

## 7. Independent source capture

Search output is a hint. The deterministic retriever then:

1. accepts HTTP(S) candidates, with HTTPS required by default;
2. rejects userinfo, local hostnames, loopback, link-local, private, multicast, reserved, and unspecified IPs;
3. revalidates redirects;
4. limits redirect count, response size, media types, and timeout;
5. stores the exact response bytes in cold memory;
6. extracts normalized text without scripts, styles, templates, SVG, or `noscript` content;
7. checks the proposed quotation against captured text;
8. assigns source authority from standing policy only.

A search-engine snippet is not equivalent to a full source capture. High-risk closures reject `agent_grounded_snippet` evidence.

Known MVP boundary: PDF bytes can be preserved, but the standard-library retriever does not extract PDF text. Such a candidate remains unverified until a PDF adapter supplies page-aware citation coordinates.

## 8. Document memory contract

Schemas:

- [`schemas/document-snapshot.v1.schema.json`](../../schemas/document-snapshot.v1.schema.json)
- [`schemas/document-chunk.v1.schema.json`](../../schemas/document-chunk.v1.schema.json)

A stable `document_id` represents one canonical URI. A `snapshot_id` pins that document to a content hash. A changed hash creates a new snapshot, stores `supersedes_snapshot_id`, and appends a `REVISES_OR_SUPERSEDES` event to `silver/revisions.jsonl`; observing identical bytes again reuses the same snapshot identity while retrieval events preserve the new observation time.

Each snapshot records source type, authority, product, version, channel, commit SHA when available, media type, retrieval and validity times, capture scope, and the cold-blob digest.

The standard-library MVP chunks normalized Markdown-like text deterministically by heading and paragraph, with bounded size and overlap. Each chunk records:

- structural heading path;
- character span in normalized text;
- text hash and token estimate;
- extracted API, symbol, flag, and constant-like identifiers;
- parent document and snapshot IDs.

SQLite FTS indexes current chunks for low-latency retrieval. The chunk ledger retains older snapshots for audit and future temporal retrieval. Vector embeddings are deliberately an adapter, not the canonical identity of a chunk.

## 9. Evidence contract

Schema: [`schemas/evidence.v1.schema.json`](../../schemas/evidence.v1.schema.json)

An accepted evidence record contains:

- claim and evidence IDs;
- canonical source URI and domain;
- independently assigned source class;
- `supports`, `refutes`, or `context` relationship;
- exact quote and quote hash;
- source content hash and capture scope;
- provider receipt hash;
- retrieval, publication, and validity times;
- explicit `quote_verified: true` citation receipt;
- semantic verifier family receipts for the `supports` or `refutes` relationship.

The lake refuses to index evidence unless both the source blob and provider receipt blob exist.

## 10. Evidence Closure

Schema: [`schemas/evidence-closure.v1.schema.json`](../../schemas/evidence-closure.v1.schema.json)

Current deterministic gates:

| Gate | Meaning |
|---|---|
| `G1_CITATION_INTEGRITY` | a directional quote has a valid digest and was found in the captured source |
| `G2_FRESHNESS` | directional evidence is inside the claim freshness SLA and validity window |
| `G3_PRIMARY_AUTHORITY` | risk policy has enough official, standard, source-code, or first-party evidence |
| `G4_INDEPENDENT_CORROBORATION` | enough distinct independent source domains exist |
| `G5_REQUIRED_SOURCE_CLASSES` | claim-specific classes are present |
| `G6_FULL_SOURCE_CAPTURE` | risk policy does not rely on snippets alone |
| `G7_SEMANTIC_REVIEW` | every directional citation has semantic review and the risk policy has enough independent verifier families |
| `G8_NO_UNRESOLVED_CONFLICT` | fresh support and refutation do not coexist |

Risk defaults:

- low: no mandatory primary, independent source, or semantic verifier family;
- medium: primary source, full capture, and one semantic verifier family;
- high: primary source, full capture, one independent domain, and two semantic verifier families;
- critical: primary source, full capture, two independent domains, two semantic verifier families, and live retrieval every run.

These defaults are policy, not universal truth. Teams should tighten them per domain.

## Operational companion

See [standards, security, operations, and roadmap](operations-and-standards.md) for provenance mappings, the threat model, commands, acceptance criteria, and production increments.
