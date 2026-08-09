# truth-verify-loop

Measurable claim verification with deterministic scoring and blind fixtures.

This clean-root release contains the deterministic core, an Antigravity-compatible skill, and synthetic dev/holdout fixtures. It intentionally excludes historical runs, cached source pages, and private evaluation corpora.

## Verify

```bash
bash verify.sh
```

The suite checks claim and verdict contracts, controlled mutations, false-supported scoring, fixture blindness, and the public surface.

## Layout

- [skill](skills/truth-verify-loop/SKILL.md)
- [deterministic core](core/tv-score.py)
- [synthetic fixture](examples/synthetic/fixtures)
- [fixture topology checker](scripts/check_fixture_layout.py)

License: MIT. Delivery tracking: [PRD #1](https://github.com/ed3c/truth-verify-loop/issues/1).
