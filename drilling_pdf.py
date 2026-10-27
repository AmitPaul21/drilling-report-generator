"""One-page (US Letter) Drilling Operations Report PDF - modern layout.

Header with the well as the headline, a KPI strip, measured depth by leg, daily metres and
time by section side by side, and a leg summary table. Each chart has a single y-scale."""
from __future__ import annotations

import functools
import io
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

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
NEUTRAL = '#a3a29c'
# validated categorical order - colour follows the leg number
LEG_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']

PAGE_W, PAGE_H = 8.5, 11.0
LOGO_URL = 'https://belloygeologists.ca/wp-content/uploads/2022/09/Belloy-Geologists-Logo-1.png'
LOGO_FILE = Path(__file__).resolve().parent / 'belloy_logo.png'   # optional local override
LOGO_COLOR = (14, 58, 87)                                           # Belloy navy
M = 0.55                                   # page margin (in)
CW = PAGE_W - 2 * M                        # content width


@functools.lru_cache(maxsize=1)
def load_logo():
    """Belloy logo as an RGBA array, or None. Uses belloy_logo.png if present, otherwise the
    website logo (white on transparent), recoloured navy for a white page."""
    try:
        import numpy as np
        from PIL import Image
        if LOGO_FILE.exists():
            img = Image.open(LOGO_FILE).convert('RGBA')
            return np.asarray(img)
        req = urllib.request.Request(LOGO_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as r:
            img = Image.open(io.BytesIO(r.read())).convert('RGBA')
        arr = np.array(img)
        if arr[..., :3][arr[..., 3] > 128].mean() > 200:        # white logo -> recolour
            arr[..., 0], arr[..., 1], arr[..., 2] = LOGO_COLOR
        return arr
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


def _depth_chart(fig, rep):
    df = rep.daily
    _section_title(fig, M, 2.6, 'Measured depth by leg', 'Kick-off depth to end depth for each leg, by report day')
    ax = _ax(fig, M + 0.45, 3.05, CW - 0.55, 2.55)
    x = pd.to_datetime(df['Date'])
    legs = [lg for lg in rep.legs if lg.start_idx is not None]
    first = legs[0].start_idx if legs else len(df) - 1
    ax.plot(x[:first + 1], df['To (m)'][:first + 1], color=NEUTRAL, linewidth=1.8, marker='o',
            markersize=3.5, markeredgecolor='white', markeredgewidth=0.6, label='Surface / build', zorder=3)
    for lg in legs:
        s = pd.to_numeric(df[f'Leg {lg.number}'], errors='coerce')
        ax.plot(x, s, color=leg_color(lg.number), linewidth=1.8, marker='o', markersize=3.8,
                markeredgecolor='white', markeredgewidth=0.6, label=f'Leg {lg.number}', zorder=4)
        last = s.last_valid_index()
        if last is not None:
            ax.annotate(f'{s[last]:,.0f}', (x[last], s[last]), xytext=(0, 5), textcoords='offset points',
                        ha='center', fontsize=5.8, color=INK2, fontweight='bold')
    _style(ax)
    ax.set_ylabel('MD (m)', fontsize=6.5, color=INK2)
    ax.set_ylim(0, None)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d %b'))
    ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=max(1, len(df) // 10)))
    ax.set_xlim(x.min() - pd.Timedelta(hours=12), x.max() + pd.Timedelta(hours=12))
    ax.legend(loc='lower right', ncol=min(4, len(legs) + 1), fontsize=6, frameon=False,
              handlelength=1.4, columnspacing=1.0, borderaxespad=0.2)


def _daily_chart(fig, rep):
    df = rep.daily
    w = CW * 0.56
    _section_title(fig, M, 5.85, 'Daily metres drilled', 'All legs combined, per report day')
    ax = _ax(fig, M + 0.45, 6.3, w - 0.5, 1.95)
    x = pd.to_datetime(df['Date'])
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
    bars = ax.bar(x, dr, width=0.72, color=BAR, zorder=2)
    for b, v in zip(bars, dr):
        if v > 0:
            ax.text(b.get_x() + b.get_width() / 2, v + dr.max() * 0.02, f'{v:,.0f}', ha='center',
                    va='bottom', fontsize=5, color=INK2)
    _style(ax)
    ax.set_ylim(0, dr.max() * 1.15 if dr.max() else 1)
    ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d %b'))
    ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=max(2, len(df) // 6)))
    ax.set_xlim(x.min() - pd.Timedelta(hours=14), x.max() + pd.Timedelta(hours=14))


def _time_chart(fig, rep):
    sec = rep.sections.dropna(subset=['Hours'])
    x0 = M + CW * 0.6
    w = CW * 0.4
    _section_title(fig, x0, 5.85, 'Time by section', f"{rep.kpis['total_hours']:,.1f} hrs spud to TD")
    ax = _ax(fig, x0 + 0.62, 6.3, w - 0.95, 1.95)
    names = list(sec['Section'])
    hrs = list(sec['Hours'])
    colors = [leg_color(int(n.split()[1])) if n.startswith('Leg') else NEUTRAL for n in names]
    y = range(len(names))
    ax.barh(list(y), hrs, height=0.62, color=colors, zorder=2)
    total = sum(hrs) or 1
    for yi, h in zip(y, hrs):
        ax.text(h + max(hrs) * 0.03, yi, f'{h:,.1f} h  ·  {h / total:.0%}', va='center', fontsize=5.6,
                color=INK2)
    ax.set_yticks(list(y)); ax.set_yticklabels(names, fontsize=6.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(hrs) * 1.45 if hrs else 1)
    for s in ('top', 'right', 'bottom', 'left'):
        ax.spines[s].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(axis='y', pad=4)


def _leg_table(fig, rep):
    _section_title(fig, M, 8.45, 'Leg summary')
    cols = [('Leg', 0.0, 'left'), ('Kick-off (m)', 1.35, 'right'), ('End MD (m)', 2.45, 'right'),
            ('Length (m)', 3.5, 'right'), ('Reached', 5.15, 'right'), ('Leg time (hrs)', CW - 0.05, 'right')]
    rows = [lg for lg in rep.legs]
    rh = 0.18
    c = _canvas(fig, M, 8.78, CW, rh * (len(rows) + 2) + 0.1)
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
    c.text(3.5, yt + 0.11, f"{rep.kpis['total_hz_m']:,.0f}", fontsize=7, fontweight='bold', color=INK,
           ha='right', va='center')


def _footer(fig, rep):
    c = _canvas(fig, M, PAGE_H - 0.5, CW, 0.2)
    c.plot([0, CW], [0, 0], color='#e2e1dc', linewidth=0.6)
    c.text(0, 0.12, 'Belloy Petroleum Consulting Ltd.  ·  Drilling Report Generator', fontsize=5.8,
           color=MUTED, va='center')
    c.text(CW, 0.12, f"Generated {pd.Timestamp.now().strftime('%d %b %Y')}", fontsize=5.8, color=MUTED,
           ha='right', va='center')


def build_pdf(rep) -> bytes:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    fig.patch.set_facecolor('white')
    _header(fig, rep)
    _kpis(fig, rep)
    _depth_chart(fig, rep)
    _daily_chart(fig, rep)
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
