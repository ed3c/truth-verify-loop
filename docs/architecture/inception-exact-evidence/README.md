# Inception A3 — exact code, source and citation evidence

Status: **FIRST PUBLIC IMPLEMENTATION CANDIDATE**  
Upstream profile issue: `ed3c/enterprise_agent_system#15`  
Owner issue: `ed3c/truth-verify-loop#23`

This leaf is a true child of the green baseline convergence subject `c01254547672a9ad03345c9013b20d3d1049e274`. It implements a bounded, read-only exact-evidence validator for commit-pinned code locations and citation claims. Physical/lexical readback remains separate from independent semantic interpretation; the validator cannot become the proposer or a canonical task/effect/Human writer.

## Exact lineage

```text
repository        ed3c/truth-verify-loop
base commit       c01254547672a9ad03345c9013b20d3d1049e274
base tree         577213165a091aee389e9c7028570eb8cf6da1c7
branch            agent/inception-a3-exact-evidence-v2
controller commit 6e0a916fd06dd8635d77c9a8c4d1b475185ea13e
controller tree   c3851a6953d456d0342a9776eed28561c1af0ca1
packet digest     sha256:8ed7553094f26df439f796e25ef83cdbe6916d0c50e8e659905ca12d3bd44ad6
packet bundle     sha256:dc4473b3195a738e55eb49c43661b6e1f4ea7f95c66749454776f2003b18ebc3
```

## Implementation subjects

```text
schemas/inception-code-evidence.v1.schema.json
schemas/inception-citation-claim.v1.schema.json
harness/inception_evidence.py
tests/test_inception_evidence.py
```

The code-evidence contract binds:

```text
repository + exact 40-hex commit + exact 40-hex tree
repository-relative, symlink-confined path
1-based line range
exact snippet SHA-256
optional symbol
parser identity + declared coverage
physical state + claims_not_proven
```

For `python-ast`, the validator independently parses the file and checks the named function/class symbol. `text-only` cannot claim symbol coverage. `unavailable` cannot claim parser coverage.

The citation contract binds:

```text
source digest
exact locator
quote + quote digest
lexical state
semantic state
independent semantic receipt when exercised
claims_not_proven
```

A lexical `PASS` with `semantic_state = NOT_EXERCISED` remains lexical evidence only. `SUPPORTED` / `REFUTED` / `CONFLICTED` / `ABSTAIN` require a separate semantic receipt digest; this shape check does not prove that the independent semantic run actually occurred.

## State Machine

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

The current implementation covers the deterministic physical/lexical half through `SYMBOL_SNIPPET_OR_QUOTE_VERIFIED`. Independent semantic dispatch and business-claim closure remain separate existing harness lanes.

## Deterministic disagreement controls

The public tests refuse:

```text
mutable commit subjects
path traversal
symlink escape
out-of-range lines
snippet digest mismatch
missing AST symbol
false parser coverage
quote digest mismatch
semantic promotion without an independent receipt shape
```

## Writer lease

```text
docs/architecture/inception-exact-evidence/**
schemas/inception-code-evidence.v1.schema.json
schemas/inception-citation-claim.v1.schema.json
harness/inception_evidence.py
tests/test_inception_evidence.py
examples/inception-evidence/**
.github/workflows/inception-a3-evidence.yml
```

Existing closure, retriever, lake and semantic modules remain read-only. Private code/source bytes and service-account paths never enter portable fixtures or receipts.

## Next transition

`RUN_PUBLIC_REPOSITORY_BLOB_READBACK_AND_INDEPENDENT_SEMANTIC_CANARY`

The next atom must bind a real public repository commit/tree/blob and independently read it back, then run a separate semantic canary without letting that reviewer mutate the evidence source.

## Evidence ceiling

```text
code/citation schemas          DETERMINISTIC_CANDIDATE
physical/lexical validator     DETERMINISTIC_CANDIDATE
mutation controls              DETERMINISTIC_CANDIDATE
real public blob readback      NOT_EXERCISED
private evidence               NOT_EXERCISED
independent semantic canary    NOT_EXERCISED
business claim closure         ABSENT
Human admission / release      NOT_PERFORMED
```
