# Dual-Agent evidence verification agent instructions

These instructions scope `harness/dual_agent_evidence/**`. Repository-root `AGENTS.md` remains authoritative for global Truth Verify Loop architecture, confidentiality, exact-subject, runtime-classification, and evidence rules.

## Integrated subject

```text
repository          ed3c/truth-verify-loop
implementation main 123bee539157331cb976c2926f4359352430bfd1
implementation tree 507a4bda6e0df459fca1d71c838c9386cf3aff79
merge PR            #28
state               IMPLEMENTATION_MERGED_TO_MAIN
highest ceiling     COMPLETE_DETERMINISTIC_DUAL_AGENT_TRUTH_MATRIX_ONLY
```

This is a deterministic verification capability, not live semantic truth, task success, provider execution, Human admission, or release.

## Read order

Before modifying or consuming this subtree, read in order:

1. repository-root `AGENTS.md`;
2. this `AGENTS.md`;
3. `README.md`;
4. `stack-index.json`;
5. `contract.py`;
6. the verifier family being changed: `delivery.py`, `effect.py`, `artifact.py`, or `user_result.py`;
7. `matrix-preflight.json`;
8. `convergence.py`;
9. matching `tests/test_dual_agent_evidence_*.py`;
10. current GitHub issue, PR, and Actions state.

GitHub `main` and exact Actions receipts are canonical. The Stack index is a routing projection and cannot substitute for current readback.

## Authority map

```text
existing Truth Verify Loop closure plane  closure vocabulary and semantic claim direction
DA-TV-C                                  evidence-bundle contract only
DA-TV-DLV                                delivery/workflow/inbox verification only
DA-TV-EF                                 effect/idempotency/readback verification only
DA-TV-ART                                source/artifact byte-readback verification only
DA-TV-USER                               user-result/cross-lane/cleanup verification only
DA-TV-E                                  technical finding convergence only
executing Agent/provider/workflow        candidate evidence only
bettor-arena#186                         physical local→cloud→local execution owner
Human/release systems                    external authority
```

No file in this subtree may append canonical task state, acknowledge transport, execute a workflow/provider, commit an external effect, approve a Human gate, alter release state, or promote production. `canonical_write=NONE`.

## Closure vocabulary

Do not add synonyms or a second closure enum. Only these existing states are valid:

```text
SUPPORTED
REFUTED
CONFLICTED
STALE
UNVERIFIABLE
```

The deterministic DA-TV matrix must end `UNVERIFIABLE`. A green technical matrix means the bundle is internally consistent under exercised controls. It does not establish semantic support or refutation.

Technical verifier PASS cannot emit SUPPORTED/REFUTED by itself.

## State Machine

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

Fail closed on a missing family or attempt, digest disagreement, stale producer/runtime/policy binding, lane substitution, unresolved effect, missing actual bytes, dirty/UNKNOWN cleanup, finding tamper, or authority widening.

## Directory and writer leases

| Owner | Writable scope | Prohibited scope |
|---|---|---|
| DA-TV-C / #31 | bundle schema, root contract, root tests/workflow | sibling semantics, shared release state |
| DA-TV-DLV / #32 | delivery/workflow/inbox verifier, tests/workflow | effect/artifact/user/shared docs |
| DA-TV-EF / #33 | effect/idempotency/readback verifier, tests/workflow | provider execution, shared docs |
| DA-TV-ART / #34 | source/artifact actual-byte verifier, tests/workflow | semantic claim direction, shared docs |
| DA-TV-USER / #35 | provider-route-user-cleanup verifier, tests/workflow | effect writer, Human/release state |
| DA-TV-E / #36 | convergence, exact sibling preflight, matrix tests/workflow | rewriting sibling semantics |
| DA-TV-D / #37 | README, this file, Stack index, docs verifier/workflow | raising evidence ceiling |
| LH-TV-001 | no public implementation writer; trusted execution receipts only | changing deterministic verifier laws during the canary |

Issues #31–#37 are completed deterministic milestones once the post-merge trace finalization is merged. Parent #22 stays open for the live/physical objective.

## Git DAG law

- A true child consumes named unmerged parent bytes.
- Path-disjoint verifier families are siblings from one contract root.
- #36 used exact Git blob materialization as process inputs; it did not invent multi-parent ancestry.
- The merged chain is `#45 → #44 → #39 → #29 → #28 → main@123bee539157331cb976c2926f4359352430bfd1`.
- PRs #40–#43 are atomic implementation records whose exact bytes were admitted by #44 and are present on `main`; do not merge them a second time.
- Git mergeability, CI status, or docs presence is not semantic, live, Human, or release evidence.
- Preserve failed-head history. Never force-push away the denominator merely to simplify a graph.

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

Retries, duplicates, failures, timeouts, cancellations, and `RESULT_UNKNOWN` remain in the denominator.

## Sensitive-data boundary

Never persist raw credentials, token values, cookies, browser profiles/storage state, session bytes, personal data, private reasoning, or chain-of-thought in evidence bundles. Store only allowed evidence-safe references and digests. Do not materialize private-source content into public tests.

## Source and artifact rule

DA-TV-ART must hash independently supplied captured/read-back bytes. A producer digest, manifest entry, screenshot, or `bytes_present=true` flag is not sufficient. Temporary paths are not durable evidence. Capture proves provenance and byte identity only; semantic verification remains separate.

## Current merged Stack

```text
DA-TV-C    #31 / PR #39  merged via a1b09a70bf6c6ec75c7a4a2b5328d67231ac929b
DA-TV-DLV  #32 / PR #40  admitted by convergence #44
DA-TV-EF   #33 / PR #41  admitted by convergence #44
DA-TV-ART  #34 / PR #42  admitted by convergence #44
DA-TV-USER #35 / PR #43  admitted by convergence #44
DA-TV-E    #36 / PR #44  merged via 280873959db52f241beea53becd4e5d0e339426d
DA-TV-D    #37 / PR #45  merged via 5a9223b4525966550921c2727b144f119ff82c9a
baseline   #29           merged via 10778f398adf89c748a24ac1da6c32bcaf583f54
main       #28           123bee539157331cb976c2926f4359352430bfd1
```

Read `stack-index.json` for exact leaf heads, trees, targeted runs, repository runs, retained failures, and the Local Handoff packet.

## Local Handoff Execution Queue

Canonical item: `LH-TV-001`.

```text
parent requirement  truth-verify-loop#22
physical owner      bettor-arena#186
exact base          truth-verify-loop main@123bee539157331cb976c2926f4359352430bfd1
state               HANDOFF_READY / NOT_EXERCISED
idempotency         one job identity + canonical effect identities
verifier            this repository after actual receipts exist
```

The trusted/local executor must provide actual local outbox/restart/reconnect/inbox receipts, cloud workflow/provider/sandbox observations, target and policy bindings, actual source/artifact bytes, user-visible readback, optional effect disposition, cleanup inventory, and Human decision where required.

Every network, workflow, provider, effect, readback, and cleanup attempt must have a bounded timeout and remain in the evidence denominator. On rollback, revoke temporary identities/sessions, remove disposable resources, preserve receipts, and return to the exact public base without deleting failure evidence.

## Shadow stop conditions

Stop and update the Local Handoff issue instead of self-promoting when a next step needs:

- real provider, network, browser session, or physical local→cloud→local execution;
- private-source access;
- production credential/session resolution;
- target/terms or billing approval;
- external effect authorization;
- Human admission;
- release, rollback, or production promotion.

Mark such states `NOT_EXERCISED`, `NOT_PERFORMED`, `UNVERIFIABLE`, or the repository's existing fail-closed equivalent.

## Zero-context continuation

A new Agent should:

1. read this file, `README.md`, and `stack-index.json`;
2. verify `main@123bee539157331cb976c2926f4359352430bfd1` is an ancestor of the current public `main`;
3. re-read parent issue #22 and physical owner `ed3c/bettor-arena#186`;
4. verify exact receipts before running contract, DLV, EF, ART, USER, matrix, and semantic closure checks;
5. keep technical closure `UNVERIFIABLE` unless the existing semantic plane independently closes the exact claim;
6. leave task/effect/Human/release authority external;
7. update `LH-TV-001` with exact base, bounded actions, receipts, rollback, remaining `NOT_EXERCISED` lanes, and verifier result.