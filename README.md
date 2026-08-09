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
  --lake .tvlake
```

The provider adapter uses a non-shell argument vector, pins the `tvl.search-result.v1` output schema, and accepts candidates only from the terminal provider result. `step_update`, tool output, and fetched-page text cannot become the final result envelope. Candidate sources remain untrusted until the deterministic retriever captures the URL, blocks private-network targets, hashes the response, and finds the exact quote.

Source capture proves provenance, not entailment. Medium-risk claims require one recorded semantic verifier family, while high- and critical-risk claims require two independent verifier families before closure. The current `run-agy` path records the search provider as one semantic family, so high- and critical-risk claims remain fail-closed until independent reviews are supplied; provider-neutral dispatch is tracked in [issue #9](https://github.com/ed3c/truth-verify-loop/issues/9).

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
- [deterministic core](core/tv-score.py)
- [synthetic core fixture](examples/synthetic/fixtures)
- [fixture topology checker](scripts/check_fixture_layout.py)

The clean release excludes historical runs, cached private source pages, credentials, and private evaluation corpora.

License: MIT. Core delivery: [PRD #1](https://github.com/ed3c/truth-verify-loop/issues/1). Live verification MVP: [PRD #4](https://github.com/ed3c/truth-verify-loop/issues/4). Production roadmap: [#6](https://github.com/ed3c/truth-verify-loop/issues/6), [#7](https://github.com/ed3c/truth-verify-loop/issues/7), [#8](https://github.com/ed3c/truth-verify-loop/issues/8), [#9](https://github.com/ed3c/truth-verify-loop/issues/9), [#10](https://github.com/ed3c/truth-verify-loop/issues/10), [#11](https://github.com/ed3c/truth-verify-loop/issues/11).
