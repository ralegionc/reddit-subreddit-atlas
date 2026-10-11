"""Stage 3c: per-period author profiles, for the temporal map.

Serves two improvements with one pass.

COVERAGE. The round-one author pool was seeded entirely from the top 1,000
subreddits, so anyone who never comments in a large community was invisible, and
niche subreddits were positioned largely through whatever mainstream subs their
members happened to share. The pool here is stratified over every mapped
subreddit (see `fetch_authors.py --source atlas`), so niche communities
contribute their own members.

TIME. The original profiles stored only totals, with no dates, so "how did the
map move?" was unanswerable from what was on disk. Here each author is sampled
once per period, which is why this costs a request per author per period rather
than one per author.

Sampling the same authors in both periods is deliberate: it means a change in
the map is a change in where those people went, not an artefact of having
surveyed two different populations.

Resumable: appends JSONL, skips authors already complete.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

import arctic
from fetch_profiles import build_pool

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "profiles_temporal.jsonl"
DAY = 86400


def periods(n: int, span_days: int) -> list[tuple[str, int, int]]:
    """`n` contiguous windows ending now, oldest first."""
    now = int(time.time())
    width = span_days * DAY // n
    out = []
    for i in range(n):
        lo = now - (n - i) * width
        hi = now - (n - i - 1) * width
        out.append((time.strftime("%Y-%m", time.gmtime(lo)), lo, hi))
    return out


def fetch_author(author: str, wins: list[tuple[str, int, int]],
                 pages: int) -> dict | None:
    per: dict[str, dict[str, int]] = {}
    for tag, lo, hi in wins:
        subs: Counter[str] = Counter()
        cursor = hi
        for _ in range(pages):
            rows = arctic.get(
                "comments/search",
                {"author": author, "limit": arctic.MAX_LIMIT,
                 "fields": "subreddit,created_utc",
                 "after": lo, "before": cursor, "sort": "desc"},
            )
            if not rows:
                break
            for r in rows:
                s = r.get("subreddit")
                if s:
                    subs[s] += 1
            oldest = min((r.get("created_utc") or lo) for r in rows)
            if oldest >= cursor:
                break
            cursor = oldest - 1
            if len(rows) < arctic.MAX_LIMIT:
                break
        if subs:
            per[tag] = dict(subs)
    if not per:
        return None
    return {"a": author, "p": per}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-sub", type=int, default=25)
    ap.add_argument("--max-authors", type=int, default=32_000)
    ap.add_argument("--periods", type=int, default=2)
    ap.add_argument("--span-days", type=int, default=730)
    ap.add_argument("--pages", type=int, default=1)
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
    random.Random(11).shuffle(pool)
    pool = pool[: a.max_authors]
    todo = [p for p in pool if p not in done]

    wins = periods(a.periods, a.span_days)
    print(f"pool {len(pool):,} | cached {len(done):,} | to fetch {len(todo):,}")
    print("periods:")
    for tag, lo, hi in wins:
        print(f"  {tag}  {time.strftime('%Y-%m-%d', time.gmtime(lo))} .. "
              f"{time.strftime('%Y-%m-%d', time.gmtime(hi))}")
    print(f"budget: {len(todo) * a.periods * a.pages:,} requests\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for _, res in arctic.imap(
            lambda w: fetch_author(w, wins, a.pages), todo, desc="authors"
        ):
            if res:
                fh.write(json.dumps(res) + "\n")
                written += 1
                if written % 2000 == 0:
                    fh.flush()
    print(f"\nwrote {written:,} temporal profiles -> {OUT}")
