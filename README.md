# truth-verify-loop

Measurable claim verification with deterministic scoring, blind fixtures, live source receipts, and tiered agent memory.

The repository separates two layers:

1. the deterministic mutation, aggregation, scoring, and sealed-fixture core;
2. an Agentic Data Lake harness that bridges model knowledge cutoffs to current technical sources.

A search agent proposes evidence. It does not decide truth. The harness re-fetches cited sources, validates exact quotes, stores immutable receipts, and emits an explicit Evidence Closure: `SUPPORTED`, `REFUTED`, `CONFLICTED`, `STALE`, or `UNVERIFIABLE`.

## Verify

```bash
bash verify.sh
```

The suite checks claim and verdict contracts, controlled mutations, false-supported scoring, fixture blindness, source-capture controls, memory integrity, closure gates, and the public surface.

## Run the sealed Agentic Data Lake fixture

```bash
python3 -m harness.cli run-fixture \
  --claim examples/live-search/fixture-claim.json \
  --evidence examples/live-search/fixture-evidence.jsonl \
  --policy config/source-policy.example.json \
  --source examples/live-search/fixture-source.txt \
  --receipt examples/live-search/fixture-provider-receipt.json \
  --lake .tvlake
```

## Decide whether a current claim requires live search

```bash
python3 -m harness.cli decide \
  --claim examples/live-search/claim.json \
  --model-knowledge-cutoff 2025-12-01T00:00:00Z
```

## Run with Antigravity CLI

Authenticate `agy` outside this repository and use a build that supports structured output with `--json-schema` and typed terminal `result` events. Then run:

```bash
python3 -m harness.cli run-agy \
  --claim examples/live-search/claim.json \
  --policy config/source-policy.example.json \
  --model-knowledge-cutoff 2025-12-01T00:00:00Z \
  --model gemini-3.6-flash-low \
  --effort low \
  --provider-print-timeout 300 \
  --outer-timeout 330 \
  --semantic-config config/semantic-verifiers.example.json \
  --lake .tvlake
```

Copy the semantic config before use and replace every `replace-with-*` command,
provider, and model value with two genuinely independent verifier identities and
an optional third judge identity. Commands use JSON on stdin/stdout; their
contracts are published as `schemas/semantic-review-command.v1.schema.json` and
`schemas/semantic-review-batch.v1.schema.json`. The example placeholders
intentionally fail loudly until configured.

The provider adapter uses a non-shell argument vector, pins the `tvl.search-result.v1` output schema, and accepts candidates only from the terminal provider result. `step_update`, tool output, and fetched-page text cannot become the final result envelope. Directional candidates must select an exact quote that directly entails the entire proposed relationship; partial or merely relevant passages are `context`. Candidate sources remain untrusted until the deterministic retriever captures the URL, blocks private-network targets, hashes the response, and finds the exact quote.

Source capture proves provenance, not entailment. Medium-risk claims require one recorded semantic verifier family, while high- and critical-risk claims require two independent verifier families before closure. `harness.semantic.SemanticDispatcher` is the provider-neutral review seam: callers inject independently configured verifier adapters and may configure a fresh bounded judge for genuine `ENTAILS`/`DOES_NOT_ENTAIL` disagreements. Each reviewer receives an isolated data-only batch containing scoped claims, exact quotes, and content-addressed document-snapshot receipts; it does not contain sealed truth, authority decisions, or other reviewer labels. `ENTAILS` means that the quote entails the proposed `supports` or `refutes` relationship—it does not always mean support.

When a dispatcher is passed to `run_live_verification`, every adapter declares a configured provider/model identity and its receipts must match that identity. The search provider identity is excluded from reviewer coverage even if a family is renamed, and multiple family labels backed by the same provider/model count once. Conflicting aliases of one identity are all discarded rather than resolved by family name. Every chronological verifier attempt chain—including failed, timeout, discarded, and recovery attempts—retains provider/model/version, prompt/instruction/output hashes, usage, cost, and latency; the dispatch also records whether each run was accepted, discarded, or ineligible and why. Successful adapters must return exactly one receipt-bound review per request; `ABSTAIN` is explicit, does not count as family coverage, and does not trigger the judge. A non-entailing or unresolved quote is stored as contextual evidence and cannot close the claim.

`run-agy --semantic-config` constructs subprocess adapters from the versioned configuration and enforces provider/model identity independence before live search starts. Without that option, the CLI retains the MVP compatibility behavior of recording the search provider as one family; that fallback cannot satisfy a high- or critical-risk two-family policy.

Semantic commands start in an empty disposable working directory with a minimal environment and receive only the versioned request on stdin. Stdout and stderr are each bounded to 1 MiB; every bounded attempt stream and receipt is stored in cold memory, including failures, timeouts, and recoveries. This is process hygiene, not an OS sandbox: configured commands are trusted local adapters and production deployments still need a sandbox or container when executing untrusted verifier code.

Source authority comes only from `config/source-policy.example.json`. Claim-level `trusted_domains` can guide retrieval but cannot promote an unknown domain to an official or primary source class.

## Memory tiers

- **cold**: immutable content-addressed source, provider, and session blobs;
- **warm**: append-only hash-chained claims, evidence, revisions, retrievals, and closures;
- **hot**: rebuildable SQLite current-state and full-text projection.

Runtime memory is written under `.tvlake/` and is not committed. Rebuild the disposable hot projection from validated canonical ledgers without rewriting them:

```bash
python3 -m harness.cli rebuild-hot --lake .tvlake
python3 -m harness.cli search-hot --lake .tvlake --query Python
```

## Layout

- [architecture and harness contract](docs/architecture/agentic-data-lake-mvp.md)
- [implementation map and production sequence](docs/architecture/implementation-map.md)
- [Evidence Closure decision](docs/architecture/decisions/0001-evidence-closure-not-truth-score.md)
- [truth verification skill](skills/truth-verify-loop/SKILL.md)
- [live harness CLI](harness/cli.py)
- [deterministic hot replay](harness/lake_rebuild.py)
- [portable schemas](schemas)
- [source authority policy](config/source-policy.example.json)
- [semantic verifier configuration](config/semantic-verifiers.example.json)
- [deterministic core](core/tv-score.py)
- [synthetic core fixture](examples/synthetic/fixtures)
- [fixture topology checker](scripts/check_fixture_layout.py)

The clean release excludes historical runs, cached private source pages, credentials, and private evaluation corpora.

License: MIT. Core delivery: [PRD #1](https://github.com/ed3c/truth-verify-loop/issues/1). Live verification MVP: [PRD #4](https://github.com/ed3c/truth-verify-loop/issues/4). Production roadmap: [#6](https://github.com/ed3c/truth-verify-loop/issues/6), [#7](https://github.com/ed3c/truth-verify-loop/issues/7), [#8](https://github.com/ed3c/truth-verify-loop/issues/8), [#9](https://github.com/ed3c/truth-verify-loop/issues/9), [#10](https://github.com/ed3c/truth-verify-loop/issues/10), [#11](https://github.com/ed3c/truth-verify-loop/issues/11).
