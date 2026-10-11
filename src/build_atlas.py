"""Stage 4: turn author profiles into a 2D subreddit embedding.

Pipeline: author x subreddit incidence -> BM25 weighting -> truncated SVD
-> L2 normalise -> UMAP(cosine) -> HDBSCAN clusters.

Weighting has to happen: on raw counts every community looks similar to
r/AskReddit, because a large share of any author sample comments there, and the
map collapses toward a single hub.

This originally used PPMI on the reasoning that dividing out base rates leaves
only surprising association. Measurement disagreed. PPMI over-corrects: it
punishes pairs that are related *and* both popular, and on the known-pair test
it scored worse than doing nothing at all (median partner rank 30 vs 20 for raw
counts). BM25 won both metrics and is now the default. See src/validate.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "data" / "raw" / "profiles.jsonl"
SEEDS = ROOT / "data" / "raw" / "seeds.json"
META = ROOT / "data" / "raw" / "subreddit_meta.jsonl"
TEMPORAL = ROOT / "data" / "raw" / "profiles_temporal.jsonl"
OUT = ROOT / "data" / "interim" / "atlas.json"


def load(min_subs_per_author: int, max_subs_per_author: int, min_authors: int,
         include_round2: bool = True):
    """Build the author x subreddit incidence matrix.

    The mapped set is every subreddit the profiles revealed often enough to place,
    not just the original seeds. The seed list existed only to discover a diverse
    author population; restricting the columns to it threw away ~99% of the
    subreddits those authors actually turned out to inhabit.
    """
    subscribers: dict[str, int] = {}
    nsfw: set[str] = set()
    if META.exists():
        with META.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                subscribers[m["subreddit"]] = m.get("subscribers") or 0
                if m.get("over18"):
                    nsfw.add(m["subreddit"])
    else:
        seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
        subscribers = {s["subreddit"]: s["subscribers"] for s in seeds}
        nsfw = {s["subreddit"] for s in seeds if s.get("over18")}
    keep = set(subscribers)

    rows, cols = [], []
    sub_ix: dict[str, int] = {}
    n_authors = 0
    skipped_narrow = skipped_broad = 0

    def sources():
        """Round-one profiles, plus the debiased round-two pool if present.

        Round one drew its authors only from the top 1,000 subreddits, so anyone
        who never comments in a large community was invisible, and niche
        subreddits were positioned mostly through whichever mainstream subs their
        members happened to share. Round two stratifies over every mapped
        subreddit; including it is what removes that bias.
        """
        with PROFILES.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    yield json.loads(line)["s"]
                except (json.JSONDecodeError, KeyError):
                    continue
        if include_round2 and TEMPORAL.exists():
            with TEMPORAL.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        per = json.loads(line)["p"]
                    except (json.JSONDecodeError, KeyError):
                        continue
                    merged: dict[str, int] = {}
                    for counts in per.values():        # flatten the periods
                        for kk, vv in counts.items():
                            merged[kk] = merged.get(kk, 0) + vv
                    yield merged

    for rec_subs in sources():
        subs = [s for s in rec_subs if s in keep]
        if len(subs) < min_subs_per_author:
            skipped_narrow += 1
            continue
        if len(subs) > max_subs_per_author:
            # Accounts touching a huge share of the map are bots or
            # karma farmers; they link everything to everything.
            skipped_broad += 1
            continue
        for s in subs:
            if s not in sub_ix:
                sub_ix[s] = len(sub_ix)
            rows.append(n_authors)
            cols.append(sub_ix[s])
        n_authors += 1

    X = sp.csr_matrix(
        (np.ones(len(rows), dtype=np.float32), (rows, cols)),
        shape=(n_authors, len(sub_ix)),
    )
    names = np.array(sorted(sub_ix, key=sub_ix.get))

    # Drop subreddits with too few sampled authors to place reliably.
    counts = np.asarray(X.sum(axis=0)).ravel()
    live = counts >= min_authors
    X, names, counts = X[:, live], names[live], counts[live]

    print(f"authors used      : {n_authors:,}")
    print(f"  dropped <{min_subs_per_author} subs : {skipped_narrow:,}")
    print(f"  dropped >{max_subs_per_author} subs: {skipped_broad:,}")
    print(f"subreddits kept   : {len(names):,} (>= {min_authors} authors each)")
    print(f"nonzeros          : {X.nnz:,}")
    return X, names, counts, subscribers, nsfw


def bm25(X: sp.csr_matrix, k1: float = 1.5, b: float = 0.75) -> sp.csr_matrix:
    """BM25 over subreddit "documents" of commenters.

    This is the default because it measurably beats PPMI, not because it is
    fashionable. On a fixed set of 18 unarguable subreddit pairs, median rank of
    a partner in its counterpart's neighbour list was 2 under BM25 versus 30
    under PPMI, and split-half neighbour agreement was 0.357 versus 0.331
    (src/validate.py reproduces both).

    The reason is that PPMI over-corrects for popularity. Dividing out base rates
    punishes pairs that are genuinely related *and* both large: r/gaming and
    r/videogames sat 414 neighbours apart under PPMI and 21 apart under BM25.
    BM25's frequency saturation is gentler, and its IDF term damps ubiquitous
    subreddits without erasing association between popular ones.
    """
    M = X.tocsc().astype(np.float64)
    dl = np.asarray(M.sum(axis=0)).ravel()           # commenters per subreddit
    avgdl = dl.mean() if dl.size else 1.0
    n_docs = M.shape[1]
    df = np.asarray((M > 0).sum(axis=1)).ravel()     # subreddits per author
    idf = np.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
    C = M.tocoo()
    denom = C.data + k1 * (1 - b + b * dl[C.col] / max(avgdl, 1e-9))
    vals = idf[C.row] * (C.data * (k1 + 1)) / np.maximum(denom, 1e-12)
    W = sp.coo_matrix((vals, (C.row, C.col)), shape=M.shape).tocsr()
    W.eliminate_zeros()
    return W


def ppmi(X: sp.csr_matrix) -> sp.csr_matrix:
    """Positive pointwise mutual information over the incidence matrix."""
    X = X.tocsc().astype(np.float64)
    total = X.sum()
    col = np.asarray(X.sum(axis=0)).ravel()          # per subreddit
    row = np.asarray(X.sum(axis=1)).ravel()          # per author
    Xc = X.tocoo()
    with np.errstate(divide="ignore", invalid="ignore"):
        vals = np.log(
            (Xc.data * total) / (row[Xc.row] * col[Xc.col])
        )
    vals[~np.isfinite(vals)] = 0.0
    vals = np.maximum(vals, 0.0)
    M = sp.coo_matrix((vals, (Xc.row, Xc.col)), shape=X.shape).tocsr()
    M.eliminate_zeros()
    return M


def main(a):
    X, names, counts, subscribers, nsfw = load(
        a.min_subs_per_author, a.max_subs_per_author, a.min_authors,
        include_round2=not a.round1_only,
    )
    print(f"\nweighting with {a.weight.upper()} ...")
    weigh = {"bm25": bm25, "ppmi": ppmi}[a.weight]
    M = weigh(X).T.tocsr()                # subreddits x authors

    dims = min(a.dims, min(M.shape) - 1)
    print(f"SVD -> {dims} dims ...")
    V = TruncatedSVD(n_components=dims, random_state=0).fit_transform(M)
    V = normalize(V)

    print("UMAP -> 2D ...")
    import umap
    # min_dist/spread govern how evenly the map fills its canvas. Tight values
    # pack ~9.5k points into an overplotted core with most of the frame empty,
    # which also starves the label placer of room.
    emb = umap.UMAP(
        n_neighbors=a.neighbors,
        min_dist=a.min_dist,
        spread=a.spread,
        metric="cosine",
        random_state=42,
        verbose=False,
    ).fit_transform(V)

    print("clustering ...")
    labels = HDBSCAN(
        min_cluster_size=a.min_cluster_size, min_samples=3
    ).fit_predict(emb)
    n_clusters = len({l for l in labels if l >= 0})
    print(f"  {n_clusters} clusters, {(labels < 0).sum()} unclustered")

    out = {
        "subreddits": [
            {
                "name": str(n),
                "x": float(emb[i, 0]),
                "y": float(emb[i, 1]),
                "cluster": int(labels[i]),
                "authors": int(counts[i]),
                "subscribers": int(subscribers.get(str(n), 0)),
                "nsfw": str(n) in nsfw,
            }
            for i, n in enumerate(names)
        ],
        "n_clusters": n_clusters,
        "method": {
            "weight": a.weight, "dims": dims,
            "neighbors": a.neighbors, "min_dist": a.min_dist, "spread": a.spread,
            "min_authors": a.min_authors,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"\nwrote {len(names)} positioned subreddits -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--round1-only", action="store_true",
                    help="exclude the debiased round-two author pool")
    ap.add_argument("--min-subs-per-author", type=int, default=2)
    ap.add_argument("--max-subs-per-author", type=int, default=60)
    ap.add_argument("--min-authors", type=int, default=30)
    ap.add_argument("--weight", choices=["bm25", "ppmi"], default="bm25",
                    help="term weighting; bm25 validated better (see validate.py)")
    ap.add_argument("--dims", type=int, default=128)
    ap.add_argument("--neighbors", type=int, default=30)
    ap.add_argument("--min-dist", type=float, default=0.35)
    ap.add_argument("--spread", type=float, default=1.6)
    ap.add_argument("--min-cluster-size", type=int, default=25)
    main(ap.parse_args())
