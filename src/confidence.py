"""Stage 7b: per-subreddit placement confidence, by bootstrap.

Validation showed neighbour agreement tracks how much evidence a subreddit has
(0.27 for the thinnest quarter against 0.41 for the densest). The map itself
said nothing about that: a subreddit placed from 30 sampled commenters was drawn
exactly like one placed from 15,000.

This resamples the author population with replacement, rebuilds the
representation each time, and scores each subreddit by how much its neighbour
set survives resampling. Confidence is measured in the 128-d space rather than
in 2-d: UMAP would cost minutes per replicate, and neighbourhoods are what the
map actually claims -- the projection's own fidelity is measured separately by
trustworthiness in validate.py.

Writes `confidence` back into atlas.json so the renderers can use it.
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
    X, names, counts, _subs, _nsfw = B.load(2, a.max_subs_per_author, a.min_authors)
    rng = np.random.default_rng(7)
    n_auth = X.shape[0]

    print(f"bootstrapping {a.reps} replicates over {n_auth:,} authors "
          f"({len(names):,} subreddits, k={a.k})")

    neighbour_sets: list[np.ndarray] = []
    for rep in range(a.reps):
        idx = rng.integers(0, n_auth, size=n_auth)     # resample with replacement
        Vr = V.embed(X[idx], a.weight, a.dims)
        neighbour_sets.append(V.knn(Vr, a.k))
        print(f"  replicate {rep + 1}/{a.reps}", flush=True)

    # Mean pairwise neighbour agreement across replicates.
    pairs = 0
    agree = np.zeros(len(names))
    for i in range(len(neighbour_sets)):
        for j in range(i + 1, len(neighbour_sets)):
            agree += V.jaccard_rows(neighbour_sets[i], neighbour_sets[j])
            pairs += 1
    agree /= max(pairs, 1)

    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    conf = {n: float(c) for n, c in zip(names, agree)}
    hit = 0
    for r in atlas["subreddits"]:
        if r["name"] in conf:
            r["confidence"] = round(conf[r["name"]], 4)
            hit += 1
        else:
            r["confidence"] = None
    atlas["confidence"] = {
        "reps": a.reps, "k": a.k, "weight": a.weight,
        "mean": float(agree.mean()), "median": float(np.median(agree)),
    }
    ATLAS.write_text(json.dumps(atlas), encoding="utf-8")

    print(f"\nmean confidence   : {agree.mean():.3f}")
    print(f"median            : {np.median(agree):.3f}")
    for q, tag in [(10, "bottom 10%"), (50, "median"), (90, "top 10%")]:
        print(f"  {tag:<12}: {np.percentile(agree, q):.3f}")
    lo = agree < a.floor
    print(f"\nbelow {a.floor} confidence: {lo.sum():,} subreddits "
          f"({100 * lo.mean():.0f}%) -- median {int(np.median(counts[lo]))} commenters")
    print(f"wrote confidence for {hit:,} subreddits -> {ATLAS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--dims", type=int, default=128)
    ap.add_argument("--weight", default="bm25")
    ap.add_argument("--min-authors", type=int, default=30)
    ap.add_argument("--max-subs-per-author", type=int, default=60)
    ap.add_argument("--floor", type=float, default=0.25)
    main(ap.parse_args())
