"""Stage 8b: render what moved between the two periods.

Deliberately NOT arrows on the map. The obvious temporal visual is a quiver plot
of each subreddit's period-one position to its period-two position, and it would
be a lie here: the correlation between a subreddit's real drift and its 2-d
displacement is 0.041. Both period-rows of a subreddit are near-identical, so
UMAP drops them almost on top of each other and whatever separation remains is
projection jitter, uncorrelated with what actually changed.

So change is shown where it is real: in the neighbourhood. A ranked chart of how
far each community moved in units of its own sampling noise, annotated with the
communities it moved toward, plus a scatter of drift against that noise floor so
the threshold is visible rather than asserted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import palette as P

ROOT = Path(__file__).resolve().parent.parent
TEMPORAL = ROOT / "data" / "interim" / "temporal.json"
META = ROOT / "data" / "raw" / "subreddit_meta.jsonl"
OUTDIR = ROOT / "output"


def nsfw_set() -> set[str]:
    """Adult subreddits, so this chart can hold to the same naming rule as the
    posters. A ranked list of names is exactly the place that rule matters."""
    out: set[str] = set()
    if META.exists():
        with META.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if m.get("over18"):
                    out.add(m["subreddit"])
    return out


def movers_chart(d, rows, mode, out, top, gained):
    surface = P.SURFACE_DARK if mode == "dark" else P.SURFACE_LIGHT
    ink = P.INK[mode]
    hue = P.CATEGORICAL[mode][0]

    rows = sorted(rows, key=lambda r: -r["score"])[:top][::-1]
    names = ["r/" + r["name"] for r in rows]
    vals = [r["score"] for r in rows]

    fig, ax = plt.subplots(figsize=(15, 0.42 * len(rows) + 2.6), dpi=200)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)

    y = np.arange(len(rows))
    # Thin marks, rounded data-ends, anchored at the baseline.
    ax.barh(y, vals, height=0.52, color=hue, zorder=3,
            linewidth=0, joinstyle="round")
    for yi, v, r in zip(y, vals, rows):
        note = gained.get(r["name"], "")
        ax.text(v + max(vals) * 0.012, yi, f"{v:.0f}x", va="center",
                fontsize=8.5, color=ink["primary"], zorder=4)
        if note:
            ax.text(v + max(vals) * 0.055, yi, note, va="center",
                    fontsize=8, color=ink["muted"], zorder=4)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9, color=ink["secondary"])
    ax.set_xlabel("movement, in multiples of that community's own sampling noise",
                  fontsize=9, color=ink["muted"], labelpad=9)
    ax.tick_params(axis="x", labelsize=8, colors=ink["muted"], length=0)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(vals) * 1.55)
    ax.grid(axis="x", color=ink["muted"], alpha=0.14, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)

    p0, p1 = d["periods"][0], d["periods"][-1]
    fig.suptitle("Which communities changed company", fontsize=18,
                 color=ink["primary"], weight="bold", x=0.012, ha="left", y=0.995)
    fig.text(0.012, 0.963, textwrap.fill(
                 f"Shift in who comments where, {p0} to {p1}. Bars show "
                 f"movement relative to each community's own sampling noise, "
                 f"so a thinly sampled subreddit is not flattered.", 120),
             fontsize=10, color=ink["secondary"], ha="left", va="top")
    fig.tight_layout(rect=[0, 0.005, 1, 0.945])
    fig.savefig(out, facecolor=surface)
    plt.close(fig)
    print(f"  wrote {out}")


def floor_scatter(d, rows, mode, out):
    surface = P.SURFACE_DARK if mode == "dark" else P.SURFACE_LIGHT
    ink = P.INK[mode]
    hue = P.CATEGORICAL[mode][0]
    thr = d["threshold"]

    drift = np.array([r["drift"] for r in rows])
    floor = np.array([r["drift"] / max(r["score"], 1e-9) for r in rows])
    moved = np.array([r["moved"] for r in rows])

    fig, ax = plt.subplots(figsize=(11, 8), dpi=200)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)

    ax.scatter(floor[~moved], drift[~moved], s=7, c=ink["muted"], alpha=0.30,
               linewidths=0, zorder=2, label="within sampling noise")
    ax.scatter(floor[moved], drift[moved], s=9, c=hue, alpha=0.62,
               linewidths=0, zorder=3, label=f"moved >= {thr:g}x noise")

    lim = float(np.percentile(np.concatenate([floor, drift]), 99.5))
    xs = np.linspace(0, lim, 50)
    ax.plot(xs, xs, color=ink["muted"], lw=1, ls="--", alpha=0.55, zorder=4)
    ax.plot(xs, thr * xs, color=ink["primary"], lw=1.1, alpha=0.65, zorder=4)
    ax.text(lim * 0.70, lim * 0.72, "no change", fontsize=8.5,
            color=ink["muted"], rotation=34)
    ax.text(lim * 0.40, lim * 0.86, f"{thr:g}x noise", fontsize=8.5,
            color=ink["secondary"], rotation=52)

    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("sampling noise floor for that community", fontsize=9.5,
                  color=ink["muted"], labelpad=8)
    ax.set_ylabel("observed drift between periods", fontsize=9.5,
                  color=ink["muted"], labelpad=8)
    ax.tick_params(labelsize=8, colors=ink["muted"], length=0)
    ax.grid(color=ink["muted"], alpha=0.12, linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    leg = ax.legend(frameon=False, fontsize=9, loc="lower right")
    for t in leg.get_texts():
        t.set_color(ink["secondary"])

    fig.suptitle("Real change against the noise it has to beat", fontsize=16,
                 color=ink["primary"], weight="bold", x=0.02, ha="left", y=0.985)
    # Wrapped explicitly: figure-coordinate text does not reflow, and this line
    # was running off the right edge.
    fig.text(0.02, 0.925, textwrap.fill(
                 f"{d['n_moved']:,} of {len(rows):,} communities cleared the "
                 f"threshold. Each floor is measured per community by "
                 f"resplitting its own comments, so thin sampling cannot "
                 f"masquerade as change.", 96),
             fontsize=9.5, color=ink["secondary"], ha="left", va="top")
    fig.tight_layout(rect=[0, 0, 1, 0.885])
    fig.savefig(out, facecolor=surface)
    plt.close(fig)
    print(f"  wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dark", "light"], default="dark")
    ap.add_argument("--top", type=int, default=26)
    ap.add_argument("--gained", default="",
                    help="optional JSON file of {subreddit: note}")
    ap.add_argument("--explicit", action="store_true",
                    help="include adult communities in the named ranking")
    a = ap.parse_args()

    d = json.loads(TEMPORAL.read_text(encoding="utf-8"))
    rows = d["subreddits"]
    # The scatter keeps every community (it names none of them); only the ranked
    # chart, which prints names and their new neighbours, is filtered.
    adult = set() if a.explicit else nsfw_set()
    named = [r for r in rows if r["name"] not in adult]
    dropped = len(rows) - len(named)
    # Annotations come from the build itself, filtered to the same naming rule
    # the ranking uses. Previously these lived in a hand-made side-car file,
    # which meant the chart silently lost them whenever that file was not around.
    gained = {}
    for name, gs in (d.get("gained") or {}).items():
        keep = [g for g in gs if g not in adult][:2]
        if keep:
            gained[name] = "-> " + ", ".join("r/" + g for g in keep)
    if a.gained and Path(a.gained).exists():
        gained.update(json.loads(Path(a.gained).read_text(encoding="utf-8")))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"{len(rows):,} comparable subreddits, {d['n_moved']:,} moved")
    if dropped:
        print(f"  {dropped:,} adult communities excluded from the named ranking")
    movers_chart(d, named, a.mode, OUTDIR / f"temporal_movers_{a.mode}.png",
                 a.top, gained)
    floor_scatter(d, rows, a.mode, OUTDIR / f"temporal_floor_{a.mode}.png")
