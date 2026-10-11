"""Stage 7c: nearest neighbours per subreddit, for the interactive map.

"What sits next to this?" is the question the map exists to answer, but a 2-d
picture can only answer it approximately -- two points can look adjacent while
being far apart in the representation. These neighbours are taken from the 128-d
space, so the panel reports the real answer rather than the projected one.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import build_atlas as B
import validate as V

ROOT = Path(__file__).resolve().parent.parent
ATLAS = ROOT / "data" / "interim" / "atlas.json"


def main(a):
    X, names, _c, _s, _n = B.load(2, a.max_subs_per_author, a.min_authors)
    print(f"embedding {len(names):,} subreddits ({a.weight}) ...")
    Vs = V.embed(X, a.weight, a.dims)
    print(f"top-{a.k} neighbours ...")
    N = V.knn(Vs, a.k)

    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    ix = {n: i for i, n in enumerate(names)}
    # Store as names, not row indices: the renderers filter and reorder rows, and
    # an index into a different ordering is a silent, hard-to-spot wrong answer.
    for r in atlas["subreddits"]:
        i = ix.get(r["name"])
        r["near"] = [str(names[j]) for j in N[i]] if i is not None else []
    atlas["neighbours"] = {"k": a.k, "weight": a.weight, "space": "svd128"}
    ATLAS.write_text(json.dumps(atlas), encoding="utf-8")
    print(f"wrote neighbours -> {ATLAS}")
    for probe in ("rust", "anime", "wallstreetbets"):
        i = ix.get(probe)
        if i is not None:
            print(f"  r/{probe}: " + ", ".join(str(names[j]) for j in N[i][:6]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--dims", type=int, default=128)
    ap.add_argument("--weight", default="bm25")
    ap.add_argument("--min-authors", type=int, default=30)
    ap.add_argument("--max-subs-per-author", type=int, default=60)
    main(ap.parse_args())
