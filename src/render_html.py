"""Stage 6: emit a self-contained, zoomable HTML map.

Canvas rather than SVG: a thousand-plus DOM nodes with per-node listeners stutters
badly while panning. Hit testing uses a uniform-grid nearest-point lookup, because
a dense scatter must not demand that the pointer land dead-centre on an 8px dot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import palette as P

ROOT = Path(__file__).resolve().parent.parent
ATLAS = ROOT / "data" / "interim" / "atlas.json"
OUT = ROOT / "output" / "atlas.html"

TEMPLATE = """<title>The Map of Reddit</title>
<style>
  :root {
    color-scheme: light;
    --surface: __SURFACE_LIGHT__;
    --ink-1: __INK1_LIGHT__;
    --ink-2: __INK2_LIGHT__;
    --ink-3: __INK3_LIGHT__;
    --accent: __ACC_LIGHT__;
    --panel: #ffffffee;
    --hair: #00000018;
  }
  :root:not([data-theme="light"]) { }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --surface: __SURFACE_DARK__;
      --ink-1: __INK1_DARK__;
      --ink-2: __INK2_DARK__;
      --ink-3: __INK3_DARK__;
      --accent: __ACC_DARK__;
      --panel: #22221fee;
      --hair: #ffffff1f;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface: __SURFACE_DARK__;
    --ink-1: __INK1_DARK__;
    --ink-2: __INK2_DARK__;
    --ink-3: __INK3_DARK__;
    --accent: __ACC_DARK__;
    --panel: #22221fee;
    --hair: #ffffff1f;
  }

  body {
    background: var(--surface);
    color: var(--ink-1);
    font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
          Helvetica, Arial, sans-serif;
    margin: 0;
    overflow: hidden;
  }
  header {
    position: absolute; top: 0; left: 0; right: 0; padding: 18px 22px 22px;
    pointer-events: none; z-index: 3;
    background: linear-gradient(var(--surface), transparent);
  }
  h1 { margin: 0 0 4px; font-size: 21px; letter-spacing: -0.01em; }
  .sub { margin: 0; color: var(--ink-2); font-size: 12.5px; max-width: 60ch; }
  #wrap { position: fixed; inset: 0; }
  canvas { display: block; width: 100%; height: 100%; cursor: grab;
           touch-action: none; }
  canvas.drag { cursor: grabbing; }

  .controls {
    position: absolute; top: 18px; right: 22px; z-index: 4;
    display: flex; gap: 8px; align-items: center;
  }
  input[type="search"] {
    background: var(--panel); color: var(--ink-1);
    border: 1px solid var(--hair); border-radius: 7px;
    padding: 7px 10px; font: inherit; font-size: 13px; width: 190px;
    outline: none;
  }
  input[type="search"]:focus { border-color: var(--accent); }
  button {
    background: var(--panel); color: var(--ink-2); border: 1px solid var(--hair);
    border-radius: 7px; padding: 7px 11px; font: inherit; font-size: 12.5px;
    cursor: pointer;
  }
  button:hover { color: var(--ink-1); }

  #tip {
    position: absolute; z-index: 5; pointer-events: none; opacity: 0;
    transition: opacity .09s linear;
    background: var(--panel); border: 1px solid var(--hair);
    border-radius: 9px; padding: 9px 11px; min-width: 150px;
    box-shadow: 0 8px 26px #00000038;
    backdrop-filter: blur(7px);
  }
  #tip .n { font-weight: 650; font-size: 13.5px; }
  #tip .r { color: var(--ink-2); font-size: 11.5px; margin-top: 3px; }
  #tip .k { color: var(--ink-3); font-size: 11px; margin-top: 5px;
            border-top: 1px solid var(--hair); padding-top: 5px; }

  #panel {
    position: absolute; top: 62px; right: 22px; z-index: 4; width: 216px;
    background: var(--panel); border: 1px solid var(--hair); border-radius: 10px;
    padding: 12px 13px; box-shadow: 0 10px 30px #00000030;
    backdrop-filter: blur(7px); display: none;
  }
  #panel.on { display: block; }
  #panel h2 { margin: 0 0 2px; font-size: 14px; }
  #panel .meta { color: var(--ink-2); font-size: 11.5px; margin-bottom: 9px; }
  #panel .conf { font-size: 11px; color: var(--ink-3); margin-bottom: 9px; }
  #panel h3 { margin: 0 0 5px; font-size: 10.5px; letter-spacing: .06em;
              text-transform: uppercase; color: var(--ink-3); font-weight: 600; }
  #panel ol { margin: 0; padding: 0; list-style: none; }
  #panel li { margin: 0 0 1px; }
  #panel button.nb {
    background: none; border: 0; padding: 3px 0; font: inherit; font-size: 12px;
    color: var(--accent); cursor: pointer; text-align: left; width: 100%;
  }
  #panel button.nb:hover { text-decoration: underline; }
  #panel .close {
    position: absolute; top: 7px; right: 8px; background: none; border: 0;
    color: var(--ink-3); font-size: 15px; cursor: pointer; padding: 2px 5px;
  }
  footer {
    position: absolute; left: 22px; bottom: 16px; z-index: 3;
    color: var(--ink-3); font-size: 11.5px; max-width: 66ch;
  }
  .ramp { display: flex; align-items: center; gap: 8px; margin-top: 7px; }
  .ramp i { display: block; width: 132px; height: 8px; border-radius: 4px;
            background: linear-gradient(90deg, __RAMP_CSS__); }
  @media (max-width: 720px) {
    .controls { position: static; padding: 10px 22px 0; }
    input[type="search"] { width: 100%; }
    footer { display: none; }
  }
</style>

<div id="wrap"><canvas id="c"></canvas></div>

<header>
  <h1>The Map of Reddit</h1>
  <p class="sub">__SUBTITLE__</p>
</header>

<div class="controls">
  <input id="q" type="search" placeholder="Find a subreddit..." spellcheck="false">
  <button id="reset">Reset view</button>
</div>

<div id="tip"></div>

<div id="panel"><button class="close" id="panelClose" title="Close">&times;</button></div>

<footer>
  <div>__FOOTER__</div>
  <div class="ramp"><span>__LO__</span><i></i><span>__HI__</span>
    <span style="margin-left:4px">sampled commenters</span></div>
</footer>

<script>
const DATA = __DATA__;
const RAMP = __RAMP_JSON__;

const cv = document.getElementById('c');
const ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
const css = getComputedStyle(document.documentElement);
const ink = k => css.getPropertyValue(k).trim();

let W = 0, H = 0, DPR = 1;
let view = {k: 1, x: 0, y: 0};
let hover = null, matches = null, selected = null;
const BY_NAME = new Map();

// Normalise the raw embedding into [0,1] once.
const xs = DATA.map(d => d.x), ys = DATA.map(d => d.y);
const x0 = Math.min(...xs), x1 = Math.max(...xs);
const y0 = Math.min(...ys), y1 = Math.max(...ys);
const mags = DATA.map(d => Math.log10(Math.max(d.authors, 1)));
const m0 = Math.min(...mags), m1 = Math.max(...mags);
DATA.forEach((d, i) => {
  d.nx = (d.x - x0) / (x1 - x0 || 1);
  d.ny = 1 - (d.y - y0) / (y1 - y0 || 1);
  d.t  = (mags[i] - m0) / ((m1 - m0) || 1);
  d.lc = d.name.toLowerCase();
  BY_NAME.set(d.name, d);
});

// Sorted once: label priority never changes, so re-sorting each frame was pure
// waste at this point count.
const RANKED = [...DATA].sort((a, b) => b.t - a.t);

// Per-point constants precomputed once. Recomputing the ramp colour for ~10k
// points every frame was the single biggest cost while panning.
const RAMP_FLOOR = 0.30;
DATA.forEach(d => {
  d.col = rampColor(RAMP_FLOOR + (1 - RAMP_FLOOR) * d.t);
  // Confidence is a bootstrap estimate of how stable this placement is. A
  // weakly-placed subreddit is drawn fainter rather than hidden: it is still a
  // real community, it just should not be read as precisely sited.
  const c = (d.conf === null || d.conf === undefined) ? 1 : d.conf;
  d.trust = Math.max(0, Math.min(1, c / 0.45));
  d.alpha = (0.34 + 0.61 * d.t) * (0.35 + 0.65 * d.trust);
  d.label = 'r/' + d.name;
});

// Uniform spatial grid over normalised coordinates, so hit testing scans a
// handful of nearby points instead of all of them on every mouse move.
const GRID_N = 64;
const GRID = new Map();
const cellKey = (cx, cy) => cx * GRID_N + cy;
DATA.forEach(d => {
  const cx = Math.min(GRID_N - 1, Math.max(0, Math.floor(d.nx * GRID_N)));
  const cy = Math.min(GRID_N - 1, Math.max(0, Math.floor(d.ny * GRID_N)));
  const k = cellKey(cx, cy);
  if (!GRID.has(k)) GRID.set(k, []);
  GRID.get(k).push(d);
});

function lerpHex(a, b, t) {
  const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const [ar, ag, ab] = p(a), [br, bg, bb] = p(b);
  return `rgb(${Math.round(ar + (br - ar) * t)},${Math.round(ag + (bg - ag) * t)},${Math.round(ab + (bb - ab) * t)})`;
}
function rampColor(t) {
  const s = Math.min(Math.max(t, 0), 1) * (RAMP.length - 1);
  const i = Math.floor(s);
  return lerpHex(RAMP[i], RAMP[Math.min(i + 1, RAMP.length - 1)], s - i);
}

function inset() { return Math.min(W, H) * 0.06; }
function px(d) { const p = inset(); return (p + d.nx * (W - 2 * p)) * view.k + view.x; }
function py(d) { const p = inset(); return (p + d.ny * (H - 2 * p)) * view.k + view.y; }
function radius(d) { return (1.5 + 6.6 * Math.pow(d.t, 2.1)) * Math.sqrt(view.k); }

function resize() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  W = cv.clientWidth; H = cv.clientHeight;
  cv.width = W * DPR; cv.height = H * DPR;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  draw();
}

function draw() {
  const surface = ink('--surface');
  ctx.fillStyle = surface;
  ctx.fillRect(0, 0, W, H);

  for (const d of DATA) {
    const X = px(d), Y = py(d), r = radius(d);
    if (X < -40 || X > W + 40 || Y < -40 || Y > H + 40) continue;
    const dim = matches && !matches.has(d.name);
    ctx.globalAlpha = dim ? 0.10 : d.alpha;
    ctx.beginPath();
    ctx.arc(X, Y, r, 0, 6.2832);
    ctx.fillStyle = d.col;
    ctx.fill();
    // Surface ring only on marks big enough for it to separate anything.
    if (r > 3.2) { ctx.lineWidth = 1.2; ctx.strokeStyle = surface; ctx.stroke(); }
  }
  ctx.globalAlpha = 1;

  // Labels only where they fit: biggest first, rejected on collision.
  const boxes = [];
  const zoomBoost = Math.max(0, Math.log2(view.k)) * 0.16;
  const labelInk = ink('--ink-2');
  ctx.font = '600 11.5px ui-sans-serif, system-ui, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (const d of RANKED) {
    if (d.t + zoomBoost < 0.62) {
      if (!matches) break;              // sorted: nothing after this qualifies
      if (!matches.has(d.name)) continue;
    }
    if (matches && !matches.has(d.name)) continue;
    const X = px(d), Y = py(d) - radius(d) - 8;
    if (X < 0 || X > W || Y < 54 || Y > H - 18) continue;
    const w = ctx.measureText(d.label).width + 7, h = 15;
    const b = [X - w / 2, Y - h / 2, X + w / 2, Y + h / 2];
    if (boxes.some(o => !(b[2] < o[0] || b[0] > o[2] || b[3] < o[1] || b[1] > o[3]))) continue;
    boxes.push(b);
    ctx.lineWidth = 3.4; ctx.strokeStyle = surface;
    ctx.strokeText(d.label, X, Y);            // halo for legibility over marks
    ctx.fillStyle = labelInk;
    ctx.fillText(d.label, X, Y);
    if (boxes.length > 420) break;
  }

  if (hover) {
    const X = px(hover), Y = py(hover);
    ctx.beginPath(); ctx.arc(X, Y, radius(hover) + 4, 0, 6.2832);
    ctx.lineWidth = 2; ctx.strokeStyle = ink('--accent'); ctx.stroke();
  }
  if (selected) {
    const X = px(selected), Y = py(selected);
    ctx.beginPath(); ctx.arc(X, Y, radius(selected) + 7, 0, 6.2832);
    ctx.lineWidth = 2.2; ctx.strokeStyle = ink('--accent'); ctx.stroke();
    // Ring the selected community's nearest neighbours too, so the panel's
    // answer is visible on the map rather than only in a list.
    ctx.lineWidth = 1.3; ctx.setLineDash([3, 3]);
    for (const i of (selected.near || [])) {
      const d = DATA[i]; if (!d) continue;
      ctx.beginPath(); ctx.arc(px(d), py(d), radius(d) + 5, 0, 6.2832); ctx.stroke();
    }
    ctx.setLineDash([]);
  }
}

// Nearest-point picking within a generous radius, so dense areas stay usable.
function pick(mx, my) {
  const p = inset(), spanX = (W - 2 * p) * view.k, spanY = (H - 2 * p) * view.k;
  if (spanX <= 0 || spanY <= 0) return null;
  const TOL = 26;                                   // px; larger than any mark
  const nx = (mx - view.x - p * view.k) / spanX;
  const ny = (my - view.y - p * view.k) / spanY;
  const rx = Math.ceil((TOL / spanX) * GRID_N), ry = Math.ceil((TOL / spanY) * GRID_N);
  const cx = Math.floor(nx * GRID_N), cy = Math.floor(ny * GRID_N);

  let best = null, bestScore = TOL * TOL;
  for (let i = cx - rx; i <= cx + rx; i++) {
    if (i < 0 || i >= GRID_N) continue;
    for (let j = cy - ry; j <= cy + ry; j++) {
      if (j < 0 || j >= GRID_N) continue;
      const bucket = GRID.get(cellKey(i, j));
      if (!bucket) continue;
      for (const d of bucket) {
        const ddx = px(d) - mx, ddy = py(d) - my;
        // Distance to the mark's edge, so a big mark wins over a far small one.
        const score = ddx * ddx + ddy * ddy - radius(d) * radius(d);
        if (score < bestScore) { bestScore = score; best = d; }
      }
    }
  }
  return best;
}

function confWord(c) {
  if (c >= 0.45) return 'well constrained';
  if (c >= 0.30) return 'moderate';
  if (c >= 0.18) return 'weak';
  return 'very weak';
}

// ---- selection panel -------------------------------------------------------
const panel = document.getElementById('panel');
function select(d, recentre) {
  selected = d;
  if (!d) { panel.classList.remove('on'); draw(); writeHash(); return; }
  if (recentre) {
    const p = inset();
    view.x = W / 2 - (p + d.nx * (W - 2 * p)) * view.k;
    view.y = H / 2 - (p + d.ny * (H - 2 * p)) * view.k;
  }
  const subs = d.subscribers > 0
    ? Number(d.subscribers).toLocaleString() + ' subscribers' : 'subscribers unknown';
  const near = (d.near || []).map(i => DATA[i]).filter(Boolean);
  panel.innerHTML =
    '<button class="close" id="panelClose" title="Close">&times;</button>' +
    '<h2>r/' + d.name + '</h2>' +
    '<div class="meta">' + Number(d.authors).toLocaleString() +
      ' sampled commenters<br>' + subs + '</div>' +
    ((d.conf === null || d.conf === undefined) ? '' :
      '<div class="conf">placement ' + confWord(d.conf) +
      ' (' + d.conf.toFixed(2) + ')</div>') +
    (near.length
      ? '<h3>Nearest communities</h3><ol>' + near.map(nd =>
          '<li><button class="nb" data-n="' + nd.name + '">r/' + nd.name + '</button></li>').join('') + '</ol>'
      : '');
  panel.classList.add('on');
  panel.querySelector('#panelClose').onclick = () => select(null);
  panel.querySelectorAll('button.nb').forEach(b => {
    b.onclick = () => select(BY_NAME.get(b.dataset.n), true);
  });
  draw();
  writeHash();
}

// ---- deep linking ----------------------------------------------------------
let hashTimer = null;
function writeHash() {
  clearTimeout(hashTimer);
  hashTimer = setTimeout(() => {
    const p = new URLSearchParams();
    p.set('k', view.k.toFixed(3));
    p.set('x', Math.round(view.x));
    p.set('y', Math.round(view.y));
    const q = document.getElementById('q').value.trim();
    if (q) p.set('q', q);
    if (selected) p.set('sel', selected.name);
    history.replaceState(null, '', '#' + p.toString());
  }, 220);
}
function readHash() {
  if (!location.hash.length) return;
  const p = new URLSearchParams(location.hash.slice(1));
  const k = parseFloat(p.get('k')), x = parseFloat(p.get('x')), y = parseFloat(p.get('y'));
  if (isFinite(k) && isFinite(x) && isFinite(y)) view = {k, x, y};
  const q = p.get('q');
  if (q) {
    document.getElementById('q').value = q;
    matches = new Set(DATA.filter(d => d.lc.includes(q.toLowerCase())).map(d => d.name));
  }
  const sel = p.get('sel');
  if (sel && BY_NAME.has(sel)) select(BY_NAME.get(sel), false);
}

// ---- touch: one finger pans, two fingers pinch ------------------------------
// Without these the map is inert on a phone; pointer events alone do not give
// pinch, and the wheel handler never fires on touch.
let touch = null;
const dist = t => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
const mid = t => [(t[0].clientX + t[1].clientX) / 2, (t[0].clientY + t[1].clientY) / 2];

cv.addEventListener('touchstart', e => {
  const t = e.touches;
  if (t.length === 1) {
    touch = {mode: 'pan', x: t[0].clientX, y: t[0].clientY, vx: view.x, vy: view.y};
  } else if (t.length === 2) {
    const [mx, my] = mid(t);
    touch = {mode: 'pinch', d0: dist(t), k0: view.k, mx, my, vx: view.x, vy: view.y};
  }
}, {passive: true});

cv.addEventListener('touchmove', e => {
  if (!touch) return;
  e.preventDefault();
  const t = e.touches, r = cv.getBoundingClientRect();
  if (touch.mode === 'pan' && t.length === 1) {
    view.x = touch.vx + (t[0].clientX - touch.x);
    view.y = touch.vy + (t[0].clientY - touch.y);
  } else if (touch.mode === 'pinch' && t.length === 2) {
    const k = Math.min(Math.max(touch.k0 * (dist(t) / touch.d0), 0.6), 26);
    const s = k / touch.k0;
    const ax = touch.mx - r.left, ay = touch.my - r.top;
    view.x = ax - (ax - touch.vx) * s;
    view.y = ay - (ay - touch.vy) * s;
    view.k = k;
  }
  draw();
}, {passive: false});

cv.addEventListener('touchend', e => {
  if (touch && touch.mode === 'pan' && e.changedTouches.length === 1) {
    const moved = Math.hypot(view.x - touch.vx, view.y - touch.vy);
    if (moved < 6) {                                  // a tap, not a drag
      const r = cv.getBoundingClientRect();
      const hit = pick(e.changedTouches[0].clientX - r.left,
                       e.changedTouches[0].clientY - r.top);
      if (hit) select(hit, false);
    }
  }
  touch = null;
  writeHash();
}, {passive: true});

let drag = null;
let drag0 = null;
cv.addEventListener('mousedown', e => {
  drag0 = {x: e.clientX, y: e.clientY};
  drag = {x: e.clientX, y: e.clientY, vx: view.x, vy: view.y};
  cv.classList.add('drag');
});
addEventListener('mouseup', () => { drag = null; cv.classList.remove('drag'); });
cv.addEventListener('click', e => {
  const r = cv.getBoundingClientRect();
  if (drag0 && Math.hypot(e.clientX - drag0.x, e.clientY - drag0.y) > 5) return;
  select(pick(e.clientX - r.left, e.clientY - r.top), false);
});
cv.addEventListener('mousemove', e => {
  const r = cv.getBoundingClientRect();
  if (drag) {
    view.x = drag.vx + (e.clientX - drag.x);
    view.y = drag.vy + (e.clientY - drag.y);
    tip.style.opacity = 0; hover = null;
    draw();
    writeHash();
    return;
  }
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const hit = pick(mx, my);
  if (hit !== hover) { hover = hit; draw(); }
  if (hit) {
    const subsLine = hit.subscribers > 0
      ? Number(hit.subscribers).toLocaleString() + ' subscribers'
      : 'subscriber count unavailable';
    const confLine = (hit.conf === null || hit.conf === undefined)
      ? '' : ' - placement ' + confWord(hit.conf);
    tip.innerHTML =
      '<div class="n">r/' + hit.name + '</div>' +
      '<div class="r">' + Number(hit.authors).toLocaleString() + ' sampled commenters</div>' +
      '<div class="k">' + subsLine + confLine + '</div>';
    tip.style.opacity = 1;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(mx + 16, W - tw - 10) + 'px';
    tip.style.top = Math.max(my - th - 12, 8) + 'px';
  } else {
    tip.style.opacity = 0;
  }
});
cv.addEventListener('mouseleave', () => {
  tip.style.opacity = 0; hover = null; draw();
});

cv.addEventListener('wheel', e => {
  e.preventDefault();
  const r = cv.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const f = Math.exp(-e.deltaY * 0.0016);
  const k = Math.min(Math.max(view.k * f, 0.6), 26);
  const s = k / view.k;
  view.x = mx - (mx - view.x) * s;
  view.y = my - (my - view.y) * s;
  view.k = k;
  draw();
  writeHash();
}, {passive: false});

document.getElementById('q').addEventListener('input', e => {
  const v = e.target.value.trim().toLowerCase();
  matches = v ? new Set(DATA.filter(d => d.lc.includes(v)).map(d => d.name)) : null;
  if (matches && matches.size === 0) matches = new Set();
  draw();
  writeHash();
});
document.getElementById('reset').addEventListener('click', () => {
  view = {k: 1, x: 0, y: 0};
  document.getElementById('q').value = '';
  matches = null;
  select(null);
  draw();
});

addEventListener('resize', resize);
addEventListener('hashchange', () => { readHash(); draw(); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => draw());
readHash();
resize();
</script>
"""


def main(subtitle: str) -> None:
    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    rows = atlas["subreddits"]
    # Neighbours ship as indices, not names: 9,587 x 8 repeated strings was
    # ~1.3 MB of the payload. Safe here because both sides are built from this
    # same ordered list in this same function.
    order = {r["name"]: i for i, r in enumerate(rows)}
    slim = [
        {
            "name": r["name"],
            "x": round(r["x"], 4),
            "y": round(r["y"], 4),
            "cluster": r["cluster"],
            "authors": r["authors"],
            "subscribers": r["subscribers"],
            "conf": r.get("confidence"),
            "near": [order[n] for n in (r.get("near") or []) if n in order],
        }
        for r in rows
    ]
    ramp = P.SEQ_BLUE[::-1]  # dark surface: near-zero recedes toward the surface
    subs = [r["authors"] for r in rows]

    footer = (
        "{:,} subreddits positioned only by which people comment in them "
        "(BM25, SVD, UMAP). Scroll or pinch to zoom, drag to pan, click a "
        "community for its nearest neighbours. Topic was never supplied."
    ).format(len(rows))

    html = (
        TEMPLATE
        .replace("__SURFACE_LIGHT__", P.SURFACE_LIGHT)
        .replace("__SURFACE_DARK__", P.SURFACE_DARK)
        .replace("__INK1_LIGHT__", P.INK["light"]["primary"])
        .replace("__INK2_LIGHT__", P.INK["light"]["secondary"])
        .replace("__INK3_LIGHT__", P.INK["light"]["muted"])
        .replace("__INK1_DARK__", P.INK["dark"]["primary"])
        .replace("__INK2_DARK__", P.INK["dark"]["secondary"])
        .replace("__INK3_DARK__", P.INK["dark"]["muted"])
        .replace("__ACC_LIGHT__", P.CATEGORICAL["light"][0])
        .replace("__ACC_DARK__", P.CATEGORICAL["dark"][0])
        .replace("__RAMP_CSS__", ", ".join(ramp))
        .replace("__RAMP_JSON__", json.dumps(ramp))
        .replace("__SUBTITLE__", subtitle)
        .replace("__FOOTER__", footer)
        .replace("__LO__", "{:,}".format(min(subs)))
        .replace("__HI__", "{:,}".format(max(subs)))
        .replace("__DATA__", json.dumps(slim, separators=(",", ":")))
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print("  wrote {}  ({:.0f} KB, {} points)".format(OUT, kb, len(slim)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--subtitle",
        default="Communities placed by the people they share. "
                "Nothing about topic was supplied.",
    )
    main(ap.parse_args().subtitle)
