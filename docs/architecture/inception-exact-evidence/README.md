# Inception A3 — exact code, source and citation evidence preflight

Status: **OWNER IMPLEMENTATION PREPARATION ONLY**  
Upstream profile issue: `ed3c/enterprise_agent_system#15`  
Owner issue: `ed3c/truth-verify-loop#23`

This leaf prepares an independent evidence path for commit-pinned code, source
locators and citation claims. Deterministic physical/lexical readback, parser
coverage, semantic review, disagreement, repair and Human escalation remain
separately attributable. The verifier may block or admit evidence for review; it
cannot become the proposer or a canonical task/effect/Human writer.

## Exact preparation subject

```text
repository        ed3c/truth-verify-loop
base commit       ce0c90f0c9bc87427d433ce537eea7f3a0fca008
base tree         9ab841a793c4cdbca82a5a31eddb2dcd7485f3c1
branch            agent/inception-a3-exact-evidence
controller commit 6e0a916fd06dd8635d77c9a8c4d1b475185ea13e
controller tree   c3851a6953d456d0342a9776eed28561c1af0ca1
packet digest     sha256:8ed7553094f26df439f796e25ef83cdbe6916d0c50e8e659905ca12d3bd44ad6
packet bundle     sha256:dc4473b3195a738e55eb49c43661b6e1f4ea7f95c66749454776f2003b18ebc3
```

## Existing canonical mechanisms to adapt

| Existing path | Reusable responsibility | Boundary |
|---|---|---|
| `harness/model.py` | versioned claim/evidence/provider contracts | new profile fields need explicit versioning |
| `harness/retriever.py` | independent capture, egress safety and quote readback | search snippets are not evidence |
| `harness/documents.py` | stable document/snapshot/chunk identity | code subjects need commit/tree/parser identity |
| `harness/closure.py` | categorical multi-gate closure | no single score or model self-promotion |
| `harness/lake*.py` | immutable cold/warm history and rebuildable hot state | hot index is not canonical evidence |
| `harness/semantic*.py` | independent semantic review attempts | lexical match is not entailment |

## Target State Machine

```text
EXACT_SUBJECT_BOUND
→ PATH_AND_LOCATOR_CONFINED
→ PHYSICAL_OR_LEXICAL_READBACK_VERIFIED
→ PARSER_COVERAGE_DECLARED
→ SYMBOL_SNIPPET_OR_QUOTE_VERIFIED
→ SEMANTIC_REVIEW_DISPATCHED
→ DISAGREEMENT_OR_ABSTENTION_RECONCILED
→ SUPPORTED | REFUTED | CONFLICTED | STALE | UNVERIFIABLE
→ REPAIR_OR_HUMAN_REVIEW
```

## Required evidence dimensions

```text
repository + commit + tree
normalized symlink-confined path
line range + snippet digest
symbol/signature + parser identity and coverage
source subject digest + exact locator + quote digest
lexical/physical Gate result
independent semantic reviewer identity and receipt
attempt denominator, disagreement, abstention and freshness state
```

## Provisional lease

```text
docs/architecture/inception-exact-evidence/**
schemas/inception-code-evidence.v1.schema.json
schemas/inception-citation-claim.v1.schema.json
harness/inception_evidence.py
tests/test_inception_evidence.py
examples/inception-evidence/**
.github/workflows/inception-a3-evidence.yml
```

Existing closure, retriever, lake and semantic modules remain read-only until an
adapter test proves an unavoidable public-seam extension. Private code/source
bytes and service-account homes never enter portable fixtures or receipts.

## First implementation commit admission

The next commit must add strict code-evidence and citation-claim schemas plus a
hollow or failing test for stale subject, path escape, line/snippet mismatch,
missing symbol, unavailable parser coverage or lexical-to-semantic promotion.
No exact business claim may be marked supported by the preparation fixture.

## Evidence ceiling

```text
OWNER_PREPARATION_READY
schema/adapter code       NOT_STARTED
private independent run  NOT_EXERCISED
parser coverage canary   NOT_EXERCISED
semantic disagreement    NOT_EXERCISED
business claim closure   ABSENT
Human admission/release  NOT_PERFORMED
```

Machine authority: [`preflight.json`](preflight.json).
