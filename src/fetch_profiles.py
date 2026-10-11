"""Stage 3: fetch each sampled author's cross-subreddit activity profile.

This is the load-bearing stage. Sampling subreddit-first gives a very sparse
co-occurrence matrix (measured: only 5.7% of authors appeared in 2+ subreddits).
Asking the API author-first instead returns 29-42 subreddits from a single
request, so one request yields a complete co-occurrence row rather than one
sparse cell. Same request budget, roughly two orders of magnitude more signal.

Resumable: profiles append to JSONL, already-fetched authors are skipped.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import arctic

ROOT = Path(__file__).resolve().parent.parent
AUTHORDIR = ROOT / "data" / "raw" / "authors"
OUT = ROOT / "data" / "raw" / "profiles.jsonl"


def build_pool(per_sub: int, seed: int = 0) -> list[str]:
    """Stratified sample: up to `per_sub` authors from each subreddit.

    Stratifying matters. Pooling every author and sampling globally would draw
    overwhelmingly from the largest subreddits, and the resulting map would
    resolve the defaults in detail while leaving niche communities as noise.
    """
    rng = random.Random(seed)
    pool: set[str] = set()
    files = sorted(AUTHORDIR.glob("*.json"))
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        authors = list(rec.get("authors", {}))
        rng.shuffle(authors)
        pool.update(authors[:per_sub])
    return sorted(pool)


def fetch_profile(author: str, pages: int) -> dict | None:
    subs: Counter[str] = Counter()
    cursor = None
    for _ in range(pages):
        params = {
            "author": author,
            "limit": arctic.MAX_LIMIT,
            "fields": "subreddit,created_utc",
            "sort": "desc",
        }
        if cursor is not None:
            params["before"] = cursor
        rows = arctic.get("comments/search", params)
        if not rows:
            break
        for r in rows:
            s = r.get("subreddit")
            if s:
                subs[s] += 1
        oldest = min((r.get("created_utc") or 0) for r in rows)
        if cursor is not None and oldest >= cursor:
            break
        cursor = oldest - 1
        if len(rows) < arctic.MAX_LIMIT:
            break
    if not subs:
        return None
    return {"a": author, "n": sum(subs.values()), "s": dict(subs)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-sub", type=int, default=60, help="authors sampled per subreddit")
    ap.add_argument("--max-authors", type=int, default=60_000)
    ap.add_argument("--pages", type=int, default=1, help="pages of 100 comments per author")
    a = ap.parse_args()

    done: set[str] = set()
    if OUT.exists():
        with OUT.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["a"])
                except (json.JSONDecodeError, KeyError):
                    pass

    pool = build_pool(a.per_sub)
    random.Random(1).shuffle(pool)
    pool = pool[: a.max_authors]
    todo = [p for p in pool if p not in done]

    print(f"pool {len(pool):,} authors | cached {len(done):,} | to fetch {len(todo):,}")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for _, res in arctic.imap(
            lambda w: fetch_profile(w, a.pages), todo, desc="authors"
        ):
            if res:
                fh.write(json.dumps(res) + "\n")
                written += 1
                if written % 2000 == 0:
                    fh.flush()
    print(f"\nwrote {written:,} profiles -> {OUT}")
