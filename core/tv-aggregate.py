#!/usr/bin/env python3
"""tv-aggregate.py — 合併 worker shards → provisional verdicts.jsonl + split-queue。

擁有 AGG_RULE {1, 2+judge-on-split, 3-majority} 與 TYPE_C 跨家族必開(00-intent §4 Q1;CONTEXT §4)。
用法:  tv-aggregate.py <run-dir>
讀:
  <run-dir>/config.json     (N_VERIFIERS / AGG_RULE / cross_family_fallback)
  <run-dir>/claims.jsonl    (claim_id -> type)
  <run-dir>/cl-*.jsonl, gm-*.jsonl   (worker 原始 shards)
寫:
  <run-dir>/verdicts.jsonl        (已解決,scorer 唯一輸入;verifier 記聚合來源)
  <run-dir>/split-queue.jsonl     (待判官)
  <run-dir>/agg-provenance.jsonl  (member 審計 sidecar)
  追加 <run-dir>/dispatch-fail.jsonl (TYPE_C 缺家族 / 無 verdict / 未知 AGG_RULE)
永不讀 sealed ledger(鐵律 4)。退出碼:有 dispatch-fail → 1,否則 0。
"""
import json, sys, glob, os
from collections import Counter

def load_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out

def dump_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def append_jsonl(path, rows):
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def tag(v, verifier_tag):
    out = dict(v)
    out["verifier"] = verifier_tag
    return out

def apply_agg(cid, vs, rule, resolved, splits, prov, fails):
    counts = Counter(v["verdict"] for v in vs)
    if rule == "1":
        resolved.append(tag(vs[0], "agg:1"))
        prov.append({"claim_id": cid, "rule": "single", "members": [vs[0]["verifier"]]})
    elif rule == "2+judge-on-split":
        if len(counts) == 1:
            resolved.append(tag(vs[0], "agg:2"))
            prov.append({"claim_id": cid, "rule": "pair-agree", "members": [v["verifier"] for v in vs]})
        else:
            splits.append({"claim_id": cid, "reason": "pair_split", "candidates": vs})
    elif rule == "3-majority":
        top, ntop = counts.most_common(1)[0]
        if ntop >= 2:
            winner = next(v for v in vs if v["verdict"] == top)
            resolved.append(tag(winner, "agg:majority"))
            prov.append({"claim_id": cid, "rule": "majority", "winner": top,
                         "members": [v["verifier"] for v in vs]})
        else:
            splits.append({"claim_id": cid, "reason": "no_majority_1_1_1", "candidates": vs})
    else:
        fails.append({"claim_id": cid, "status": "FAIL", "reason": f"unknown_AGG_RULE:{rule}"})

def main(run_dir):
    cfg = json.load(open(os.path.join(run_dir, "config.json")))
    agg_rule = cfg["AGG_RULE"]
    fallback = bool(cfg.get("cross_family_fallback", False))
    claims = {c["claim_id"]: c for c in load_jsonl(os.path.join(run_dir, "claims.jsonl"))}
    raw = {}
    shards = sorted(glob.glob(os.path.join(run_dir, "cl-*.jsonl")) +
                    glob.glob(os.path.join(run_dir, "gm-*.jsonl")))
    for shard in shards:
        for v in load_jsonl(shard):
            raw.setdefault(v["claim_id"], []).append(v)

    resolved, splits, prov, fails = [], [], [], []
    for cid, claim in claims.items():
        vs = raw.get(cid, [])
        ctype = claim["type"]
        if not vs:
            fails.append({"claim_id": cid, "status": "FAIL", "reason": "no_verdict_from_any_worker"})
            continue
        if ctype == "TYPE_D":
            pick = next((v for v in vs if v["verdict"] == "OPINION"), vs[0])
            resolved.append(tag(pick, "agg:opinion"))
            prov.append({"claim_id": cid, "rule": "opinion", "members": [v["verifier"] for v in vs]})
            continue
        if ctype == "TYPE_C":
            fams = {v.get("family") for v in vs}
            degraded = False
            if not ({"claude", "gemini"} <= fams):
                if fallback and fams == {"claude"} and len(vs) >= 2:
                    degraded = True   # 誠實降級:claude 雙 tier 交叉
                else:
                    fails.append({"claim_id": cid, "status": "FAIL",
                                  "reason": "typeC_missing_cross_family", "fams": sorted(fams)})
                    continue
            verdicts = {v["verdict"] for v in vs}
            suffix = "-DEGRADED" if degraded else ""
            if len(verdicts) == 1:
                resolved.append(tag(vs[0], "agg:cross-family-agree" + suffix))
                prov.append({"claim_id": cid, "rule": "cross-family-agree" + suffix,
                             "members": [v["verifier"] for v in vs]})
            else:
                splits.append({"claim_id": cid, "reason": "typeC_cross_family_split" + suffix,
                               "candidates": vs})
            continue
        # TYPE_A / TYPE_B
        apply_agg(cid, vs, agg_rule, resolved, splits, prov, fails)

    dump_jsonl(os.path.join(run_dir, "verdicts.jsonl"), resolved)
    dump_jsonl(os.path.join(run_dir, "split-queue.jsonl"), splits)
    dump_jsonl(os.path.join(run_dir, "agg-provenance.jsonl"), prov)
    if fails:
        append_jsonl(os.path.join(run_dir, "dispatch-fail.jsonl"), fails)
    print(f"AGGREGATE resolved={len(resolved)} splits={len(splits)} fails={len(fails)} run={run_dir}")
    return 1 if fails else 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: tv-aggregate.py <run-dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
