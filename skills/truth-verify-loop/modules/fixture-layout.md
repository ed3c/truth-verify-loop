# Blind fixture layout

```text
fixtures/
  dev.list
  holdout.list
  articles/<topic>.md
  mutated/<topic>.md
  mut-config/<topic>.json
  _sealed/<topic>.ledger.jsonl
```

`dev.list` and `holdout.list` must be disjoint. Each topic named in either list must have all four artifacts. The sealed ledger is consumed only by the deterministic scorer after the judge output is final.

Run `python3 scripts/check_fixture_layout.py <fixtures>` to validate the topology.
