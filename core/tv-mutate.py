#!/usr/bin/env python3
"""tv-mutate.py — truth-verify fixtures 的機械 + injection 播錯生成器。

讀原文 + 機械播錯配置 → 產 mutated 文章 + sealed ledger（ground truth）。
密度分檔：--dens lo 施加 dens=="lo" 的 mutation；--dens hi 施加 dens in {"lo","hi"}
（hi 是 lo 的超集）。所有 mutation 皆逐字 find->replace；每個 find 在原文須恰好出現一次，
否則 fail loud（絕不 silent 部分播錯）。

Contract SSOT：docs/plans/2026-07-05-truth-verify-loop/CONTEXT.md §4（sealed ledger schema）；
00-intent-and-knowhow.md §4 Q3 / §5 ①⑦。

用法：
  tv-mutate.py --article A.md --config C.json --fam cl|gm --dens lo|hi \
      --out-md OUT.md --out-ledger OUT.ledger.jsonl
"""
import argparse
import json
import re
import sys

SENT_RE = re.compile(r"[.!?。！？]")


class MutateError(Exception):
    """任一硬失敗（find 不唯一 / 缺 injection / canary 缺失 / find 重疊）。"""


def _select(mutations, dens):
    if dens == "lo":
        return [m for m in mutations if m.get("dens") == "lo"]
    if dens == "hi":
        return [m for m in mutations if m.get("dens") in ("lo", "hi")]
    raise MutateError(f"unknown dens: {dens!r}")


def _find_span(text, needle):
    i = text.find(needle)
    if i < 0:
        return None
    if text.find(needle, i + 1) >= 0:
        return "AMBIGUOUS"
    return (i, i + len(needle))


def mutate(article_text, config, fam, dens):
    """回傳 (mutated_text, ledger_entries)。任一硬失敗 raise MutateError。"""
    if fam not in ("cl", "gm"):
        raise MutateError(f"fam must be cl|gm: {fam!r}")
    selected = _select(config.get("mutations", []), dens)
    if not selected:
        raise MutateError(f"no mutations selected for dens={dens}")

    # 每個 dens 檔必含 >=1 injection 探針（Task 4 / 閘 G5）
    injections = [m for m in selected if m.get("kind") == "injection"]
    if not injections:
        raise MutateError(
            f"dens={dens} set has no injection probe (need >=1; tag it dens=lo)")
    for m in injections:
        if "c-inj-" not in m.get("replace", ""):
            raise MutateError(
                f"injection {m.get('id')} payload missing canary convention 'c-inj-'")

    # 於「原文」解析所有 find 的 span，確保唯一且不重疊，再一次 splice（避免相互干擾）
    spans = []
    for m in selected:
        for req in ("id", "find", "replace", "true_type", "kind"):
            if req not in m:
                raise MutateError(f"mutation missing field {req!r}: {m}")
        span = _find_span(article_text, m["find"])
        if span is None:
            raise MutateError(f"{m['id']}: find not present: {m['find']!r}")
        if span == "AMBIGUOUS":
            raise MutateError(f"{m['id']}: find occurs >1 time (ambiguous): {m['find']!r}")
        spans.append((span[0], span[1], m))
    spans.sort(key=lambda t: t[0])
    for a in range(1, len(spans)):
        if spans[a][0] < spans[a - 1][1]:
            raise MutateError(
                f"overlapping finds: {spans[a - 1][2]['id']} & {spans[a][2]['id']}")

    out = []
    ledger = []
    cur = 0
    for start, end, m in spans:
        out.append(article_text[cur:start])
        out.append(m["replace"])
        cur = end
        ledger.append({
            "mutation_id": m["id"],
            "claim_hint": m.get("claim_hint", m["replace"]),
            "true_type": m["true_type"],
            "expected_verdict": m.get("expected_verdict", "REFUTED"),
            "mutation_kind": m["kind"],
            "author_family": "script",
            "original": m["find"],
            "mutated": m["replace"],
        })
    out.append(article_text[cur:])
    return "".join(out), ledger


def density(text, n_mut):
    sents = [s for s in SENT_RE.split(text) if s.strip()]
    n = max(1, len(sents))
    return n_mut / n, len(sents)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--fam", required=True, choices=["cl", "gm"])
    ap.add_argument("--dens", required=True, choices=["lo", "hi"])
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-ledger", required=True)
    args = ap.parse_args(argv)

    with open(args.article, encoding="utf-8") as f:
        article = f.read()
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    try:
        mutated, ledger = mutate(article, config, args.fam, args.dens)
    except MutateError as e:
        print(f"FATAL tv-mutate: {e}", file=sys.stderr)
        return 2

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(mutated)
    with open(args.out_ledger, "w", encoding="utf-8") as f:
        for e in ledger:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    frac, n_sents = density(mutated, len(ledger))
    band = (0.02, 0.05) if args.dens == "lo" else (0.15, 0.20)
    warn = "" if band[0] <= frac <= band[1] else "  [WARN density out of band]"
    print(f"MUTATE fam={args.fam} dens={args.dens} muts={len(ledger)} sents={n_sents} "
          f"density={frac:.1%} band={band[0]:.0%}-{band[1]:.0%}{warn} "
          f"md={args.out_md} ledger={args.out_ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
