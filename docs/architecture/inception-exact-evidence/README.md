# Inception A3 — exact code, source and citation evidence

Status: **PUBLIC BLOB + DUAL-METHOD SEMANTIC CANARY CANDIDATE**  
Upstream profile issue: `ed3c/enterprise_agent_system#15`  
Owner issue: `ed3c/truth-verify-loop#23`

This leaf is a true child of the green baseline convergence subject `c01254547672a9ad03345c9013b20d3d1049e274`. It implements a bounded, read-only exact-evidence validator and now exercises it against one real public Git object. Physical/lexical readback remains separate from semantic interpretation; neither the validator nor the canary can become the proposer or a canonical task/effect/Human writer.

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
harness/inception_public_canary.py
tests/test_inception_public_canary.py
```

The code-evidence contract binds repository/commit/tree, a repository-relative symlink-confined path, a 1-based line range, exact snippet SHA-256, symbol and parser coverage. `python-ast` independently parses the file; `text-only` cannot claim symbol coverage and `unavailable` cannot claim parser coverage.

The citation contract keeps source digest, locator, quote digest, lexical state and semantic state separate. A lexical `PASS` with `semantic_state = NOT_EXERCISED` remains lexical evidence only.

## Public Git-object canary

The verification canary reads this immutable public subject through the local Git object database created by an exact public checkout:

```text
repository  ed3c/truth-verify-loop
commit      c01254547672a9ad03345c9013b20d3d1049e274
tree        577213165a091aee389e9c7028570eb8cf6da1c7
path        harness/orchestrator.py
symbol      run_live_verification
```

The canary performs:

```text
git rev-parse <commit>^{tree}
        ↓ exact tree equality
git show <commit>:harness/orchestrator.py
        ↓ exact public blob bytes
isolated temporary materialization
        ↓
line/snippet digest + Python AST symbol validator
        ↓
lexical PASS
```

It never mutates the source repository and deletes its temporary materialization when the canary returns.

## Dual-method semantic fixture

The canary then asks a deliberately narrow fixture statement: whether `run_live_verification` is defined in the exact public path. Two deterministic mechanisms evaluate the same immutable bytes:

```text
regex-symbol-reviewer/v1
python-ast-symbol-reviewer/v1
```

Their reducer is categorical:

```text
both support → SUPPORTED
one disagrees → CONFLICTED
both absent → ABSTAIN
```

This is **not** independent external model/provider evidence. It only proves that the A3 pipeline preserves separate reviewer identities, a separate semantic receipt, and disagreement/abstention states. It receives no arbitrary business-claim closure credit.

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

## Writer lease

```text
docs/architecture/inception-exact-evidence/**
schemas/inception-code-evidence.v1.schema.json
schemas/inception-citation-claim.v1.schema.json
harness/inception_evidence.py
harness/inception_public_canary.py
tests/test_inception_evidence.py
tests/test_inception_public_canary.py
examples/inception-evidence/**
.github/workflows/inception-a3-evidence.yml
```

Existing closure, retriever, lake and semantic modules remain read-only. Private code/source bytes and service-account paths never enter portable fixtures or receipts.

## Evidence ceiling

```text
code/citation schemas             DETERMINISTIC_PASS candidate
physical/lexical validator        DETERMINISTIC_PASS candidate
real public Git blob readback     PUBLIC_VERIFICATION_CANDIDATE
dual-method fixture semantic      PUBLIC_VERIFICATION_CANDIDATE
external independent semantic     NOT_EXERCISED
private evidence                  NOT_EXERCISED
arbitrary business claim closure  ABSENT
Human admission / release         NOT_PERFORMED
```

Machine state: [`preflight.json`](preflight.json).

## Next transition

`RUN_PUBLIC_SOURCE_CAPTURE_WITH_EXTERNAL_INDEPENDENT_SEMANTIC_REVIEW`

The next promotion requires an external independent semantic reviewer or scoped Human review over a public source subject. The deterministic regex/AST fixture may not proxy that lane.
