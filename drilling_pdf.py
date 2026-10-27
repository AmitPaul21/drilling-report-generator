"""One-page (US Letter) Drilling Operations Report PDF - modern layout.

Header with the well as the headline, a KPI strip, measured depth by leg, daily metres and
time by section side by side, and a leg summary table. Each chart has a single y-scale."""
from __future__ import annotations

import functools
import io
import math
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator  # noqa: E402

plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 7.5, 'axes.titlesize': 9,
    'axes.edgecolor': '#c9c8c2', 'axes.linewidth': 0.6, 'xtick.color': '#6b6a65',
    'ytick.color': '#6b6a65', 'xtick.major.size': 0, 'ytick.major.size': 0,
    'pdf.fonttype': 42,
})

INK = '#0b0b0b'
INK2 = '#52514e'
MUTED = '#8a8984'
GRID = '#ebeae6'
CARD = '#f5f4f1'
ACCENT = '#2a78d6'
BAR = '#6da7ec'
BAR_SOFT = '#cfe0f6'
BAR_TEXT = '#3d6fa8'
NEUTRAL = '#a3a29c'
# validated categorical order - colour follows the leg number
LEG_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']

PAGE_W, PAGE_H = 8.5, 11.0
LOGO_URL = 'https://belloygeologists.ca/wp-content/uploads/2022/09/Belloy-Geologists-Logo-1.png'
LOGO_FILES = ('Logo_Belloy_Blue.psd', 'belloy_logo.png')       # logo files in the repo
LOGO_COLOR = (14, 58, 87)                                           # Belloy navy
M = 0.55                                   # page margin (in)
CW = PAGE_W - 2 * M                        # content width


@functools.lru_cache(maxsize=1)
def load_logo():
    """Belloy logo as an RGBA array, or None.

    Looks for Logo_Belloy_Blue.psd / belloy_logo.png next to this file (falls back to the website).
    The artwork is cropped to the logo and its white background made transparent."""
    try:
        from PIL import Image
        here = Path(__file__).resolve().parent
        local = [here / n for n in LOGO_FILES if (here / n).exists()]
        if local:
            img = Image.open(local[0])
        else:
            req = urllib.request.Request(LOGO_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as r:
                img = Image.open(io.BytesIO(r.read()))
        a = np.asarray(img.convert('RGBA')).astype(float)
        rgb = a[..., :3] * (a[..., 3:] / 255) + 255 * (1 - a[..., 3:] / 255)   # flatten on white
        ink = rgb.min(axis=2) < 235
        if not ink.any():                                    # white logo (website) -> navy
            rgb = 255 - a[..., 3:].repeat(3, axis=2) * (1 - np.array(LOGO_COLOR) / 255)
            ink = a[..., 3] > 20
        ys, xs = np.where(ink)
        rgb = rgb[max(ys.min() - 4, 0):ys.max() + 5, max(xs.min() - 4, 0):xs.max() + 5]
        dark = rgb[rgb.min(axis=2) < 140]
        colour = np.median(dark, axis=0) if len(dark) else np.array(LOGO_COLOR, float)
        alpha = np.clip((255 - rgb.min(axis=2)) / max(1.0, 255 - colour.min()), 0, 1)
        out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
        out[..., :3] = colour.round()
        out[..., 3] = (alpha * 255).round()
        return out
    except Exception:  # noqa: BLE001 - logo is decoration; never fail the report
        return None


def leg_color(n: int) -> str:
    return LEG_COLORS[(n - 1) % len(LEG_COLORS)]


def _ax(fig, x, y, w, h, **kw):
    """Axes placed in inches from the page's top-left corner."""
    return fig.add_axes([x / PAGE_W, 1 - (y + h) / PAGE_H, w / PAGE_W, h / PAGE_H], **kw)


def _canvas(fig, x, y, w, h):
    ax = _ax(fig, x, y, w, h)
    ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.axis('off')   # inch units, y downwards
    return ax


def _dt(v, fmt='%d %b %Y, %H:%M'):
    return '—' if v is None or pd.isna(v) else pd.Timestamp(v).strftime(fmt)


def _style(ax, ygrid=True):
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color('#c9c8c2')
    if ygrid:
        ax.grid(axis='y', color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=6.5, pad=3)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))


def _section_title(fig, x, y, title, sub=None):
    c = _canvas(fig, x, y, 4, 0.34)
    c.text(0, 0.12, title, fontsize=9.5, fontweight='bold', color=INK, va='center')
    if sub:
        c.text(0, 0.29, sub, fontsize=6.5, color=MUTED, va='center')


# ---------------------------------------------------------------- blocks
def _header(fig, rep):
    w = rep.well
    c = _canvas(fig, M, 0.45, CW, 1.1)
    logo = load_logo()
    x_eyebrow = 0
    if logo is not None:
        lh = 0.32                                   # logo height (in)
        lw = lh * logo.shape[1] / logo.shape[0]
        lax = _ax(fig, M, 0.45, lw, lh)
        lax.imshow(logo, interpolation='lanczos'); lax.axis('off')
        c.plot([lw + 0.15, lw + 0.15], [0.04, 0.28], color='#d6d5d0', linewidth=0.8)
        x_eyebrow = lw + 0.3
    else:
        c.add_patch(Rectangle((0, 0.1), 0.5, 0.05, color=ACCENT))
        x_eyebrow = 0.65
    c.text(x_eyebrow, 0.16, 'DRILLING OPERATIONS REPORT', fontsize=7, color=ACCENT, fontweight='bold',
           va='center')
    # spud / TD on the right of the top row
    for i, (lab, val) in enumerate((('SPUD', rep.milestones.get('Spud')),
                                    ('TOTAL DEPTH', rep.milestones.get('Total Depth')))):
        x = CW - (1 - i) * 1.5 - 1.45
        c.text(x, 0.06, lab, fontsize=5.8, color=MUTED, fontweight='bold', va='center')
        c.text(x, 0.24, _dt(val), fontsize=7.5, color=INK, va='center')
    c.text(0, 0.6, w.get('Well Name') or 'Unnamed well', fontsize=17, fontweight='bold', color=INK,
           va='center')
    sub = '   \u00b7   '.join(v for v in (w.get('Licensee'), w.get('UWI'), w.get('Surface Location')) if v)
    c.text(0, 0.84, sub, fontsize=7.5, color=INK2, va='center')
    c.plot([0, CW], [1.02, 1.02], color='#e2e1dc', linewidth=0.8)


def _kpis(fig, rep):
    k = rep.kpis
    tiles = [('Total horizontal', f"{k['total_hz_m']:,.0f}", 'm'),
             ('Legs drilled', f"{k['legs_drilled']}", ''),
             ('Operational days', f"{k['operational_days']}", 'days'),
             ('Drilling days', f"{k['drilling_days']}", 'days'),
             ('Non-drilling days', f"{k['non_drilling_days']}", 'days'),
             ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day')]
    gap = 0.1
    tw = (CW - gap * (len(tiles) - 1)) / len(tiles)
    c = _canvas(fig, M, 1.66, CW, 0.82)
    for i, (lab, val, unit) in enumerate(tiles):
        x = i * (tw + gap)
        c.add_patch(FancyBboxPatch((x, 0), tw, 0.8, boxstyle='round,pad=0,rounding_size=0.06',
                                   facecolor=CARD, edgecolor='none'))
        c.text(x + 0.12, 0.2, lab.upper(), fontsize=5.2, color=MUTED, fontweight='bold', va='center')
        t = c.text(x + 0.12, 0.52, val, fontsize=15, color=INK, fontweight='bold', va='center')
        if unit:
            fig.canvas.draw() if not hasattr(fig, '_drawn') else None
            fig._drawn = True
            bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
            wid = bb.width / fig.dpi
            c.text(x + 0.12 + wid + 0.05, 0.56, unit, fontsize=6.5, color=INK2, va='center')


def _pchip(xs, ys, n=24):
    """Monotone cubic (Fritsch-Carlson) through the points: smooth, never overshoots the data."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < 3:
        return xs, ys
    h = np.diff(xs); d = np.diff(ys) / h
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


def _smooth_line(ax, x, s, color, label, z):
    """Smooth curve through each continuous run of points, with markers on the real readings."""
    xn = matplotlib.dates.date2num(pd.to_datetime(x))
    vals = pd.to_numeric(s, errors='coerce').to_numpy(float)
    ok = ~np.isnan(vals)
    runs, cur = [], []
    for i in range(len(vals)):
        if ok[i]:
            cur.append(i)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    for r in runs:
        sx, sy = _pchip(xn[r], vals[r])
        ax.plot(sx, sy, color=color, linewidth=1.9, solid_capstyle='round', zorder=z)
        ax.plot(xn[r], vals[r], linestyle='none', marker='o', markersize=3.8, color=color,
                markeredgecolor='white', markeredgewidth=0.6, zorder=z + 0.5)
    return Line2D([], [], color=color, linewidth=1.9, marker='o', markersize=3.8,
                  markeredgecolor='white', markeredgewidth=0.6, label=label)


def _combo_chart(fig, rep):
    """Daily metres (bars, left axis) with measured depth per leg (lines, right axis)."""
    df = rep.daily
    _section_title(fig, M, 2.6, 'Daily progress & measured depth',
                   'Bars: metres drilled per report day (left)   \u00b7   Lines: measured depth by leg (right)')
    ax = _ax(fig, M + 0.5, 3.15, CW - 1.05, 2.85)
    x = pd.to_datetime(df['Date'])
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
    bars = ax.bar(x, dr, width=0.7, color=BAR_SOFT, zorder=1, label='Metres drilled')
    top = max(250, math.ceil(dr.max() / 250) * 250)       # e.g. 908 m -> 0-1,000
    for b, v in zip(bars, dr):
        ax.text(b.get_x() + b.get_width() / 2, top * 0.012, f'{v:,.0f}', ha='center',
                va='bottom', fontsize=5, color=BAR_TEXT if v > 0 else MUTED, zorder=2)
    _style(ax)
    ax.set_ylim(0, top)
    ax.yaxis.set_major_locator(MultipleLocator(top / 5))
    ax.set_ylabel('Metres drilled per day', fontsize=6.5, color=INK2)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d %b'))
    ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=max(1, len(df) // 12)))
    ax.set_xlim(x.min() - pd.Timedelta(hours=14), x.max() + pd.Timedelta(hours=14))

    ax2 = ax.twinx()
    legs = [lg for lg in rep.legs if lg.start_idx is not None]
    first = legs[0].start_idx if legs else len(df) - 1
    handles = [bars]
    pre = pd.Series([v if i <= first else None for i, v in enumerate(df['To (m)'])], dtype='float')
    handles.append(_smooth_line(ax2, x, pre, NEUTRAL, 'Surface / build', 3))
    md_max = pd.to_numeric(df['To (m)'], errors='coerce').max()
    for lg in legs:
        s = pd.to_numeric(df[f'Leg {lg.number}'], errors='coerce')
        md_max = max(md_max, s.max())
        handles.append(_smooth_line(ax2, x, s, leg_color(lg.number), f'Leg {lg.number}', 4))
        last = s.last_valid_index()
        if last is not None:
            ax2.annotate(f'{s[last]:,.0f}', (x[last], s[last]), xytext=(0, 5), textcoords='offset points',
                         ha='center', fontsize=5.8, color=INK2, fontweight='bold', zorder=5)
    ax2.set_ylim(0, math.ceil(md_max * 1.1 / 500) * 500)
    ax2.yaxis.set_major_locator(MultipleLocator(500))
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax2.set_ylabel('Measured depth (m)', fontsize=6.5, color=INK2)
    ax2.tick_params(labelsize=6.5, pad=3)
    for sp in ('top', 'left', 'right', 'bottom'):
        ax2.spines[sp].set_visible(False)
    ax.legend(handles, [hh.get_label() for hh in handles], loc='lower center', bbox_to_anchor=(0.5, 1.0),
              ncol=len(handles), fontsize=6, frameon=False, handlelength=1.4, columnspacing=1.1)


def _time_chart(fig, rep):
    sec = rep.sections.dropna(subset=['Hours'])
    _section_title(fig, M, 6.3, 'Time by section', f"{rep.kpis['total_hours']:,.1f} hrs spud to TD")
    ax = _ax(fig, M + 0.75, 6.68, CW - 1.6, 1.65)
    names = list(sec['Section'])
    hrs = list(sec['Hours'])
    colors = [leg_color(int(n.split()[1])) if n.startswith('Leg') else NEUTRAL for n in names]
    y = range(len(names))
    ax.barh(list(y), hrs, height=0.6, color=colors, zorder=2)
    total = sum(hrs) or 1
    for yi, hh in zip(y, hrs):
        ax.text(hh + max(hrs) * 0.015, yi, f'{hh:,.1f} h  \u00b7  {hh / total:.0%}', va='center', fontsize=5.8,
                color=INK2)
    ax.set_yticks(list(y)); ax.set_yticklabels(names, fontsize=6.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(hrs) * 1.2 if hrs else 1)
    for sp in ('top', 'right', 'bottom', 'left'):
        ax.spines[sp].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(axis='y', pad=4)


def _leg_table(fig, rep):
    _section_title(fig, M, 8.5, 'Leg summary')
    cols = [('Leg', 0.0, 'left'), ('Sidetrack point (m)', 1.55, 'right'), ('End MD (m)', 2.6, 'right'),
            ('Length (m)', 3.6, 'right'), ('Reached', 5.15, 'right'), ('Leg time (hrs)', CW - 0.05, 'right')]
    rows = [lg for lg in rep.legs]
    rh = 0.18
    c = _canvas(fig, M, 8.83, CW, rh * (len(rows) + 2) + 0.1)
    for name, x, ha in cols:
        c.text(x, 0.1, name.upper(), fontsize=5.6, color=MUTED, fontweight='bold', ha=ha, va='center')
    c.plot([0, CW], [0.2, 0.2], color='#d6d5d0', linewidth=0.7)
    for i, lg in enumerate(rows):
        yy = 0.2 + rh * (i + 0.5)
        if i % 2 == 1:
            c.add_patch(Rectangle((0, 0.2 + rh * i), CW, rh, color='#faf9f7', zorder=0))
        c.add_patch(Rectangle((0, yy - 0.035), 0.07, 0.07, color=leg_color(lg.number)))
        vals = [f'Leg {lg.number}', f'{lg.kop:,.0f}' if lg.kop else '—', f'{lg.td:,.0f}' if lg.td else '—',
                f'{lg.length:,.0f}', _dt(lg.reached), '—' if lg.hours is None else f'{lg.hours:,.2f}']
        for (name, x, ha), v in zip(cols, vals):
            c.text(x + (0.14 if name == 'Leg' else 0), yy, v, fontsize=7, color=INK, ha=ha, va='center',
                   fontweight='bold' if name in ('Leg', 'Length (m)') else 'normal')
    yt = 0.2 + rh * len(rows)
    c.plot([0, CW], [yt, yt], color='#d6d5d0', linewidth=0.7)
    c.text(0.14, yt + 0.11, 'Total', fontsize=7, fontweight='bold', color=INK, va='center')
    c.text(3.6, yt + 0.11, f"{rep.kpis['total_hz_m']:,.0f}", fontsize=7, fontweight='bold', color=INK,
           ha='right', va='center')


def _footer(fig, rep):
    c = _canvas(fig, M, PAGE_H - 0.5, CW, 0.2)
    c.plot([0, CW], [0, 0], color='#e2e1dc', linewidth=0.6)
    c.text(CW / 2, 0.12, 'Created by Belloy Petroleum Consulting LTD.', fontsize=6, color=MUTED,
           ha='center', va='center')


def build_pdf(rep) -> bytes:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    fig.patch.set_facecolor('white')
    _header(fig, rep)
    _kpis(fig, rep)
    _combo_chart(fig, rep)
    _time_chart(fig, rep)
    _leg_table(fig, rep)
    _footer(fig, rep)
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        d = pdf.infodict()
        d['Title'] = f"Drilling Operations Report - {rep.well.get('Well Name', '')}"
        d['Author'] = 'Belloy Petroleum Consulting'
        pdf.savefig(fig)
    plt.close(fig)
    return buf.getvalue()
