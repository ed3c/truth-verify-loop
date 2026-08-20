# Dual-Agent evidence verification agent instructions

These instructions scope `harness/dual_agent_evidence/**`. Repository-root `AGENTS.md` remains authoritative for global Truth Verify Loop architecture, confidentiality, exact-subject and evidence rules.

## Read order

Before modifying this subtree read, in order:

1. `AGENTS.md` (this file)
2. `README.md`
3. `stack-index.json`
4. `contract.py`
5. the verifier family you own (`delivery.py`, `effect.py`, `artifact.py`, or `user_result.py`)
6. `matrix-preflight.json`
7. `convergence.py`
8. matching `tests/test_dual_agent_evidence_*.py`

Re-read GitHub PR/Actions state before using any head/tree/run from the index. The index is a trace snapshot, not a substitute for current GitHub state.

## Authority map

```text
Truth Verify Loop existing closure plane  closure vocabulary / semantic truth
DA-TV-C                                 evidence bundle contract only
DA-TV-DLV                               delivery/workflow/inbox evidence gate
DA-TV-EF                                effect/idempotency/readback evidence gate
DA-TV-ART                               source/artifact byte-readback evidence gate
DA-TV-USER                              user-result/cross-lane/cleanup evidence gate
DA-TV-E                                 technical finding convergence only
executing Agent/provider/workflow       candidate evidence only
Human/release systems                   external authority
```

No file in this subtree may append task state, execute a provider, acknowledge transport, commit an effect, approve a Human gate, or publish/release. `canonical_write=NONE` at convergence.

## Closure vocabulary

Do not create synonyms or a second closure enum. Only the existing states are valid:

```text
SUPPORTED
REFUTED
CONFLICTED
STALE
UNVERIFIABLE
```

The deterministic DA-TV matrix **must** end `UNVERIFIABLE`. A fully green technical matrix means the evidence bundle is technically consistent under the exercised controls; it does not decide semantic claim direction.

Technical verifier PASS cannot emit SUPPORTED/REFUTED by itself.

## State machine

```text
BUNDLE_PROPOSED
→ SCHEMA_VALIDATED
→ RUN_JOB_TENANT_BOUND
→ PRODUCER_SUBJECTS_PINNED
→ RECEIPT_DENOMINATOR_COMPLETE
→ SENSITIVE_MATERIAL_EXCLUDED
→ CROSS_FAMILY_BINDINGS_CHECKED
→ DLV_CHECKED
→ EF_CHECKED
→ ART_BYTES_READ_BACK
→ USER_AND_CLEANUP_CHECKED
→ FINDING_DIGESTS_RECOMPUTED
→ TECHNICAL_MATRIX_PASS
→ UNVERIFIABLE_PENDING_SEMANTIC_OR_LIVE_EVIDENCE
```

Fail closed on any missing family, missing attempt, digest disagreement, stale producer/runtime/policy subject, lane substitution, unresolved effect, byte-readback mismatch, dirty/UNKNOWN cleanup, finding tamper or authority widening.

## Path leases

### DA-TV-C / issue #31

May write only bundle/schema/root-contract/test/workflow bytes necessary for the contract root.

### DA-TV-DLV / issue #32

Owns only delivery/workflow/inbox verifier implementation/test/workflow. It does not own effect/artifact/user or shared docs.

### DA-TV-EF / issue #33

Owns only effect/idempotency/readback/compensation verifier implementation/test/workflow.

### DA-TV-ART / issue #34

Owns only source/artifact byte-readback verifier implementation/test/workflow.

### DA-TV-USER / issue #35

Owns only provider-route-user-cleanup verifier implementation/test/workflow.

### DA-TV-E / issue #36

Owns convergence implementation, exact sibling materialization preflight, matrix test and matrix workflow. It must not rewrite sibling semantics.

### DA-TV-D / issue #37

Sole shared docs/trace owner for this subtree: `README.md`, this `AGENTS.md`, `stack-index.json`, docs verifier/workflow. Documentation never raises the evidence ceiling.

## Git DAG law

- A true child consumes named unmerged parent bytes.
- Path-disjoint verifier families are siblings from the same contract root.
- #36 uses exact Git blob materialization as process inputs; it does not invent multi-parent ancestry.
- Restacking after parent movement must preserve child bytes and historical PASS/RED evidence. Do not force-push away audit history when a merge-restack can retain it.
- Git/PR mergeability is not implementation, semantic, live, Human, or release evidence.

## Evidence non-substitution laws

```text
transport ACK             != task/user success
workflow completion       != user success
provider observation      != effect commit
API receipt               != browser receipt
browser receipt           != API receipt
provider result           != user-visible result
artifact manifest/hash    != read-back bytes
screenshot presence       != semantic support
technical matrix PASS     != SUPPORTED/REFUTED
Human/release fixture     != Human/release evidence
```

Retries, duplicates, failed/timeouts/cancelled attempts and `RESULT_UNKNOWN` stay in the denominator. Do not optimize them away as noise.

## Sensitive-data boundary

Never persist raw credentials, token values, cookies, browser profiles/storage state, session bytes, private reasoning or chain-of-thought in evidence bundles. Store only allowed public/evidence-safe references and digests. Do not invent or materialize private-source content in public tests.

## Source and artifact rule

DA-TV-ART must hash independently supplied captured/read-back bytes. A producer-declared digest or `bytes_present=true` is not sufficient. Temporary paths are not durable evidence. Capture proves provenance/bytes; semantic verification remains separate.

## Shadow stop conditions

Stop and hand off rather than self-promote when any next step requires:

- private-source access not already authorized in the current execution plane;
- real provider/network/browser session execution;
- physical local→cloud→local canary execution;
- production credential/session access;
- Human approval/admission;
- merge/release/rollback/promotion.

Mark those states `NOT_EXERCISED`, `NOT_PERFORMED`, `UNVERIFIABLE`, or the repository's existing appropriate state. Never convert absence of authority into PASS.

## Current deterministic frontier

Read `stack-index.json` and current GitHub state. At the time this docs convergence was prepared:

```text
PR #39 DA-TV-C      PASS deterministic
PR #40 DA-TV-DLV    PASS deterministic
PR #41 DA-TV-EF     PASS deterministic
PR #42 DA-TV-ART    PASS deterministic
PR #43 DA-TV-USER   PASS deterministic
PR #44 DA-TV-E      PASS complete technical matrix
issue #37 DA-TV-D   docs/trace convergence
```

The next non-document transition is live/private semantic and physical-run evidence through the existing Truth Verify Loop semantic/closure architecture. No new verifier family may bypass that route.

## Zero-context continuation

A new Agent continuing this work should:

1. read this file and `README.md`;
2. re-read PR #39–#44 heads and exact Actions conclusions;
3. verify `stack-index.json` exact subjects and retained failure history;
4. run repository `verify.sh` plus the Dual-Agent matrix/docs workflows on the current candidate;
5. keep technical closure `UNVERIFIABLE` unless the **existing** semantic closure plane independently establishes a different state with admissible evidence;
6. leave Human/release states external unless an authorized Human/release transition is explicitly performed.
