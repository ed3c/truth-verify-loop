# truth-verify-loop-delivery delivery dashboard

> Snapshot: `2026-08-12T04:04:52Z`。本頁是 GitHub event truth 的時間點快照，
> 不是 registry 的第二份真相，也不是個人生產力排名。

## Truth boundary

```text
┌───────────────┐    ┌──────────────┐    ┌────────────────────────┐
│ GitHub events │ ─→ │ metrics.json │ ─→ │ Markdown decision view │
└───────────────┘    └──────────────┘    └────────────────────────┘
         │
         ├─→ GitHub Project (status projection only)
         └─→ publication attestation ─→ human visibility gate
```

## Current decision

- Repository: `ed3c/truth-verify-loop` (`PRIVATE`)
- Remote tree: `2a22ded2baa274e59d04b2e1f4e8639e3867846b` (45 files, orphan root: `YES`)
- Public ready: `NO`
- Blockers: `export-tree-drift, open-delivery-slices, open-delivery-prs, human-visibility-gate`
- Project: [truth-verify-loop delivery](https://github.com/users/ed3c/projects/5)

## Flow health

| Signal | Value |
|---|---:|
| accepted slices | 1 |
| WIP | 3 |
| blocked | 0 |
| throughput 7d / 28d | 1 / 1 |
| closed_without_merge | 1 |

## Project projection

| Status | Items |
|---|---:|
| In Progress | 1 |
| Todo | 3 |

`closed_without_merge` 是證據缺口，不計入 throughput。p50/p85 只在有 merge event 樣本時顯示。

## Slice evidence

| Issue | State | Started PR | Accepted PR | Lead | Blocked |
|---:|---|---:|---:|---:|---:|
| #1 | CLOSED | — | — | UNKNOWN | 0 |
| #2 | CLOSED | 3 | 3 | 14248 | 0 |
| #6 | OPEN | — | — | UNKNOWN | 0 |
| #7 | OPEN | — | — | UNKNOWN | 0 |
| #8 | OPEN | — | — | UNKNOWN | 0 |
| #9 | OPEN | — | — | UNKNOWN | 0 |
| #10 | OPEN | — | — | UNKNOWN | 0 |
| #11 | OPEN | — | — | UNKNOWN | 0 |
| #12 | OPEN | — | — | UNKNOWN | 0 |
| #13 | OPEN | 15 | — | UNKNOWN | 0 |
| #14 | OPEN | — | — | UNKNOWN | 0 |
| #16 | OPEN | 18 | — | UNKNOWN | 0 |
| #17 | OPEN | 19 | — | UNKNOWN | 0 |

## Human gate

只有 blockers 清空、publication attestation 與遠端 HEAD 對齊後，人類才可執行 PR merge 與 PRIVATE→PUBLIC。

## MVP extraction

| Step | Direct? | Undecided dependency | Permission | Measurable change | Size |
|---|---|---|---|---|---|
| Clear mechanical blockers | direct | none | repository scope | blockers count decreases | small |
| Human visibility decision | direct | owner review | owner only | visibility becomes PUBLIC | human gate |

Rejected now: custom daemon (extra operational surface); personal ranking (Goodhart risk); automatic merge/public toggle (violates human gate).
