#!/usr/bin/env python3
"""tv-split.py — mutated fixtures 的確定性 dev/holdout 切割（00-intent §5 ①）。

規則：slug 排序後最後一篇整篇入 holdout（保證兩密度+兩家族），其餘入 dev。需 >=2 slug。
輸出 fixtures/dev.list 與 fixtures/holdout.list（每行一個相對 fixtures/ 的路徑）。

用法：tv-split.py [MUTATED_DIR]  # 預設 truth-verify/fixtures/mutated
"""
import glob
import os
import sys


def split(mutated_dir):
    files = sorted(glob.glob(os.path.join(mutated_dir, "*.md")))
    if not files:
        raise SystemExit(f"no mutated files in {mutated_dir}")
    slugs = {}
    for f in files:
        parts = os.path.basename(f)[:-3].split(".")   # 去 .md → [slug..., fam, dens]
        if len(parts) < 3:
            raise SystemExit(f"bad name (need <slug>.<fam>.<dens>.md): {os.path.basename(f)}")
        slug = ".".join(parts[:-2])
        slugs.setdefault(slug, []).append(f)
    if len(slugs) < 2:
        raise SystemExit(f"need >=2 article slugs for split; got {sorted(slugs)}")
    ordered = sorted(slugs)
    holdout_slug = ordered[-1]
    dens_present = {os.path.basename(f)[:-3].split(".")[-1] for f in slugs[holdout_slug]}
    if not {"lo", "hi"} <= dens_present:
        raise SystemExit(
            f"holdout slug {holdout_slug} lacks both densities: {sorted(dens_present)}")
    dev, hold = [], []
    for slug in ordered:
        (hold if slug == holdout_slug else dev).extend(sorted(slugs[slug]))
    return dev, hold, holdout_slug


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    mutated_dir = argv[0] if argv else "truth-verify/fixtures/mutated"
    out_dir = os.path.dirname(mutated_dir.rstrip("/"))   # → fixtures/
    dev, hold, holdout_slug = split(mutated_dir)
    with open(os.path.join(out_dir, "dev.list"), "w", encoding="utf-8") as f:
        f.write("\n".join(os.path.relpath(p, out_dir) for p in dev) + "\n")
    with open(os.path.join(out_dir, "holdout.list"), "w", encoding="utf-8") as f:
        f.write("\n".join(os.path.relpath(p, out_dir) for p in hold) + "\n")
    print(f"SPLIT dev={len(dev)} holdout={len(hold)} holdout_slug={holdout_slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
