# KAW domain receipt canary

This directory contains a public, synthetic, domain-owned receipt for the
`kotlin-auto-webview` L5 authority canary.

The receipt is rebuilt from the existing Truth Verify Loop fixture, source policy,
and deterministic Evidence Closure engine:

```text
fixture claim + evidence
→ Claim / Evidence contracts
→ SourcePolicy
→ close_claim
→ bounded domain verdict receipt
→ exact Git commit/tree/blob reference in KAW
```

The receipt excludes raw source text, raw evidence, credentials, internal
reasoning, private locators, user outcomes, and merge/release authority.

Run:

```bash
python3 -m unittest discover -s tests -p 'test_kaw_receipt.py' -v
```

A green result proves only that this exact public synthetic claim was closed by the
domain-owned deterministic engine and exported without widening authority. It does
not establish private-source access, production deployment, every claim, user or
paid outcome, or release readiness.
