# Dual-Agent independent evidence verification

Status: complete **deterministic technical verification** candidate for parent issue #22. This directory extends the existing Truth Verify Loop evidence plane; it does not execute transport, workflow, provider, effect, Human or release operations and it does not create a second truth vocabulary.

## Agent read route

```text
AGENTS.md
→ README.md
→ stack-index.json
→ contract.py
→ delivery.py
→ effect.py
→ artifact.py
→ user_result.py
→ matrix-preflight.json
→ convergence.py
```

GitHub PR/Actions readback is authoritative for current PR/check state. `stack-index.json` is the machine routing snapshot for this deterministic subtree and intentionally cannot self-promote its own docs candidate.

## Authority

```text
execution-plane receipts
        ↓ candidate evidence only
DA-TV-C exact bundle contract
        ↓
┌─────────────────────────────────────────────┐
│ DA-TV-DLV  delivery / workflow / inbox      │
│ DA-TV-EF   effect / idempotency / readback  │
│ DA-TV-ART  source / actual artifact bytes   │
│ DA-TV-USER user result / cross-lane/cleanup │
└─────────────────────────────────────────────┘
        ↓ independent findings
DA-TV-E cross-family binding + digest convergence
        ↓
existing `tvl.evidence-closure.v1`
SUPPORTED | REFUTED | CONFLICTED | STALE | UNVERIFIABLE
```

The deterministic matrix deliberately ends at **`UNVERIFIABLE`** even when every technical verifier passes. Technical consistency is not semantic claim-direction proof. Existing Truth Verify Loop semantic verification owns semantic support/refutation; Human/release authority remains external.

## State Machine

```text
BUNDLE_PROPOSED
→ SCHEMA_VALIDATED
→ RUN_JOB_TENANT_BOUND
→ PRODUCER_SUBJECTS_PINNED
→ RECEIPT_DENOMINATOR_COMPLETE
→ SECRET_AND_REASONING_SCAN_PASS
→ CROSS_FAMILY_BINDINGS_CHECKED
→ DELIVERY_WORKFLOW_RECONCILED
→ EFFECT_LINEAGE_RECONCILED
→ SOURCE_ARTIFACT_BYTES_READ_BACK
→ USER_RESULT_AND_CLEANUP_RECONCILED
→ VERIFIER_FINDING_DIGESTS_RECOMPUTED
→ TECHNICAL_MATRIX_PASS
→ UNVERIFIABLE_PENDING_SEMANTIC_OR_LIVE_EVIDENCE
```

No transition in this subtree reaches task success, external effect commit, Human approval, release, or production promotion.

## Exact deterministic subjects

```text
baseline convergence PR #29
head c01254547672a9ad03345c9013b20d3d1049e274
tree 577213165a091aee389e9c7028570eb8cf6da1c7
verify run 32252254820 PASS

DA-TV-C issue #31 / PR #39
head 944af8fc0230a9aae31ad47d6cb6051e10521bc7
tree 1bb3589e20c157136a2597a51db15599226f4c6a
targeted run 32297448276 PASS
repository verify 32297448445 PASS

DA-TV-DLV issue #32 / PR #40
head 1faf6f818ecb9c70d122461421edf3b720e0f18e
tree 120f9e496923c428cb8c3ccd53009b2e0c92175a
targeted run 32297590276 PASS
repository verify 32297590291 PASS

DA-TV-EF issue #33 / PR #41
head 84170be2faac66fadadb1e74ef605c7006b7e898
tree 01c380ff49a3274cecda8c233db676f45b73c777
targeted run 32297636307 PASS
repository verify 32297636445 PASS

DA-TV-ART issue #34 / PR #42
head 080f623cdc7f163ca941ec31838ee6171d8bf999
tree cd70a2875dc022a3af5d07512cf15b3345444b11
targeted run 32297675577 PASS
repository verify 32297675560 PASS

DA-TV-USER issue #35 / PR #43
head 781388d84490a902d4cad414673164b40c3927d2
tree 6ff6a9df8d69a5dd35c42eddbb053bbc2be5be4a
targeted run 32297728757 PASS
repository verify 32297728719 PASS

DA-TV-E issue #36 / PR #44
head 55d13fe61eec88cd1cd5f04f0670a83ebc366953
tree e8f5194b91814d26e3c87cc194cf8789a87db4b5
matrix run 32298186985 PASS (Python 3.11 + 3.14)
repository verify 32298186805 PASS
```

## Retained failure history

Historical PR #38 remains open/draft and superseded. It records, rather than erases:

```text
head da09b28ba76a292fdecb170dd24752fc5c1f55e8
run  32295680345 RED
finding PRODUCER_VERSION_VALIDATOR_SCHEMA_MISMATCH

head 125085edee395d193c15a315f289a214ee507ed8
run  32295801844 RED
finding INHERITED_MAIN_BASELINE_SEMANTIC_FRESHNESS_FAILURE
```

Shadow review also caught a root closure-shape defect (`as_of=null`) before convergence. PR #39 was repaired to derive a schema-compatible `as_of` from verified receipt observation timestamps, then all child branches were merge-restacked and rerun.

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
       ↓
live/private semantic + physical local→cloud→local evidence
```

## Git DAG

```text
PR #29 green baseline
└─ PR #39 DA-TV-C
   ├─ PR #40 DA-TV-DLV
   ├─ PR #41 DA-TV-EF
   ├─ PR #42 DA-TV-ART
   └─ PR #43 DA-TV-USER
        ↓ exact Git-blob process inputs
      PR #44 DA-TV-E
         └─ DA-TV-D docs child
```

PR #44 has PR #39 as its actual Git base. It materializes only #40–#43 module/test bytes by exact Git blob SHA; process input does not imply fake multi-parent ancestry.

## Data flow

```text
claim/run/job/tenant
+ immutable producer subjects
+ complete attempts/retries/failures
+ payload digests
+ BINDING expected producer/runtime/policy subjects
        ↓
DA-TV-C
        ↓
DLV: delivery ACK / workflow replay / inbox restart
EF : effect identity / idempotency / unknown / readback / compensation
ART: independently supplied source+artifact bytes → SHA-256 readback
USER: provider / API-BROWSER route / user observation / cleanup
        ↓
finding digests recomputed by convergence
        ↓
all four required and same bundle subject
        ↓
`UNVERIFIABLE` technical closure
        ↓
existing semantic verification / live evidence / Human authority
```

## Hard laws

- Search/capture/provenance is not semantic truth.
- Transport ACK is not workflow/task/effect/artifact/user/release success.
- Provider output, API evidence, browser evidence and user-visible evidence are separate lanes.
- `RESULT_UNKNOWN`, timeouts, retries, failed attempts and duplicate deliveries stay in the denominator.
- An accepted effect needs exact idempotency lineage and readback; compensation is a linked effect and cannot erase parent history.
- Artifact manifests do not prove bytes. DA-TV-ART hashes independently supplied read-back bytes itself.
- Screenshot presence is not semantic proof.
- Backend completion is not user-visible success.
- Cleanup is independently verified and zero-residue; UNKNOWN/dirty cleanup prevents technical closure.
- Sensitive credential/session material and private reasoning are forbidden from evidence bundles.
- Every verifier finding digest is recomputed at convergence.
- Technical verifier PASS cannot emit SUPPORTED/REFUTED by itself.
- This directory has `canonical_write=NONE`; task/workflow/effect/Human/release writers remain external.

## Evidence ceiling and live handoff

Current highest evidence ceiling:

```text
COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY
```

Still outside this closure:

```text
real local→cloud→local physical run    NOT_EXERCISED here
live provider/network receipts          NOT_EXERCISED here
private-source evidence                 NOT_EXERCISED here
semantic claim-direction adjudication   NOT_EXERCISED by DA-TV matrix
live user result                        NOT_EXERCISED here
Human admission                         NOT_EXERCISED
release                                 NOT_PERFORMED
```

Next execution may consume exact receipts from the physical canary and private/live sources, but must pass through the existing semantic and closure planes. No deterministic fixture, CI PASS, README, Agent, provider, or verifier family may substitute for that authority.
