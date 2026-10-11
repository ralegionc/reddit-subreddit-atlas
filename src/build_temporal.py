"""Stage 4b: how did the map move between two periods?

The hard part of a temporal map is that two independently fitted embeddings are
not comparable. UMAP is free to rotate, reflect and rescale, so a subreddit can
"move" a long way on screen without anything having changed in the data, and
Procrustes alignment only papers over that.

So both periods are embedded ONCE, together. Each subreddit contributes two rows
to a single matrix -- its commenters in period one and its commenters in period
two -- over a shared author vocabulary. One BM25, one SVD, one UMAP. Both points
therefore live in the same space by construction, and the segment between them is
a real displacement rather than an artefact of fitting twice.

Drift is still mostly noise unless it is measured against noise. The floor is
built by resplitting period one's own comments binomially between two replicates
over the identical author columns, which is what "the same people, sampled
differently" actually looks like. It is computed PER SUBREDDIT: a thinly sampled
community is noisy on its own terms, and judging it against a floor averaged over
well-sampled ones simply ranks thin communities to the top.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

import build_atlas as B

ROOT = Path(__file__).resolve().parent.parent
TEMPORAL = ROOT / "data" / "raw" / "profiles_temporal.jsonl"
OUT = ROOT / "data" / "interim" / "temporal.json"


def load_periods(min_authors: int):
    """-> (period tags, list of csr [subreddit x author] per period, names)."""
    authors: list[str] = []
    per_rows: dict[str, list[tuple[int, str, int]]] = {}
    tags: list[str] = []

    with TEMPORAL.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ai = len(authors)
            authors.append(rec["a"])
            for tag, counts in rec["p"].items():
                if tag not in per_rows:
                    per_rows[tag] = []
                    tags.append(tag)
                for sub, n in counts.items():
                    per_rows[tag].append((ai, sub, n))

    tags.sort()
    # A subreddit is comparable only if both periods saw enough of it; otherwise
    # "movement" is really just an appearance or a disappearance.
    seen = {t: Counter(s for _, s, _ in per_rows[t]) for t in tags}
    names = sorted(
        s for s in set.intersection(*[set(seen[t]) for t in tags])
        if all(seen[t][s] >= min_authors for t in tags)
    )
    ix = {s: i for i, s in enumerate(names)}

    mats = []
    for t in tags:
        r, c, v = [], [], []
        for ai, sub, n in per_rows[t]:
            j = ix.get(sub)
            if j is not None:
                r.append(j); c.append(ai); v.append(float(n))
        mats.append(sp.csr_matrix((v, (r, c)),
                                  shape=(len(names), len(authors)), dtype=np.float32))
    print(f"periods    : {tags}")
    print(f"authors    : {len(authors):,}")
    print(f"comparable : {len(names):,} subreddits (>= {min_authors} in every period)")
    return tags, mats, names


def joint_embed(mats, dims, neighbors, min_dist, spread, seed=42):
    """Stack every (subreddit, period) row into one space and embed once."""
    stacked = sp.vstack(mats).tocsr()
    W = B.bm25(stacked.T.tocsr()).T.tocsr()          # bm25 expects author x sub
    d = min(dims, min(W.shape) - 1)
    V = normalize(TruncatedSVD(n_components=d, random_state=0).fit_transform(W))
    import umap
    emb = umap.UMAP(n_neighbors=neighbors, min_dist=min_dist, spread=spread,
                    metric="cosine", random_state=seed).fit_transform(V)
    return V, emb


def main(a):
    tags, mats, names = load_periods(a.min_authors)
    n = len(names)

    print("\njoint embedding of all periods ...")
    V, emb = joint_embed(mats, a.dims, a.neighbors, a.min_dist, a.spread)
    P = [emb[i * n : (i + 1) * n] for i in range(len(tags))]
    Vp = [V[i * n : (i + 1) * n] for i in range(len(tags))]

    drift2d = np.linalg.norm(P[-1] - P[0], axis=1)
    drift_cos = 1.0 - np.sum(Vp[0] * Vp[-1], axis=1)

    # Noise floor. The first attempt split period one into two DISJOINT halves
    # of authors, which is wrong: disjoint author sets share no columns, so the
    # two halves come out near-orthogonal by construction and the floor lands at
    # ~0.97 cosine, above any real signal. The genuine comparison holds the
    # author population fixed and varies only which of their comments were
    # sampled, so the null has to do the same. Each period-one count is split
    # binomially between two replicates over the identical author columns.
    print("estimating the noise floor (binomial resplit, same authors) ...")
    rng = np.random.default_rng(3)
    C = mats[0].tocoo()
    left = rng.binomial(C.data.astype(np.int64), 0.5).astype(np.float32)
    ref = [
        sp.coo_matrix((left, (C.row, C.col)), shape=C.shape).tocsr(),
        sp.coo_matrix((C.data - left, (C.row, C.col)), shape=C.shape).tocsr(),
    ]
    for m in ref:
        m.eliminate_zeros()
    floors = []
    for rep in range(a.null_reps):
        if rep:
            left = rng.binomial(C.data.astype(np.int64), 0.5).astype(np.float32)
            ref = [sp.coo_matrix((left, (C.row, C.col)), shape=C.shape).tocsr(),
                   sp.coo_matrix((C.data - left, (C.row, C.col)),
                                 shape=C.shape).tocsr()]
            for m in ref:
                m.eliminate_zeros()
        Vr, er = joint_embed(ref, a.dims, a.neighbors, a.min_dist, a.spread,
                             seed=42 + rep)
        floors.append(1.0 - np.sum(Vr[:n] * Vr[n:], axis=1))
        if rep == 0:
            floor2d = np.linalg.norm(er[n:] - er[:n], axis=1)
    # PER SUBREDDIT, not a single global median. A thinly sampled subreddit is
    # noisy on its own terms, so judging it against a floor built mostly from
    # well-sampled ones just ranks thin subreddits to the top. Averaging a few
    # replicates keeps the per-subreddit floor from being noise itself.
    floor_cos = np.mean(floors, axis=0)
    f2, fc = float(np.median(floor2d)), float(np.median(floor_cos))
    print(f"  median null drift : {f2:.2f} (2d)   {fc:.3f} (cosine)")
    print(f"  median real drift : {np.median(drift2d):.2f} (2d)   "
          f"{np.median(drift_cos):.3f} (cosine)")

    score = drift_cos / np.maximum(floor_cos, 1e-6)
    signal = score >= a.threshold
    print(f"\n{int(signal.sum()):,} of {n:,} subreddits moved >= {a.threshold}x "
          f"the sampling floor")

    # Record which communities each mover moved TOWARD. Computed here, where the
    # period vectors already exist, so the chart needs no side-car file.
    order = np.argsort(-score)
    gained_map: dict[str, list[str]] = {}
    for i in order[: a.annotate]:
        g0 = set(np.argsort(-(Vp[0] @ Vp[0][i]))[1 : a.k + 1])
        g1 = set(np.argsort(-(Vp[-1] @ Vp[-1][i]))[1 : a.k + 1])
        gained_map[str(names[i])] = [str(names[j]) for j in list(g1 - g0)[:6]]

    print(f"\ntop movers ({tags[0]} -> {tags[-1]}):")
    print(f"  {'subreddit':<28}{'xnull':>7}{'n':>7}   neighbours gained")
    kn = a.k
    for i in order[:a.show]:
        s0 = set(np.argsort(-(Vp[0] @ Vp[0][i]))[1 : kn + 1])
        s1 = set(np.argsort(-(Vp[-1] @ Vp[-1][i]))[1 : kn + 1])
        gained = [names[j] for j in list(s1 - s0)[:3]]
        nobs = int(min(m[i].nnz for m in mats))
        print(f"  r/{names[i]:<26}{score[i]:>6.1f}x{nobs:>7}   "
              + (", ".join("r/" + g for g in gained) if gained else "-"))

    OUT.write_text(json.dumps({
        "periods": tags,
        "null_floor": {"cosine": fc, "2d": f2},
        "threshold": a.threshold,
        "n_moved": int(signal.sum()),
        "gained": gained_map,
        "subreddits": [
            {"name": names[i],
             "x0": float(P[0][i, 0]), "y0": float(P[0][i, 1]),
             "x1": float(P[-1][i, 0]), "y1": float(P[-1][i, 1]),
             "drift": float(drift_cos[i]), "score": float(score[i]),
             "moved": bool(signal[i])}
            for i in range(n)
        ],
    }), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-authors", type=int, default=25)
    ap.add_argument("--dims", type=int, default=128)
    ap.add_argument("--neighbors", type=int, default=30)
    ap.add_argument("--min-dist", type=float, default=0.35)
    ap.add_argument("--spread", type=float, default=1.6)
    ap.add_argument("--threshold", type=float, default=2.0)
    ap.add_argument("--null-reps", type=int, default=3)
    ap.add_argument("--annotate", type=int, default=200,
                    help="record gained neighbours for the top N movers")
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--show", type=int, default=25)
    main(ap.parse_args())
