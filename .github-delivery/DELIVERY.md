# Delivery evidence boundary

This directory binds the repository's materialized delivery surface to GitHub tracking records.

- `registry.json` names each locally checkable delivery line and pins the immutable GitHub repository node ID.
- `receipts/` records the GitHub issue, pull request, Project, source commit, and synchronization time observed by a live sync.
- `publications/` records the remote default-branch state and any honest publication blockers.
- `metrics/` and `dashboard.md` are derived projections; GitHub issue and pull-request events remain the event source of truth.

Run the local gate from any working directory:

```bash
python3 ~/.claude/skills/github-delivery-loop/scripts/github_delivery.py check \
  --registry /absolute/path/to/truth-verify-loop/.github-delivery/registry.json
```

The `check` command is a zero-network replay. It proves that registered artifacts and well-formed, identity-matched receipts are present locally. It does not prove that GitHub has not changed since `synced_at`.

A live `sync --github` is different evidence: it queries the current GitHub repository, issue, pull-request, and Project state, then atomically refreshes the receipt, publication attestation, metrics, and dashboard. Publication blockers such as `export-tree-drift`, open slices, open pull requests, or private visibility are evidence, not check failures, and must not be erased or retroactively rewritten.
