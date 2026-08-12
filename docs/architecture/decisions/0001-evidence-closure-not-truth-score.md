# ADR 0001: Use Evidence Closure, not one truth score

Status: accepted

Date: 2026-08-09

## Context

A single probability combines unlike questions:

- Was the quote actually present?
- Was the source captured or only summarized by a model?
- Is the source authoritative for this product and version?
- Is the evidence fresh enough?
- Do current sources conflict?
- Did the harness reproduce the run?

A high scalar can hide a hard failure in any one of these dimensions. It also makes revisions difficult because users cannot see which assumption changed.

## Decision

The system emits one categorical state plus independent deterministic gates:

- `SUPPORTED`
- `REFUTED`
- `CONFLICTED`
- `STALE`
- `UNVERIFIABLE`

A claim is closed only when the state is `SUPPORTED` or `REFUTED` and every required gate passes. Authority, freshness, corroboration, citation integrity, capture scope, and conflict remain separate fields.

Model votes and search rankings may be recorded as observations. They do not override a failed gate.

Every closure includes conditions that create a new revision or invalidate it.

## Consequences

Benefits:

- fail-closed behavior is visible;
- source conflict cannot be averaged away;
- risk policy can tighten without changing historical records;
- hot memory can expire a closure by time;
- evaluation can measure false support, stale acceptance, conflict recall, citation integrity, and cost separately.

Costs:

- applications must handle unknown and conflicted states;
- there is no convenient universal ranking number;
- policy owners must define source classes and freshness SLAs.

## Rejected alternatives

### Model confidence

Rejected because it is not a source receipt and is not calibrated across model, prompt, provider, or date changes.

### Majority vote

Rejected because correlated models can agree on the same stale or fabricated premise.

### Search rank as authority

Rejected because retrieval rank optimizes relevance, not domain authority, quotation fidelity, or freshness.
