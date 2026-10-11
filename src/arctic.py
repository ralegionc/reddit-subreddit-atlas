"""Arctic Shift API client: retrying, rate-limit aware, thread-pooled."""
from __future__ import annotations

import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = "https://arctic-shift.photon-reddit.com/api"
MAX_LIMIT = 100          # hard server cap
WORKERS = int(os.environ.get("ATLAS_WORKERS", "12"))  # 16 measured safe (~13 req/s)
TIMEOUT = 40

_local = threading.local()


def _session() -> requests.Session:
    """One Session per thread so connection pools are not shared across threads."""
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = "subreddit-atlas/1.0 (research; contact via github)"
        _local.s = s
    return s


def get(path: str, params: dict, retries: int = 5) -> list[dict]:
    """GET one page. Returns the `data` list, or [] if the server has nothing.

    The API answers over-broad queries with HTTP 200 and {"data": null,
    "error": "Timeout. Maybe slow down a bit"}, so a 200 is not sufficient
    evidence of success -- the body has to be inspected too.
    """
    for attempt in range(retries):
        try:
            r = _session().get(f"{BASE}/{path}", params=params, timeout=TIMEOUT)
            if r.status_code == 429:
                time.sleep(2 ** attempt + random.random())
                continue
            r.raise_for_status()
            body = r.json()
            data = body.get("data")
            if data is None:
                # Server-side timeout on a too-expensive query: back off and retry.
                time.sleep(1.5 * (attempt + 1) + random.random())
                continue
            return data
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                return []
            time.sleep(1.5 * (attempt + 1) + random.random())
    return []


def imap(fn, jobs, workers: int = WORKERS, desc: str = ""):
    """Run fn over jobs in a thread pool, yielding (job, result) as they land."""
    total = len(jobs)
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futures = {ex.submit(fn, j): j for j in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            done += 1
            if desc and (done % 25 == 0 or done == total):
                rate = done / max(time.time() - t0, 1e-9)
                eta = (total - done) / max(rate, 1e-9)
                print(
                    f"  {desc}: {done}/{total}  {rate:.1f}/s  eta {eta/60:.1f}m",
                    flush=True,
                )
            try:
                yield job, fut.result()
            except Exception as e:  # noqa: BLE001 - one bad job must not kill the run
                print(f"  ! {job}: {type(e).__name__}: {e}", flush=True)
                yield job, None
