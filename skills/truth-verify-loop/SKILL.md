---
name: truth-verify-loop
description: |
  Use when an article, concept, or consequential claim set needs a measurable verification loop rather than a one-off fact check. Extracts typed claims, validates verbatim anchors, runs independent verifier families, aggregates disagreements, applies a fresh semantic judge only where scripts cannot decide, scores against sealed synthetic truth, and records cost and failure modes.
---

# Truth verification loop

The loop separates three powers:

1. workers produce claim-level evidence and provisional labels;
2. an independent judge resolves only bounded semantic disagreements;
3. deterministic scripts validate shape, quote fidelity, blindness, and final scores.

A worker label is data, not the final verdict.

## Pipeline

```text
article -> typed claims -> deterministic preverify -> verifier batches
       -> cross-family aggregation -> bounded fresh judge
       -> deterministic score against sealed truth -> ledger
```

## Invariants

- A run pin changes one variable. Do not change contracts or tools mid-run.
- Authors, workers, and judges cannot read `fixtures/_sealed`.
- False `SUPPORTED` is a hard failure.
- Abstention and cross-family agreement are sampled because consensus can be jointly wrong.
- Failed, discarded, and recovery attempts count toward cost.
- Historical source documents and run caches are not reusable fixtures.
- A fresh topic regenerates articles, mutations, configuration, and sealed truth locally.

## Deterministic core

- `core/tv-preverify.sh`: JSONL shape, verbatim quote, evidence quote, and type-contract gate;
- `core/tv-mutate.py`: controlled mutation set with injection canary;
- `core/tv-aggregate.py`: claim-level aggregation and disagreement queue;
- `core/tv-score.py`: pure scoring against a sealed ledger;
- `core/tv-split.py`: typed batching.

Run `bash verify.sh` before using the loop. The suite includes planted defects, not only happy paths.

## Instantiation

Create a topic directory matching [the fixture layout](modules/fixture-layout.md). Keep sealed truth in a path inaccessible to authors and judges. Write thresholds and stop conditions before dispatching workers. Store provider/model selection outside the standing contracts so a new host can retarget the loop without rewriting its truth rules.
