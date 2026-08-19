# Dual-Agent independent evidence verification

Status: deterministic contract candidate for issue #31 under parent #22. This directory extends the existing Truth Verify Loop evidence plane. It does not execute transport, workflow, provider, effect, Human or release operations.

## Authority

```text
execution-plane receipts
        ↓ candidate evidence only
exact producer/run/job/tenant binding
        ↓
DA-TV-C bundle contract
        ↓
independent verifier families
        ↓
existing tvl.evidence-closure.v1 vocabulary
SUPPORTED | REFUTED | CONFLICTED | STALE | UNVERIFIABLE
```

There is no second truth vocabulary. The executing Agent, provider, workflow engine, browser, transport or effect ledger cannot self-promote a closure.

## Contract State Machine

```text
BUNDLE_PROPOSED
→ SCHEMA_VALIDATED
→ RUN_JOB_TENANT_BOUND
→ PRODUCER_SUBJECTS_PINNED
→ RECEIPT_DENOMINATOR_COMPLETE
→ SECRET_AND_REASONING_SCAN_PASS
→ DA-TV-C_CONTRACT_VALID
→ UNVERIFIABLE_PENDING_INDEPENDENT_FAMILIES
```

Root-contract refusal states include mutable producer subject, digest mismatch, dropped/reordered receipt, missing family, cross-run/tenant receipt, deterministic Human/release promotion, secret/private-reasoning material and verifier authority widening.

## Process DAG

```text
#31 DA-TV-C
├─ #32 DA-TV-DLV
├─ #33 DA-TV-EF
├─ #34 DA-TV-ART
└─ #35 DA-TV-USER
       ↓
#36 DA-TV-E
       ↓
#37 DA-TV-D
```

Git ancestry is determined only by actual consumption of unmerged bytes. Sibling verifier families may share #31 as a true parent without depending on each other.

## Data flow

```text
source/problem claim
+ exact local/cloud/runtime/provider subjects
+ complete receipt denominator
+ immutable payload digests
        ↓
contract validation
        ↓
DLV / EF / ART / USER independent findings
        ↓
cross-family convergence
        ↓
existing Evidence Closure
```

Transport ACK, workflow completion, provider observation, effect commit, artifact presence, user-visible result, cleanup and release remain distinct claims.

## Evidence ceiling

DA-TV-C proves only bundle structure, exact-subject binding, receipt-family denominator and sensitive-material exclusion. It cannot prove delivery correctness, effect correctness, artifact bytes, user result, live provider behavior, Human admission or release.

Evidence ceiling: `DETERMINISTIC_DUAL_AGENT_BUNDLE_CONTRACT_ONLY`.
