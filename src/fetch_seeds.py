"""Stage 1: build the seed list of subreddits, ranked by subscriber count.

The subreddits endpoint returns results already ordered by subscribers
descending, so paging is done by walking `max_subscribers` down to the
smallest subreddit seen on the previous page.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import arctic

OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "seeds.json"

# Meta/default subreddits that everyone is auto-subscribed to or that carry no
# community signal. Including them adds a hub that every other node links to,
# which collapses the embedding toward a single blob.
DROP = {
    "announcements", "blog", "reddit.com", "modnews", "redditdev",
    "all", "popular", "friends", "mod", "u_", "mildlyinteresting",
}


def fetch(target: int, min_subs: int) -> list[dict]:
    seen: dict[str, dict] = {}
    cursor = None
    stalls = 0

    while len(seen) < target and stalls < 3:
        params = {
            "limit": arctic.MAX_LIMIT,
            "fields": "display_name,subscribers,over18",
            "min_subscribers": min_subs,
        }
        if cursor is not None:
            params["max_subscribers"] = cursor

        page = arctic.get("subreddits/search", params)
        if not page:
            stalls += 1
            continue

        before = len(seen)
        for row in page:
            name = (row.get("display_name") or "").strip()
            subs = row.get("subscribers") or 0
            if not name or name.lower() in DROP or name.lower().startswith("u_"):
                continue
            seen.setdefault(name, {"subreddit": name, "subscribers": subs,
                                   "over18": bool(row.get("over18"))})

        lowest = min(r.get("subscribers") or 0 for r in page)
        # Guard against a page whose entries all share one subscriber count,
        # which would otherwise pin the cursor and loop forever.
        cursor = lowest - 1 if lowest == cursor else lowest
        stalls = 0 if len(seen) > before else stalls + 1
        print(f"  seeds: {len(seen)}  cursor={cursor}", flush=True)

        if cursor is not None and cursor < min_subs:
            break

    ranked = sorted(seen.values(), key=lambda r: -r["subscribers"])
    return ranked[:target]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--min-subs", type=int, default=150_000)
    a = ap.parse_args()

    rows = fetch(a.target, a.min_subs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"\nwrote {len(rows)} seeds -> {OUT}")
    print(f"largest : {rows[0]['subreddit']} ({rows[0]['subscribers']:,})")
    print(f"smallest: {rows[-1]['subreddit']} ({rows[-1]['subscribers']:,})")
