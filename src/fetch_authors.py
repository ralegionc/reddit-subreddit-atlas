"""Stage 2: sample commenters per subreddit.

Sampling is spread over monthly slices instead of one contiguous block. A
contiguous block of a few thousand comments is often dominated by two or three
megathreads, which makes the author set reflect one event rather than the
community. Monthly slices cost the same number of requests and sample far more
independently.

Resumable: one JSON file per subreddit, existing files are skipped.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import arctic

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "data" / "raw" / "seeds.json"
OUTDIR = ROOT / "data" / "raw" / "authors"

# Deleted accounts and site-wide bots are not community members; they would
# link every subreddit to every other one.
SKIP_AUTHORS = {
    "[deleted]", "AutoModerator", "None", "", "RemindMeBot", "sneakpeekbot",
    "VredditDownloader", "SaveVideo", "converter-bot", "haikusbot",
    "WikiSummarizerBot", "B0tRank", "stabbot", "GoodBot_BadBot",
    "timestamp_bot", "same_post_bot", "repostsleuthbot", "AmputatorBot",
}
MONTH = 30 * 86400


def slice_bounds(n_slices: int, span_days: int) -> list[tuple[int, int]]:
    now = int(time.time())
    start = now - span_days * 86400
    width = (now - start) // n_slices
    return [(start + i * width, start + (i + 1) * width) for i in range(n_slices)]


def fetch_one(sub: str, slices: list[tuple[int, int]], pages: int) -> dict:
    authors: Counter[str] = Counter()
    n = 0
    for lo, hi in slices:
        cursor = lo
        for _ in range(pages):
            rows = arctic.get(
                "comments/search",
                {
                    "subreddit": sub,
                    "limit": arctic.MAX_LIMIT,
                    "fields": "author,created_utc",
                    "after": cursor,
                    "before": hi,
                    "sort": "asc",
                },
            )
            if not rows:
                break
            for r in rows:
                a = r.get("author")
                if a and a not in SKIP_AUTHORS:
                    authors[a] += 1
            n += len(rows)
            newest = max((r.get("created_utc") or cursor) for r in rows)
            if newest <= cursor:
                break            # no forward progress; slice exhausted
            cursor = newest + 1
            if len(rows) < arctic.MAX_LIMIT:
                break            # slice ran dry before the page filled
    return {
        "subreddit": sub,
        "n_comments": n,
        "n_authors": len(authors),
        "authors": dict(authors),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N seeds (0 = all)")
    ap.add_argument("--source", choices=["seeds", "atlas"], default="seeds",
                    help="atlas = sweep every mapped subreddit, not just seeds")
    ap.add_argument("--slices", type=int, default=12)
    ap.add_argument("--pages", type=int, default=3, help="pages of 100 per slice")
    ap.add_argument("--span-days", type=int, default=365)
    a = ap.parse_args()

    if a.source == "atlas":
        # Round two seeds from the subreddits the profiles actually revealed, so
        # the author pool stops being drawn only from the largest communities.
        atlas = json.loads(
            (ROOT / "data" / "interim" / "atlas.json").read_text(encoding="utf-8")
        )
        seeds = [{"subreddit": r["name"], "subscribers": r.get("subscribers", 0)}
                 for r in atlas["subreddits"]]
        seeds.sort(key=lambda r: -r["subscribers"])
    else:
        seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    if a.limit:
        seeds = seeds[: a.limit]
    OUTDIR.mkdir(parents=True, exist_ok=True)

    todo = [s["subreddit"] for s in seeds if not (OUTDIR / f"{s['subreddit']}.json").exists()]
    print(f"{len(seeds)} seeds, {len(seeds)-len(todo)} already cached, {len(todo)} to fetch")
    print(f"budget: {len(todo) * a.slices * a.pages:,} requests\n")

    sl = slice_bounds(a.slices, a.span_days)
    got = 0
    for sub, res in arctic.imap(
        lambda s: fetch_one(s, sl, a.pages), todo, desc="subs"
    ):
        if res and res["n_comments"] > 0:
            (OUTDIR / f"{sub}.json").write_text(json.dumps(res), encoding="utf-8")
            got += 1
    print(f"\nwrote {got} subreddit author files -> {OUTDIR}")
