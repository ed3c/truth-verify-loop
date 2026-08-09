# Standards, security, operations, and roadmap

Companion to [Agentic Data Lake verification MVP](agentic-data-lake-mvp.md).

## 11. Provenance mapping

| TVL record | W3C PROV concept |
|---|---|
| captured source bytes, claim, evidence, closure | `prov:Entity` |
| search run, deterministic fetch, normalization, closure | `prov:Activity` |
| model/provider, harness version, human owner | `prov:SoftwareAgent` / `prov:Agent` |
| evidence quote | `prov:wasQuotedFrom` |
| closure input | `prov:wasDerivedFrom` |
| refreshed closure | `prov:wasRevisionOf` |
| stale or superseded closure | `prov:invalidatedAtTime` |

The next storage adapter should export these relations as JSON-LD without changing internal IDs.

## 12. Lineage and telemetry mapping

A future OpenLineage exporter maps:

- one verification attempt to a `Run`;
- the claim-verification workflow to a `Job`;
- source blobs and prior evidence to input datasets;
- normalized evidence and closures to output datasets;
- closure gates to a custom data-quality assertion facet.

A future OpenTelemetry exporter maps:

- provider execution to a CLI span;
- candidate search, source fetch, quote validation, and closure to child spans;
- non-zero exit and timeout to error status;
- high-cardinality prompts and raw outputs to opt-in events or cold blobs, not span attributes.

## 13. Threat model

| Threat | MVP control |
|---|---|
| prompt injection in a source page | sources are data; script/style bodies are dropped; no page text is executed |
| shell injection | provider runs with `shell=False` and an argument vector |
| SSRF | DNS and address-class checks, HTTPS default, redirect revalidation |
| citation fabrication | exact quote must occur in captured source text |
| source mutation | raw content hash, retrieval time, and closure expiry |
| model/provider drift | binary version, model, effort, prompt, instruction, and output hashes |
| secret leakage | allowlisted environment, redacted prompt argument, existing public-surface scanner |
| hot-index corruption | SQLite is disposable; canonical blobs and ledgers rebuild it |
| ledger modification | per-stream hash chain plus top-level SHA-256 manifest |
| correlated model agreement | high- and critical-risk closure requires two named semantic verifier families; deterministic capture and authority policy remain separate from votes |

Production hardening still needed: process isolation, egress proxy, DNS pinning, signed manifests, multi-writer transactions, object-lock retention, malware scanning, and policy-controlled redaction.

## 14. Local layout

```text
harness/
  model.py          typed claim/evidence/search contracts
  documents.py      versioned document snapshots and structural chunks
  policy.py         cutoff, freshness, risk, and source authority policy
  providers.py      Antigravity and sealed-fixture adapters
  retriever.py      safe deterministic source capture
  lake.py           cold/warm/hot memory backend
  closure.py        deterministic Evidence Closure gates
  orchestrator.py   end-to-end live loop
  cli.py            runnable interface
schemas/            portable JSON contracts
config/             example authority and risk policy
examples/live-search/
tests/              deterministic positive and negative controls
```

Runtime data defaults to `.tvlake/` and is excluded from version control.

## 15. Run the MVP

### Deterministic sealed fixture

```bash
python3 -m harness.cli run-fixture \
  --claim examples/live-search/fixture-claim.json \
  --evidence examples/live-search/fixture-evidence.jsonl \
  --policy config/source-policy.example.json \
  --source examples/live-search/fixture-source.txt \
  --receipt examples/live-search/fixture-provider-receipt.json \
  --lake .tvlake
```

### Decide whether live search is required

```bash
python3 -m harness.cli decide \
  --claim examples/live-search/claim.json \
  --model-knowledge-cutoff 2025-12-01T00:00:00Z
```

### Run Antigravity live search

Authenticate `agy` outside the harness, then run:

```bash
python3 -m harness.cli run-agy \
  --claim examples/live-search/claim.json \
  --policy config/source-policy.example.json \
  --model-knowledge-cutoff 2025-12-01T00:00:00Z \
  --lake .tvlake
```

Do not add an unsafe permission-bypass flag for research over untrusted pages. Keep the working directory read-only or disposable when possible.

### Inspect and verify memory

```bash
python3 -m harness.cli search-hot --lake .tvlake --query Python
python3 -m harness.cli verify-lake --lake .tvlake
python3 -m harness.cli manifest --lake .tvlake
```

Repository checks remain:

```bash
bash verify.sh
```

## 16. MVP acceptance criteria

The MVP is acceptable when all are true:

- dynamic and unpinned claims trigger live search;
- an unknown model cutoff is preserved as unknown;
- Antigravity output is captured with a provider receipt;
- candidate URLs are re-fetched independently;
- private-network and local targets are rejected;
- quotes are checked against captured source text;
- source authority is policy-derived, not model-derived;
- cold blobs are immutable and deduplicated;
- document snapshots are content-pinned and revisions are explicit;
- structural chunks preserve heading path, spans, and technical symbols;
- warm ledgers detect modification;
- hot claim and document memory are searchable and rebuildable;
- conflict, stale evidence, snippets, and missing authority turn gates red;
- no historical private corpus or credential is committed.

## 17. Next increments

1. **Storage adapter** — Parquet and Apache Iceberg tables for claims, evidence, runs, and closures; branch/tag retention for audit snapshots.
2. **Lineage exporter** — OpenLineage START/COMPLETE/FAIL events and data-quality facets.
3. **Telemetry exporter** — OpenTelemetry traces with GenAI and CLI semantic attributes.
4. **Document adapters** — PDF page coordinates, Git repository blobs pinned to commit SHA, package registries, standards versioning, and JavaScript-rendered docs through a sandboxed browser.
5. **Change detection** — conditional requests, source content diffs, CDC events, and automatic closure invalidation.
6. **Memory lifecycle** — promotion/demotion jobs, retention classes, access-control-aware retrieval, and per-user/team scopes.
7. **Evaluation** — sealed temporal fixtures, planted stale docs, source conflicts, prompt injection, citation drift, and model/provider A/B runs.
8. **Enterprise controls** — signed manifests, object lock, KMS, policy-as-code, tenant isolation, audit review, data deletion, and human approval for critical closures.

## 18. Official references

- [Antigravity CLI repository](https://github.com/google-antigravity/antigravity-cli)
- [Antigravity CLI changelog](https://github.com/google-antigravity/antigravity-cli/blob/main/CHANGELOG.md)
- [Apache Iceberg branching and tagging](https://iceberg.apache.org/docs/latest/branching/)
- [OpenLineage facets and extensibility](https://openlineage.io/docs/spec/facets/)
- [OpenLineage data quality assertions](https://openlineage.io/docs/1.46.0/spec/facets/dataset-facets/data_quality_assertions/)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OpenTelemetry CLI spans](https://opentelemetry.io/docs/specs/semconv/cli/cli-spans/)
- [Databricks agent memory](https://docs.databricks.com/aws/en/agents/agent-framework/stateful-agents)
- [Google Cloud: lakehouse for the agentic era](https://cloud.google.com/blog/products/data-analytics/the-future-of-data-lakehouse-for-the-agentic-era)
