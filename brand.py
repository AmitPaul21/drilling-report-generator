"""Belloy brand palette and small helpers shared by the PDF and the on-screen overview."""
from __future__ import annotations

import functools
from pathlib import Path

import numpy as np

# ---- brand colours (Belloy blue comes from the logo artwork)
NAVY = '#0f2c4c'          # titles, headline numbers
BRAND = '#255f93'         # Belloy blue - accents, eyebrow, links
BRAND_TINT = '#eaf1f8'    # tiles, table header
BRAND_LINE = '#c9d9ea'    # rules on tinted areas
INK = '#1a2733'
INK2 = '#4a5866'
MUTED = '#7d8a97'
GRID = '#e6ebf0'
BAR = '#c7daee'           # daily-metres bars
BAR_TEXT = '#255f93'
NEUTRAL = '#9aa7b4'       # surface / build section
# leg colours - start with Belloy blue; order checked for colour-blind separation
LEG_COLORS = ['#255f93', '#e07b39', '#0f9f8a', '#c9a227', '#8e5ba8', '#c2185b', '#5b8c3a', '#4ba3d9']

COMPANY = 'Belloy Petroleum Consulting LTD.'
FOOTER = f'Created by {COMPANY}'
LOGO_FILES = ('Logo_Belloy_Blue.psd', 'belloy_logo.png')


def leg_color(n: int) -> str:
    return LEG_COLORS[(n - 1) % len(LEG_COLORS)]


def section_color(name: str) -> str:
    return leg_color(int(name.split()[1])) if name.startswith('Leg') else NEUTRAL


@functools.lru_cache(maxsize=1)
def load_logo():
    """Logo as an RGBA uint8 array (cropped, white background made transparent), or None."""
    try:
        from PIL import Image
        here = Path(__file__).resolve().parent
        files = [here / n for n in LOGO_FILES if (here / n).exists()]
        if not files:
            return None
        a = np.asarray(Image.open(files[0]).convert('RGBA')).astype(float)
        rgb = a[..., :3] * (a[..., 3:] / 255) + 255 * (1 - a[..., 3:] / 255)   # flatten on white
        ink = rgb.min(axis=2) < 235
        ys, xs = np.where(ink)
        rgb = rgb[max(ys.min() - 4, 0):ys.max() + 5, max(xs.min() - 4, 0):xs.max() + 5]
        dark = rgb[rgb.min(axis=2) < 140]
        colour = np.median(dark, axis=0) if len(dark) else np.array([37, 95, 147], float)
        alpha = np.clip((255 - rgb.min(axis=2)) / max(1.0, 255 - colour.min()), 0, 1)
        out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
        out[..., :3] = colour.round()
        out[..., 3] = (alpha * 255).round()
        return out
    except Exception:  # noqa: BLE001 - logo is decoration
        return None


def logo_png_bytes() -> bytes | None:
    arr = load_logo()
    if arr is None:
        return None
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr, 'RGBA').save(buf, 'PNG')
    return buf.getvalue()


def pchip(xs, ys, n=24):
    """Monotone cubic (Fritsch-Carlson) through the points: smooth and never overshoots the data."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < 3:
        return xs, ys
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    m[0], m[-1] = d[0], d[-1]
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    px, py = [], []
    for k in range(len(xs) - 1):
        t = np.linspace(0, 1, n, endpoint=k == len(xs) - 2)
        h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
        h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
        px.append(xs[k] + t * h[k])
        py.append(h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1])
    return np.concatenate(px), np.concatenate(py)


def runs(values):
    """Index runs of consecutive non-NaN values."""
    out, cur = [], []
    for i, v in enumerate(values):
        if v is not None and not np.isnan(v):
            cur.append(i)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def label_offsets(points, min_gap):
    """points: [(x_key, y, text, color)]. Puts each value label above its point; when two points on
    the same day are closer than min_gap, the lower label goes underneath its point instead."""
    by_x = {}
    for p in points:
        by_x.setdefault(p[0], []).append(p)
    out = []
    for pts in by_x.values():
        pts = sorted(pts, key=lambda p: p[1])
        placed = []
        for p in pts:
            if placed and abs(p[1] - placed[-1][1]) < min_gap:
                placed[-1] = (*placed[-1][:4], 'below')
            placed.append((*p, 'above'))
        out += placed
    return out
