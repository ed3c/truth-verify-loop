# Dual-Agent independent evidence verification

Status: **deterministic technical verification merged to `main`** for parent issue #22.

```text
integration commit  123bee539157331cb976c2926f4359352430bfd1
integration tree    507a4bda6e0df459fca1d71c838c9386cf3aff79
merge PR            #28
state               IMPLEMENTATION_MERGED_TO_MAIN
technical closure   UNVERIFIABLE by design
```

This subtree extends the existing Truth Verify Loop evidence plane. It does not execute transport, workflow, provider, effect, Human, release, or production operations, and it does not create a second truth vocabulary.

## Agent read route

```text
harness/dual_agent_evidence/AGENTS.md
→ harness/dual_agent_evidence/README.md
→ harness/dual_agent_evidence/stack-index.json
→ contract.py
→ delivery.py
→ effect.py
→ artifact.py
→ user_result.py
→ matrix-preflight.json
→ convergence.py
→ tests/test_dual_agent_evidence_*.py
```

GitHub `main`, PR history, and exact Actions receipts are canonical. `stack-index.json` is the machine-readable routing and handoff projection.

## Real problem denominator

The PDF/article requirement is a real local→cloud→local loop:

```text
local request committed while offline
→ local restart
→ reconnect and cloud dispatch
→ isolated API-first or bounded browser execution
→ result and artifact receipts
→ local inbox commit
→ second local restart and projection rebuild
→ user-visible result verification
→ optional effect disposition
→ cleanup and Human review
```

This repository has closed the **independent deterministic verification** required to audit such a run. The physical run itself remains owned by `ed3c/bettor-arena#186` and is still `NOT_EXERCISED`.

## Authority map

```text
execution-plane receipts
        ↓ candidate evidence only
DA-TV-C exact evidence-bundle contract
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

The deterministic matrix deliberately ends at `UNVERIFIABLE` even when every technical verifier passes. Technical consistency is not semantic support or refutation. The existing semantic closure plane owns claim direction. Human/release authority remains external. This subtree has `canonical_write=NONE`.

## Directory → State Machine → evidence owner

| Directory or file | State Machine responsibility | Output / evidence ceiling |
|---|---|---|
| `contract.py` | `BUNDLE_PROPOSED → SCHEMA_VALIDATED → SUBJECTS_PINNED → DENOMINATOR_COMPLETE` | bundle contract only |
| `delivery.py` | `OUTBOX/DELIVERY/WORKFLOW/INBOX → ATTEMPTS_RECONCILED → REPLAY_CHECKED` | delivery/workflow evidence only |
| `effect.py` | `INTENT → ATTEMPTS → UNKNOWN/READBACK → COMMIT_OR_REFUSAL` | effect-lineage evidence only |
| `artifact.py` | `MANIFEST → ACTUAL_BYTES → DIGEST_READBACK → BINDING_VERIFIED` | provenance and byte identity only |
| `user_result.py` | `PROVIDER → ROUTE → USER_OBSERVATION → CLEANUP` | user-result/cross-lane evidence only |
| `convergence.py` | `FINDINGS_BOUND → DIGESTS_RECOMPUTED → ALL_FAMILIES_PRESENT → TECHNICAL_MATRIX_PASS` | complete deterministic matrix only |
| `stack-index.json` | exact PR/run/main/handoff projection | trace only; no promotion authority |
| `AGENTS.md` / this README | Agent read route, stop rules, ownership, handoff | documentation only |

## Verification State Machine

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
main@123bee539157331cb976c2926f4359352430bfd1
       ↓
LH-TV-001 / bettor-arena#186 physical canary
       ↓
existing semantic closure / Human / release authorities
```

Issues #31–#37 are deterministic implementation milestones and are eligible to close as completed after this finalization merges. Parent #22 remains open for live/physical evidence.

## Git DAG and merged Stack index

The merge order preserved true byte dependencies:

```text
PR #45 DA-TV-D
  merge commit 5a9223b4525966550921c2727b144f119ff82c9a
        ↓
PR #44 DA-TV-E
  merge commit 280873959db52f241beea53becd4e5d0e339426d
        ↓
PR #39 DA-TV-C
  merge commit a1b09a70bf6c6ec75c7a4a2b5328d67231ac929b
        ↓
PR #29 green baseline convergence
  merge commit 10778f398adf89c748a24ac1da6c32bcaf583f54
        ↓
PR #28 → main
  merge commit 123bee539157331cb976c2926f4359352430bfd1
```

Molecular leaves #40–#43 were exact Git-blob process inputs to PR #44. Their implementation bytes are present on `main`; the leaf PRs can close as completed-via-convergence rather than be merged again.

### Exact deterministic leaf subjects

```text
DA-TV-C    PR #39  944af8fc0230a9aae31ad47d6cb6051e10521bc7
DA-TV-DLV  PR #40  1faf6f818ecb9c70d122461421edf3b720e0f18e
DA-TV-EF   PR #41  84170be2faac66fadadb1e74ef605c7006b7e898
DA-TV-ART  PR #42  080f623cdc7f163ca941ec31838ee6171d8bf999
DA-TV-USER PR #43  781388d84490a902d4cad414673164b40c3927d2
DA-TV-E    PR #44  55d13fe61eec88cd1cd5f04f0670a83ebc366953
DA-TV-D    PR #45  401a105d7768640dbdda8672f358407f7eb648e0
```

The full exact heads, trees, targeted runs, repository runs, retained failures, and main integration subject are stored in `stack-index.json`.

## Data flow

```text
claim/run/job/tenant
+ immutable producer subjects
+ complete attempts/retries/failures
+ payload digests
+ expected producer/runtime/policy bindings
        ↓
DA-TV-C
        ↓
DLV: delivery ACK / workflow replay / inbox restart
EF : effect identity / idempotency / UNKNOWN / readback / compensation
ART: independently supplied source+artifact bytes → SHA-256 readback
USER: provider / API-or-browser route / user observation / cleanup
        ↓
finding digests recomputed by DA-TV-E
        ↓
all four families required and bound to one bundle
        ↓
`UNVERIFIABLE` technical closure
        ↓
existing semantic verification / live evidence / Human authority
```

## Hard laws

- Search, capture, and provenance are not semantic truth.
- Transport ACK is not workflow, task, effect, artifact, user, or release success.
- Provider, API, browser, and user-visible evidence are separate lanes.
- `RESULT_UNKNOWN`, timeout, retry, failed attempt, cancellation, and duplicate delivery remain in the denominator.
- An accepted effect needs exact idempotency lineage and independent readback. Compensation is a linked effect and cannot erase parent history.
- Artifact manifests do not prove bytes. DA-TV-ART hashes independently supplied read-back bytes.
- Screenshot presence is not semantic proof.
- Backend completion is not user-visible success.
- Cleanup is independently verified; UNKNOWN or dirty cleanup prevents technical closure.
- Raw credentials, cookies, browser/session state, personal data, and private reasoning are forbidden from public evidence bundles.
- Every verifier finding digest is recomputed at convergence.
- Technical verifier PASS cannot emit SUPPORTED/REFUTED by itself.
- README, CI, Agent, provider, or fixture cannot infer Human/release state.

## Retained failure history

The Stack index preserves these failures rather than rewriting history:

```text
PR #38 / run 32295680345
PRODUCER_VERSION_VALIDATOR_SCHEMA_MISMATCH

PR #38 / run 32295801844
INHERITED_MAIN_BASELINE_SEMANTIC_FRESHNESS_FAILURE

PR #39 Shadow review
SHADOW_SCHEMA_REVIEW_CLOSURE_AS_OF_WAS_NULL

PR #45 / run 32298782739
AGENT_ROUTE_INCOMPLETE_NORMATIVE_TOKEN
```

PR #38 can close as a superseded historical record after the final integrated state is recorded.

## Local Handoff Execution Queue

Canonical handoff ID: `LH-TV-001`.

```text
parent requirement  truth-verify-loop#22
physical owner      bettor-arena#186
exact public base   truth-verify-loop main@123bee539157331cb976c2926f4359352430bfd1
rollback subject    ce0c90f0c9bc87427d433ce537eea7f3a0fca008
state               HANDOFF_READY / NOT_EXERCISED
```

Required trusted/local execution inputs:

- a safe public/test target with reviewed terms;
- actual local outbox, restart, reconnect, cloud dispatch, and inbox receipts;
- exact runtime, workflow, identity, route, sandbox, target, and policy subjects;
- full duplicate/retry/timeout/cancel/failure denominator;
- actual source and artifact bytes for verifier-side readback;
- provider/route/user observations kept in distinct lanes;
- optional effect intent, attempt, readback, duplicate disposition, and compensation lineage;
- cleanup/residue inventory;
- authorized Human decision where required.

Idempotency: one `job_id`, one logical request identity, canonical effect identities, and no accepted duplicate observable effect.

Timeout: every transport, workflow, provider, readback, effect, and cleanup attempt must be bounded and preserved in the evidence bundle.

Receipt: emit a `tvl.dual-agent-evidence-bundle.v1` bundle and run this subtree's contract, DLV, EF, ART, USER, matrix, and existing semantic closure checks.

Rollback: stop the canary, revoke temporary provider/session/identity material, remove disposable resources, preserve immutable receipts, and return to the exact public base without deleting failed-attempt evidence.

Verifier: `truth-verify-loop` verifies receipts; it does not execute or approve the physical run.

## Current closure matrix

| Plane | State |
|---|---|
| Bundle/receipt contract | `MERGED / CLOSED_DETERMINISTIC` |
| Delivery/workflow verifier | `MERGED / CLOSED_DETERMINISTIC` |
| Effect/idempotency verifier | `MERGED / CLOSED_DETERMINISTIC` |
| Source/artifact byte readback | `MERGED / CLOSED_DETERMINISTIC` |
| User-result/cross-lane verifier | `MERGED / CLOSED_DETERMINISTIC` |
| Complete technical matrix | `MERGED / CLOSED_DETERMINISTIC` |
| Documentation/AGENTS/Stack trace | `MERGED / CLOSED_DETERMINISTIC_TRACE` |
| Semantic claim direction | `NOT_EXERCISED_BY_DA_TV_MATRIX` |
| Physical local→cloud→local run | `NOT_EXERCISED` |
| Live provider/network/private source | `NOT_EXERCISED` |
| Human admission | `NOT_EXERCISED` |
| Release | `NOT_PERFORMED` |

Highest evidence ceiling:

```text
COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY
```

The next legal transition is `LH-TV-001`; no further deterministic verifier family should be added merely to avoid the live/physical boundary.