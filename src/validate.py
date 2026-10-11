"""Stage 7: does the map actually mean anything?

Everything else in this project rests on the map looking plausible. This module
tries to break it, three ways:

1. SPLIT-HALF STABILITY. Build the representation twice from disjoint halves of
   the authors. If a subreddit's neighbours are a real property of the data, the
   two halves should broadly agree; if they are sampling noise, they will not.
   Reported globally and per subreddit, so the per-subreddit number can be used
   as a confidence score downstream.

2. PROJECTION FIDELITY. UMAP is a lossy squeeze from 128 dimensions to 2. The
   trustworthiness score says how much of the neighbourhood structure survives
   that squeeze, which bounds how much anyone should read into the picture.

3. WEIGHTING ABLATION. The README claims PPMI is what makes the map readable.
   That claim was never tested. Here PPMI is scored against raw counts, log1p
   and BM25 on the same two measures, so the claim either earns its place or
   gets corrected.

Nothing here refetches; it all runs off profiles.jsonl.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.manifold import trustworthiness
from sklearn.preprocessing import normalize

import build_atlas as B

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "interim" / "validation.json"

# Pairs that any correct map must place near each other. Deliberately chosen to
# be unarguable rather than flattering: same-domain, different-name communities.
KNOWN_PAIRS = [
    ("anime", "manga"), ("Bitcoin", "CryptoCurrency"), ("Bitcoin", "ethereum"),
    ("movies", "television"), ("nfl", "CFB"), ("nba", "NBATalk"),
    ("skyrim", "Eldenring"), ("AskUK", "CasualUK"), ("soccer", "worldcup"),
    ("cats", "aww"), ("gaming", "videogames"), ("pcmasterrace", "buildapc"),
    ("personalfinance", "Frugal"), ("cooking", "Baking"), ("guitar", "Music"),
    ("baseball", "mlb"), ("hockey", "canada"), ("apple", "iphone"),
    ("Overwatch", "leagueoflegends"), ("StarWars", "Marvel"),
]


def weight(X: sp.csr_matrix, scheme: str) -> sp.csr_matrix:
    """Author x subreddit incidence -> weighted matrix."""
    if scheme == "ppmi":
        return B.ppmi(X)
    if scheme == "raw":
        return X.astype(np.float64)
    if scheme == "log1p":
        M = X.astype(np.float64).copy()
        M.data = np.log1p(M.data)
        return M
    if scheme == "bm25":
        # BM25 over the subreddit "documents": saturates frequency and damps
        # subreddits that simply appear everywhere.
        M = X.tocsc().astype(np.float64)
        k1, b = 1.5, 0.75
        dl = np.asarray(M.sum(axis=0)).ravel()
        avgdl = dl.mean() if dl.size else 1.0
        n_docs = M.shape[1]
        df = np.asarray((M > 0).sum(axis=1)).ravel()
        idf = np.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        C = M.tocoo()
        denom = C.data + k1 * (1 - b + b * dl[C.col] / max(avgdl, 1e-9))
        vals = idf[C.row] * (C.data * (k1 + 1)) / np.maximum(denom, 1e-12)
        return sp.coo_matrix((vals, (C.row, C.col)), shape=M.shape).tocsr()
    raise ValueError(scheme)


def embed(X: sp.csr_matrix, scheme: str, dims: int) -> np.ndarray:
    """Weighted incidence -> L2-normalised subreddit vectors."""
    M = weight(X, scheme).T.tocsr()                  # subreddits x authors
    d = min(dims, min(M.shape) - 1)
    V = TruncatedSVD(n_components=d, random_state=0).fit_transform(M)
    return normalize(V)


def knn(V: np.ndarray, k: int, block: int = 512) -> np.ndarray:
    """Top-k cosine neighbours per row, excluding self. Blocked to bound memory."""
    out = np.empty((V.shape[0], k), dtype=np.int32)
    for i in range(0, V.shape[0], block):
        S = V[i : i + block] @ V.T
        for r in range(S.shape[0]):
            S[r, i + r] = -np.inf                     # drop self
        idx = np.argpartition(-S, k, axis=1)[:, :k]
        rows = np.arange(S.shape[0])[:, None]
        order = np.argsort(-S[rows, idx], axis=1)
        out[i : i + block] = idx[rows, order]
    return out


def jaccard_rows(A: np.ndarray, B_: np.ndarray) -> np.ndarray:
    k = A.shape[1]
    return np.array([
        len(set(A[i]) & set(B_[i])) / len(set(A[i]) | set(B_[i]))
        for i in range(A.shape[0])
    ])


def pair_ranks(V: np.ndarray, name_ix: dict, pairs) -> tuple[list, list]:
    """Rank of each partner in the other's neighbour ordering (0 = nearest)."""
    ranks, used = [], []
    for a, b in pairs:
        ia, ib = name_ix.get(a), name_ix.get(b)
        if ia is None or ib is None:
            continue
        sims = V @ V[ia]
        sims[ia] = -np.inf
        ranks.append(int((sims > sims[ib]).sum()))
        used.append((a, b))
    return ranks, used


def main(a):
    X, names, counts, _subs, _nsfw = B.load(2, a.max_subs_per_author, a.min_authors)
    name_ix = {n: i for i, n in enumerate(names)}
    rng = np.random.default_rng(0)
    n_auth = X.shape[0]
    report: dict = {"n_subreddits": int(len(names)), "n_authors": int(n_auth)}

    # --- 1. split-half stability -------------------------------------------
    perm = rng.permutation(n_auth)
    h1, h2 = perm[: n_auth // 2], perm[n_auth // 2 :]
    print(f"\n[1] split-half stability  (k={a.k}, {len(h1):,} vs {len(h2):,} authors)")
    V1, V2 = embed(X[h1], "ppmi", a.dims), embed(X[h2], "ppmi", a.dims)
    N1, N2 = knn(V1, a.k), knn(V2, a.k)
    agree = jaccard_rows(N1, N2)

    # Random baseline: what agreement would look like with no signal at all.
    rand = (a.k / max(len(names) - 1, 1))
    print(f"    mean neighbour Jaccard : {agree.mean():.3f}")
    print(f"    median                 : {np.median(agree):.3f}")
    print(f"    chance baseline        : {rand:.4f}")
    print(f"    lift over chance       : {agree.mean() / max(rand, 1e-9):.0f}x")
    report["split_half"] = {
        "k": a.k, "mean_jaccard": float(agree.mean()),
        "median_jaccard": float(np.median(agree)),
        "chance": float(rand), "lift": float(agree.mean() / max(rand, 1e-9)),
    }

    # Stability against how much evidence each subreddit had.
    order = np.argsort(counts)
    for lo, hi, tag in [(0, 0.25, "thinnest 25%"), (0.25, 0.75, "middle 50%"),
                        (0.75, 1.0, "densest 25%")]:
        sel = order[int(lo * len(order)) : int(hi * len(order))]
        print(f"    {tag:<14}: jaccard {agree[sel].mean():.3f}  "
              f"(median {int(np.median(counts[sel]))} commenters)")
        report.setdefault("stability_by_evidence", {})[tag] = {
            "mean_jaccard": float(agree[sel].mean()),
            "median_commenters": int(np.median(counts[sel])),
        }

    # --- 2. projection fidelity --------------------------------------------
    print(f"\n[2] projection fidelity (128d -> 2d)")
    atlas = json.loads((ROOT / "data" / "interim" / "atlas.json").read_text("utf-8"))
    pos = {r["name"]: (r["x"], r["y"]) for r in atlas["subreddits"]}
    keep = [i for i, n in enumerate(names) if n in pos]
    Vfull = embed(X, "ppmi", a.dims)
    sub = rng.choice(keep, size=min(a.trust_sample, len(keep)), replace=False)
    emb2 = np.array([pos[names[i]] for i in sub])
    tw = trustworthiness(Vfull[sub], emb2, n_neighbors=a.k)
    print(f"    trustworthiness (k={a.k}, n={len(sub):,}) : {tw:.3f}")
    print(f"    (1.0 = every 2d neighbourhood is real; <0.7 = read positions loosely)")
    report["trustworthiness"] = {"k": a.k, "n": int(len(sub)), "score": float(tw)}

    # --- 3. weighting ablation ---------------------------------------------
    print(f"\n[3] weighting ablation")
    print(f"    {'scheme':<8}{'split-half J':>14}{'median pair rank':>19}"
          f"{'pairs in top-10':>18}")
    abl = {}
    for scheme in ("raw", "log1p", "bm25", "ppmi"):
        W1, W2 = embed(X[h1], scheme, a.dims), embed(X[h2], scheme, a.dims)
        j = jaccard_rows(knn(W1, a.k), knn(W2, a.k)).mean()
        Vs = embed(X, scheme, a.dims)
        ranks, used = pair_ranks(Vs, name_ix, KNOWN_PAIRS)
        med = float(np.median(ranks)) if ranks else float("nan")
        top10 = sum(r < 10 for r in ranks)
        print(f"    {scheme:<8}{j:>14.3f}{med:>19.0f}{top10:>13}/{len(ranks)}")
        abl[scheme] = {"split_half_jaccard": float(j), "median_pair_rank": med,
                       "pairs_in_top10": int(top10), "pairs_tested": len(ranks)}
    report["ablation"] = abl
    report["known_pairs_tested"] = [list(p) for p in used]

    best = min(abl, key=lambda s: abl[s]["median_pair_rank"])
    print(f"\n    best by pair rank: {best}")
    report["best_scheme"] = best

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=25, help="neighbourhood size")
    ap.add_argument("--dims", type=int, default=128)
    ap.add_argument("--min-authors", type=int, default=30)
    ap.add_argument("--max-subs-per-author", type=int, default=60)
    ap.add_argument("--trust-sample", type=int, default=3000)
    main(ap.parse_args())
