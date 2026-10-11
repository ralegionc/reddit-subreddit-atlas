"""Stage 5: render the atlas.

Identity is carried by position and direct labels, not by hue. A scatter form is
gated on all-pairs colour separation, where only three categorical hues clear the
floors, so a 40-colour cluster map would be both unreadable and out of spec.
Colour is therefore spent on a single sequential ramp (community size), and the
regions are named typographically. Per-region detail moves to a facet sheet,
where each panel holds one highlighted series and no colour pair is ever in play.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patheffects as pe
from matplotlib.patches import Polygon
from scipy.spatial import ConvexHull

import palette as P

ROOT = Path(__file__).resolve().parent.parent
ATLAS = ROOT / "data" / "interim" / "atlas.json"
OUTDIR = ROOT / "output"

# Lowest fraction of the sequential ramp to skip so faint marks stay legible.
RAMP_FLOOR = 0.30


ENCODINGS = {
    "authors": ("sampled commenters", "{:,.0f}", 1.0),
    "subscribers": ("subscribers", "{:,.0f}", 1.0),
}


def load_method():
    """Read the pipeline settings the atlas was actually built with, so the
    caption cannot drift from the method (it did: the footer kept crediting PPMI
    for several renders after the build had switched to BM25)."""
    d = json.loads(ATLAS.read_text(encoding="utf-8"))
    m = d.get("method") or {}
    return str(m.get("weight", "bm25")).upper()


def load(encode="authors"):
    """`encode` picks the magnitude channel.

    Sampled commenters is the default rather than subscribers. It is complete for
    every mapped subreddit (subscriber lookups can fail), it measures activity
    rather than dormant sign-ups, and it is the same quantity the position is
    derived from, so the size of a mark and its placement come from one source.
    """
    d = json.loads(ATLAS.read_text(encoding="utf-8"))
    rows = d["subreddits"]
    for r in rows:
        r["size"] = max(r.get(encode) or 0, 1)
    return rows


def name_regions(rows, top_n=3, sfw_labels=True):
    """Name each cluster after its largest members. The region labels are the
    map's legend, so they have to be recognisable at a glance.

    Adult communities form a large, genuinely well-separated region -- that
    separation is a real result and the points stay on the map. But naming the
    region after its three biggest members puts explicit subreddit names in
    display type, so by default such regions get a neutral label instead.
    """
    groups: dict[int, list] = {}
    for r in rows:
        if r["cluster"] >= 0:
            groups.setdefault(r["cluster"], []).append(r)

    named = {}
    for cid, members in groups.items():
        members.sort(key=lambda m: -m["size"])
        head = members[:top_n]
        nsfw_share = sum(bool(m.get("nsfw")) for m in members) / len(members)
        if sfw_labels and nsfw_share >= 0.5:
            label = "adult communities"
        else:
            label = " / ".join(m["name"] for m in head)
        facet_title = (label if (sfw_labels and nsfw_share >= 0.5)
                       else ", ".join("r/" + m["name"] for m in members[:4]))
        named[cid] = {
            "id": cid,
            "label": label,
            "facet_title": facet_title,
            "members": members,
            "n": len(members),
            "nsfw_share": nsfw_share,
            "cx": float(np.mean([m["x"] for m in members])),
            "cy": float(np.mean([m["y"] for m in members])),
            "reach": sum(m["size"] for m in members),
        }
    return named


class LabelPlacer:
    """Greedy label placement with collision rejection, in display space.

    Matplotlib will happily draw every label on top of every other one; on a
    1000-point map that is the difference between a chart and a smear.

    All geometry here is in pixels, not data units. Text can only be measured in
    pixels, and the axes are not square in data terms, so mixing the two scales
    the horizontal and vertical offsets differently -- candidate positions land
    somewhere other than intended and almost everything collides. Working in one
    coordinate system throughout is what makes the hit rate acceptable.

    Candidates are tried on rings of increasing radius. When a label ends up far
    enough from its point to be ambiguous, a leader line is drawn, so a label
    never silently claims the wrong position.
    """

    # Greedy first-fit leaves placements on the table when the candidate set is
    # coarse: a label that misses all 72 offsets is dropped even though a usable
    # gap often exists slightly further out. Widening the search and retrying
    # failures one type size down roughly doubled the hit rate.
    RINGS = (9.0, 14.0, 20.0, 27.0, 35.0, 45.0, 57.0, 72.0, 90.0)
    ANGLES = 16

    def __init__(self, ax, fig, reserved=(), halo=None):
        self.ax = ax
        self.fig = fig
        self.halo = halo
        self.renderer = fig.canvas.get_renderer()
        self.boxes: list[tuple[float, float, float, float]] = list(reserved)
        self.bounds = ax.get_window_extent(renderer=self.renderer)

    def _free(self, box):
        x0, y0, x1, y1 = box
        if (x0 < self.bounds.x0 or x1 > self.bounds.x1
                or y0 < self.bounds.y0 or y1 > self.bounds.y1):
            return False
        for b in self.boxes:
            if not (x1 < b[0] or x0 > b[2] or y1 < b[1] or y0 > b[3]):
                return False
        return True

    def _candidates(self):
        for r in self.RINGS:
            for i in range(self.ANGLES):
                a = (2 * math.pi * i) / self.ANGLES + (math.pi / self.ANGLES)
                yield r, math.cos(a) * r, math.sin(a) * r

    def place(self, x, y, text, fontsize, color, weight="normal",
              pad=2.5, leader_from=24.0, leader_color=None, retry_scale=0.0):
        """Try `fontsize`; if nothing fits and `retry_scale` is set, try once
        more at that fraction of it before giving up."""
        if self._try(x, y, text, fontsize, color, weight, pad, leader_from,
                     leader_color):
            return True
        if retry_scale:
            return self._try(x, y, text, fontsize * retry_scale, color, weight,
                             pad * 0.8, leader_from, leader_color)
        return False

    def _try(self, x, y, text, fontsize, color, weight="normal",
             pad=2.5, leader_from=24.0, leader_color=None):
        px, py = self.ax.transData.transform((x, y))
        probe = self.ax.text(
            x, y, text, fontsize=fontsize, color=color, weight=weight,
            ha="center", va="center", zorder=6,
        )
        if self.halo:
            # A surface-coloured outline behind the glyphs; without it, label
            # text and marks visually merge wherever the map is dense.
            probe.set_path_effects([
                pe.withStroke(linewidth=2.6, foreground=self.halo)
            ])
        bb = probe.get_window_extent(renderer=self.renderer)
        w, h = bb.width + 2 * pad, bb.height + 2 * pad

        for radius, dx, dy in self._candidates():
            # Push horizontally by half the label so wide text clears the mark.
            cx = px + dx * (1.0 + w / (2.0 * max(radius, 1.0)) * 0.55)
            cy = py + dy
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if not self._free(box):
                continue
            self.boxes.append(box)
            data_pos = self.ax.transData.inverted().transform((cx, cy))
            probe.set_position(tuple(data_pos))
            if radius >= leader_from:
                edge = self.ax.transData.inverted().transform(
                    (cx - math.copysign(w / 2 - pad, dx), cy)
                )
                self.ax.plot(
                    [x, edge[0]], [y, edge[1]],
                    color=leader_color or color, linewidth=0.45,
                    alpha=0.5, zorder=5, solid_capstyle="round",
                )
            return True

        probe.remove()
        return False


def _compact(v):
    v = float(v)
    if v >= 1e6:
        return "{:.0f}M".format(v / 1e6)
    if v >= 1e3:
        return "{:.0f}k".format(v / 1e3)
    return "{:.0f}".format(v)


def hero(rows, regions, mode, out, n_labels, title, subtitle,
         max_regions=12, legend_label="sampled commenters", explicit=False,
         top=0, min_conf=0.18, crop=None):
    surface = P.SURFACE_DARK if mode == "dark" else P.SURFACE_LIGHT
    ink = P.INK[mode]
    cmap = P.seq_cmap(mode)

    fig, ax = plt.subplots(figsize=(22, 15), dpi=200)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    # The title and footer live in figure coordinates while labels live in the
    # axes. Rather than reserve boxes for them (which a tight-bbox crop then
    # invalidates, letting labels ride up into the title), the axes is simply
    # inset so those bands are not drawable area at all.
    fig.subplots_adjust(left=0.015, right=0.985, top=0.885, bottom=0.075)

    x = np.array([r["x"] for r in rows])
    y = np.array([r["y"] for r in rows])
    size = np.array([r["size"] for r in rows], dtype=float)
    mag = np.log10(size)
    span = max(float(np.ptp(mag)), 1e-9)
    norm = (mag - mag.min()) / span

    # Region hulls sit well behind the marks.
    for reg in regions.values():
        if reg["n"] < 4:
            continue
        pts = np.array([[m["x"], m["y"]] for m in reg["members"]])
        try:
            hull = ConvexHull(pts)
        except Exception:
            continue
        poly = pts[hull.vertices]
        centre = poly.mean(axis=0)
        poly = centre + (poly - centre) * 1.10  # breathe outward
        ax.add_patch(
            Polygon(poly, closed=True, facecolor=ink["muted"], alpha=0.055,
                    edgecolor=ink["muted"], linewidth=0.7, zorder=1)
        )

    # Marks shrink as the map fills up; a size tuned for 1k points turns 10k
    # into a solid mass with no visible structure.
    # `top` splits the map into a focus layer and a context layer. Positions for
    # both come from the full embedding, so the structure on show is still the
    # one all ~9.6k subreddits produced; the split only governs what is drawn at
    # full weight and what is eligible for a label. A static image cannot label
    # 9.6k points, but silently dropping the rest would also discard the shape
    # they define, so they stay as texture.
    order = np.argsort(-size)
    focus = np.zeros(len(rows), dtype=bool)
    focus[order[: (top if top else len(rows))]] = True

    density = (1000.0 / max(int(focus.sum()), 1)) ** 0.30

    # At ~10k points, sizing every mark comparably turns the core into mud. The
    # map is given depth instead: small communities recede to a faint texture and
    # the large ones sit clearly on top of it, which is also what leaves the
    # label placer usable room in the dense middle.
    marker = 3.0 * density + 620.0 * density * norm ** 2.4

    # The sequential ramp deliberately lets its lowest step recede toward the
    # surface. That is right for magnitude encoding, but on a map every point is
    # a place and must stay visible, so the bottom of the ramp is clipped off.
    shade = RAMP_FLOOR + (1.0 - RAMP_FLOOR) * norm
    rgba = cmap(shade)
    rgba[:, 3] = 0.34 + 0.61 * norm            # depth, not a second encoding

    if not focus.all():
        ctx = ~focus
        ax.scatter(
            x[ctx], y[ctx], s=np.maximum(marker[ctx] * 0.55, 1.6),
            c=ink["muted"], alpha=0.16, linewidths=0, zorder=2,
        )

    # Surface ring only where marks are big enough for it to separate them.
    ring = np.where(norm > 0.45, 0.7, 0.0)
    ax.scatter(
        x[focus], y[focus], s=marker[focus], c=rgba[focus],
        linewidths=ring[focus], edgecolors=surface, zorder=3,
    )

    fig.canvas.draw()

    # Keep labels out of the title block and the footer/legend strip, which are
    # drawn in figure coordinates and so are invisible to the collision test.
    fw, fh = fig.get_size_inches() * fig.dpi
    reserved = [
        (0.0, fh * 0.885, fw * 0.62, fh),          # title + subtitle
        (0.0, 0.0, fw, fh * 0.075),                # footer
        (fw * 0.76, 0.0, fw, fh * 0.115),          # colour ramp legend
    ]
    placer = LabelPlacer(ax, fig, reserved=reserved, halo=surface)

    # Region names claim space before individual subreddits do, so the budget
    # for them is capped: 50-odd region labels would consume the whole canvas
    # and leave no room for the subreddits people actually came to find.
    top_regions = [r for r in sorted(regions.values(), key=lambda r: -r["reach"])
                   if r["n"] >= 5][:max_regions]
    for reg in top_regions:
        placer.place(reg["cx"], reg["cy"], reg["label"].upper(),
                     fontsize=9.0, color=ink["muted"], weight="bold",
                     pad=4.0, leader_from=1e9)

    # Renaming only the region was not enough: with 1,530 adult subreddits on
    # the map, many rank high enough to be labelled individually, which puts the
    # explicit names back on the poster the region rule was meant to keep off.
    focus_rows = [r for r, f in zip(rows, focus) if f]
    labelable = (focus_rows if explicit
                 else [r for r in focus_rows if not r.get("nsfw")])
    # Naming a community asserts it sits where the map puts it. For the weakest
    # placements the bootstrap says that is not supported, so they keep their
    # mark and lose the label rather than implying precision we do not have.
    labelable = [r for r in labelable
                 if (r.get("confidence") is None or r["confidence"] >= min_conf)]
    ranked = sorted(labelable, key=lambda r: -r["size"])[:n_labels]
    placed = sum(
        placer.place(r["x"], r["y"], "r/" + r["name"], fontsize=8.2,
                     color=ink["secondary"], leader_color=ink["muted"],
                     retry_scale=0.85)
        for r in ranked
    )

    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    if crop:
        # Percentile crop: zoom to where the mass actually is. The far islands
        # are real, but on one frame they push the mainland into a smear.
        lo, hi = crop
        x0, x1 = np.percentile(x, lo), np.percentile(x, hi)
        y0, y1 = np.percentile(y, lo), np.percentile(y, hi)
        mx, my = (x1 - x0) * 0.04, (y1 - y0) * 0.04
        ax.set_xlim(x0 - mx, x1 + mx)
        ax.set_ylim(y0 - my, y1 + my)
    else:
        padx, pady = float(np.ptp(x)) * 0.04, float(np.ptp(y)) * 0.04
        ax.set_xlim(x.min() - padx, x.max() + padx)
        ax.set_ylim(y.min() - pady, y.max() + pady)

    fig.text(0.045, 0.955, title, fontsize=27, color=ink["primary"],
             weight="bold", va="top")
    fig.text(0.045, 0.917, subtitle, fontsize=12.5, color=ink["secondary"],
             va="top")
    shown = int(focus.sum())
    scope = ("{:,} subreddits".format(len(rows)) if shown == len(rows) else
             "{:,} largest of {:,} subreddits (rest shown faint)"
             .format(shown, len(rows)))
    footer = (
        "{}  -  position from shared commenters ({}, SVD, UMAP)"
        "  -  point size and colour: {}  -  {} of {} labels placed "
        "without collision"
    ).format(scope, load_method(), legend_label, placed, n_labels)
    fig.text(0.045, 0.032, footer, fontsize=9, color=ink["muted"], va="bottom")

    # The sequential ramp is the only encoded colour, so it gets a real legend.
    cax = fig.add_axes([0.80, 0.055, 0.155, 0.011])
    grad = np.linspace(RAMP_FLOOR, 1, 256).reshape(1, -1)
    cax.imshow(grad, aspect="auto", cmap=cmap, vmin=0.0, vmax=1.0)
    cax.set_xticks([0, 255])
    cax.set_yticks([])
    cax.set_xticklabels([_compact(10 ** mag.min()), _compact(10 ** mag.max())],
                        fontsize=8, color=ink["muted"])
    cax.tick_params(length=0, pad=3)
    for s in cax.spines.values():
        s.set_visible(False)
    cax.set_title(legend_label, fontsize=8, color=ink["muted"], pad=5)

    # No tight bbox: it re-crops after layout and shifts every reserved band.
    fig.savefig(out, facecolor=surface)
    plt.close(fig)
    print("  wrote {}  ({}/{} labels placed)".format(out, placed, n_labels))


def facets(rows, regions, mode, out, cols=4, max_panels=12):
    """One panel per region: a single highlighted series against muted context,
    so no colour pair is ever on screen together."""
    surface = P.SURFACE_DARK if mode == "dark" else P.SURFACE_LIGHT
    ink = P.INK[mode]
    highlight = P.CATEGORICAL[mode][0]

    top = sorted(regions.values(), key=lambda r: -r["reach"])[:max_panels]
    if not top:
        print("  no regions to facet")
        return
    nrows = math.ceil(len(top) / cols)
    fig, axes = plt.subplots(nrows, cols, figsize=(4.2 * cols, 4.0 * nrows),
                             dpi=170)
    fig.patch.set_facecolor(surface)
    axes = np.atleast_1d(axes).ravel()

    x = np.array([r["x"] for r in rows])
    y = np.array([r["y"] for r in rows])

    for ax, reg in zip(axes, top):
        ax.set_facecolor(surface)
        ax.scatter(x, y, s=6, c=ink["muted"], alpha=0.42, linewidths=0, zorder=1)
        mx = [m["x"] for m in reg["members"]]
        my = [m["y"] for m in reg["members"]]
        ms = [18 + 60 * max(math.log10(m["size"]) - 5, 0) for m in reg["members"]]
        ax.scatter(mx, my, s=ms, c=highlight, alpha=0.95, linewidths=0.6,
                   edgecolors=surface, zorder=3)
        ax.set_title("{}\n{} subreddits".format(reg["facet_title"], reg["n"]),
                     fontsize=9, color=ink["secondary"], pad=7, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)

    for ax in axes[len(top):]:
        ax.set_visible(False)

    fig.suptitle("Regions of the map", fontsize=19, color=ink["primary"],
                 weight="bold", x=0.02, ha="left", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.975])
    fig.savefig(out, facecolor=surface, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print("  wrote {}  ({} panels)".format(out, len(top)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dark", "light"], default="dark")
    ap.add_argument("--labels", type=int, default=200)
    ap.add_argument("--max-regions", type=int, default=12,
                    help="how many region names to print")
    ap.add_argument("--explicit-labels", action="store_true",
                    help="name adult regions after their members")
    ap.add_argument("--encode", choices=sorted(ENCODINGS), default="authors",
                    help="magnitude channel for point size and colour")
    ap.add_argument("--crop", type=float, nargs=2, metavar=("LO", "HI"),
                    default=None,
                    help="percentile crop, e.g. --crop 2 98 to zoom the core")
    ap.add_argument("--min-conf", type=float, default=0.18,
                    help="do not label placements weaker than this")
    ap.add_argument("--out-suffix", default="",
                    help="suffix for the output filename")
    ap.add_argument("--top", type=int, default=0,
                    help="draw only the N largest at full weight (0 = all); "
                         "the rest stay as faint context")
    ap.add_argument("--title", default="The Map of Reddit")
    ap.add_argument(
        "--subtitle",
        default="Communities placed by the people they share. "
                "Nothing about topic was supplied.",
    )
    args = ap.parse_args()

    rows = load(args.encode)
    regions = name_regions(rows, sfw_labels=not args.explicit_labels)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print("{} subreddits, {} regions".format(len(rows), len(regions)))
    hero(rows, regions, args.mode,
         OUTDIR / "atlas_{}{}.png".format(args.mode, args.out_suffix),
         args.labels, args.title, args.subtitle, args.max_regions,
         ENCODINGS[args.encode][0], args.explicit_labels, args.top,
         args.min_conf, tuple(args.crop) if args.crop else None)
    if not args.out_suffix:
        facets(rows, regions, args.mode,
               OUTDIR / "atlas_facets_{}.png".format(args.mode))
