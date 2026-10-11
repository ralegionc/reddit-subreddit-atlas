"""Stage 3b: fetch metadata for every subreddit the author profiles revealed.

The seed list was only ever a device for discovering a diverse author population.
The profiles those authors returned mention ~105k distinct subreddits, and all
but the original 1,000 were being discarded at build time. Everything above a
minimum number of sampled commenters can be placed on the map, which is a ~10x
larger atlas for no additional comment fetching.

What is missing for those subreddits is metadata. `over18` matters most: without
it the neutral-labelling rule silently fails open on precisely the communities it
exists to handle. Subscriber counts are wanted too, but they are optional -- a
subreddit that cannot be looked up still gets placed, sized by sampled commenters.

Resumable: appends JSONL, skips names already present.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import arctic

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "data" / "raw" / "profiles.jsonl"
OUT = ROOT / "data" / "raw" / "subreddit_meta.jsonl"


def candidates(min_authors: int) -> list[str]:
    authors: Counter[str] = Counter()
    with PROFILES.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for s in rec["s"]:
                authors[s] += 1
    return sorted(s for s, c in authors.items() if c >= min_authors)


def fetch_one(name: str) -> dict:
    rows = arctic.get(
        "subreddits/search",
        {"subreddit": name, "limit": 1,
         "fields": "display_name,subscribers,over18"},
    )
    for r in rows:
        # The endpoint matches loosely, so confirm it returned the right one.
        if (r.get("display_name") or "").lower() == name.lower():
            return {
                "subreddit": name,
                "subscribers": r.get("subscribers") or 0,
                "over18": bool(r.get("over18")),
                "found": True,
            }
    return {"subreddit": name, "subscribers": 0, "over18": False, "found": False}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-authors", type=int, default=30)
    args = ap.parse_args()

    done: set[str] = set()
    if OUT.exists():
        with OUT.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["subreddit"])
                except (json.JSONDecodeError, KeyError):
                    pass

    names = candidates(args.min_authors)
    todo = [n for n in names if n not in done]
    print(f"{len(names):,} subreddits >= {args.min_authors} sampled authors")
    print(f"cached {len(done):,} | to fetch {len(todo):,}\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    found = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for _, res in arctic.imap(fetch_one, todo, desc="meta"):
            if res:
                fh.write(json.dumps(res) + "\n")
                found += res["found"]
    print(f"\nwrote metadata for {len(todo):,} subreddits ({found:,} resolved)")
