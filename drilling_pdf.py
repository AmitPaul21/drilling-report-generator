"""One-page (US Letter) Drilling Operations Report PDF, laid out like the Excel print of the
'Drilling Report - Multi Leg' tab: header, KPI tiles, timing doughnut, leg banner, combo chart."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

NAVY = '#14365c'
BAND = '#dceaf8'
TILE = '#21678a'
TILE_EDGE = '#164a63'
TILE_LABEL = '#ffe36e'
INK = '#1b1b1b'
GRID = '#d9d9d9'
BAR = '#83cbeb'
BAR_EDGE = '#1f4e79'
MARKER = '#e03c31'
SECTION_COLORS = {'Surface': '#156082', 'Int / Build': '#e97132'}
LEG_COLORS = ['#2b7635', '#0f9ed5', '#a02b93', '#4ea72e', '#0d3a4e', '#994010',
              '#5b9bd5', '#c00000', '#7f6000', '#3a3a3a']

PAGE_W, PAGE_H = 8.5, 11.0


def leg_color(n: int) -> str:
    return LEG_COLORS[(n - 1) % len(LEG_COLORS)]


def _ax(fig, x, y, w, h, **kw):
    """Axes placed in inches from the page's top-left corner."""
    return fig.add_axes([x / PAGE_W, 1 - (y + h) / PAGE_H, w / PAGE_W, h / PAGE_H], **kw)


def _fmt_dt(v):
    return '' if v is None or pd.isna(v) else pd.Timestamp(v).strftime('%-d-%b-%Y @ %H:%M')


def _header(fig, rep):
    ax = _ax(fig, 0.5, 0.5, 7.5, 0.95)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    ax.add_patch(Rectangle((0, 0.66), 1, 0.34, color=NAVY))
    ax.text(0.5, 0.83, 'Drilling Operations Report', ha='center', va='center', color='white',
            fontsize=13, fontweight='bold')
    ax.add_patch(Rectangle((0, 0), 1, 0.66, color=BAND))
    w = rep.well
    rows = [('Operator:', w.get('Licensee', ''), 'UWI:', w.get('UWI', '')),
            ('Well Name:', w.get('Well Name', ''), 'Spud Date:', _fmt_dt(rep.milestones.get('Spud'))),
            ('Location:', w.get('Surface Location', ''), 'TD Date:', _fmt_dt(rep.milestones.get('Total Depth')))]
    for i, (l1, v1, l2, v2) in enumerate(rows):
        y = 0.55 - i * 0.2
        ax.text(0.155, y, l1, ha='right', va='center', fontsize=8, fontweight='bold', color=INK)
        ax.text(0.165, y, v1, ha='left', va='center', fontsize=8, color=INK)
        ax.text(0.655, y, l2, ha='right', va='center', fontsize=8, fontweight='bold', color=INK)
        ax.text(0.665, y, v2, ha='left', va='center', fontsize=8, color=INK)


def _kpis(fig, rep):
    k = rep.kpis
    ax = _ax(fig, 0.5, 1.5, 3.6, 2.85)
    ax.set_xlim(0, 3.6); ax.set_ylim(0, 2.85); ax.axis('off')
    ax.text(1.8, 2.62, 'Key Performance Indicators', ha='center', va='center', fontsize=11,
            fontweight='bold', color=INK)
    tiles = [('TOTAL HZ', f"{k['total_hz_m']:,.0f} m"),
             ('OPERATIONAL DAYS', f"{k['operational_days']} Days"),
             ('DRILLING DAYS', f"{k['drilling_days']} Days"),
             ('AVG DAILY PROGRESS', f"{k['avg_daily_m']:,.2f} m/day"),
             ('NUMBER OF LEGS', f"{k['legs_drilled']}"),
             ('NON DRILLING', f"{k['non_drilling_days']} Days")]
    tw, th = 1.55, 0.58
    for i, (label, val) in enumerate(tiles):
        col, row = i % 2, i // 2
        x = 0.2 + col * (tw + 0.25)
        y = 1.72 - row * (th + 0.2)
        ax.add_patch(FancyBboxPatch((x + 0.03, y - 0.03), tw, th, boxstyle='round,pad=0,rounding_size=0.08',
                                    color='#9aa9b5', zorder=1))
        ax.add_patch(FancyBboxPatch((x, y), tw, th, boxstyle='round,pad=0,rounding_size=0.08',
                                    facecolor=TILE, edgecolor=TILE_EDGE, linewidth=0.8, zorder=2))
        ax.text(x + tw / 2, y + th * 0.7, label, ha='center', va='center', fontsize=7.5,
                color=TILE_LABEL, zorder=3)
        ax.text(x + tw / 2, y + th * 0.32, val, ha='center', va='center', fontsize=9.5,
                color='white', fontweight='bold', zorder=3)


def _donut(fig, rep):
    sec = rep.sections.dropna(subset=['Hours'])
    sec = sec[sec['Hours'] > 0]
    ax = _ax(fig, 4.3, 1.62, 3.6, 2.5)
    if sec.empty:
        ax.axis('off'); ax.text(0.5, 0.5, 'No milestone times entered', ha='center', va='center'); return
    names = list(sec['Section'])
    colors = [SECTION_COLORS.get(n) or leg_color(int(n.split()[1])) for n in names]
    hours = list(sec['Hours'])
    total = sum(hours)
    wedges, _ = ax.pie(hours, colors=colors, startangle=90, counterclock=False, radius=0.95,
                       wedgeprops=dict(width=0.42, edgecolor='white', linewidth=1.2))
    import math
    for wdg, n, h in zip(wedges, names, hours):
        pct = h / total
        ang = math.radians((wdg.theta1 + wdg.theta2) / 2)
        label = f"Hours\n{n.upper() if not n.startswith('Leg') else n}\n{h:,.2f}\n{pct:.0%}"
        if pct >= 0.06:
            r = 0.74
            ax.text(r * math.cos(ang), r * math.sin(ang), label, ha='center', va='center',
                    fontsize=5.2, color='white', fontweight='bold', linespacing=1.1)
        else:
            r = 1.13
            ax.text(r * math.cos(ang), r * math.sin(ang), label, ha='center', va='center',
                    fontsize=5.0, color=INK, linespacing=1.1)
    ax.text(0, 0, 'Drilling Timing\nSummary', ha='center', va='center', fontsize=8.5,
            fontweight='bold', color=INK)
    ax.set_aspect('equal')
    lg = _ax(fig, 4.2, 4.15, 3.8, 0.22)
    lg.axis('off')
    handles = [Rectangle((0, 0), 1, 1, color=c) for c in colors]
    lg.legend(handles, [n.upper() if not n.startswith('Leg') else n for n in names], loc='center',
              ncol=len(names), fontsize=5.5, frameon=False, handlelength=0.8, handletextpad=0.3,
              columnspacing=0.8)


def _leg_banner(fig, rep):
    ax = _ax(fig, 0.5, 4.55, 7.5, 0.92)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    ax.text(0.5, 0.86, 'Daily Drilling Process & Measured Depth', ha='center', va='center',
            fontsize=11, fontweight='bold', color=INK)
    ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.58, boxstyle='round,pad=0,rounding_size=0.06',
                                facecolor='white', edgecolor='#5d91a8', linewidth=1.0,
                                mutation_aspect=0.5))
    ax.text(0.5, 0.44, 'LEG SECTIONS (Meters Drilled Per LEG)', ha='center', va='center',
            fontsize=7.5, fontweight='bold', color='#1f6f9a')
    txt = '  |  '.join(f'Leg {lg.number}: {lg.length:,.0f} m' for lg in rep.legs if lg.length > 0)
    ax.text(0.5, 0.2, txt or '—', ha='center', va='center', fontsize=7.5, fontweight='bold', color=INK)


def _place_labels(points, min_gap):
    """points: list of (x_index, y, text). Returns list with vertical offsets (points) avoiding overlaps
    between labels on the same x position."""
    out = []
    by_x = {}
    for p in points:
        by_x.setdefault(p[0], []).append(p)
    for x, pts in by_x.items():
        pts = sorted(pts, key=lambda p: p[1])
        last_y = None
        for i, (xi, y, t) in enumerate(pts):
            off = 6
            if last_y is not None and abs(y - last_y) < min_gap:
                out[-1] = (*out[-1][:3], -12)   # lower of two close labels goes under its marker
            out.append((xi, y, t, off))
            last_y = y
    return out


def _combo(fig, rep):
    df = rep.daily
    ax = _ax(fig, 1.05, 5.75, 6.35, 3.85)
    x = list(range(len(df)))
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
    bars = ax.bar(x, dr, width=0.92, color=BAR, edgecolor=BAR_EDGE, linewidth=0.6, label='DRILLED', zorder=2)
    for b, v in zip(bars, dr):
        ax.text(b.get_x() + b.get_width() / 2, 12 if v > 60 else v + 12, f'{v:,.0f}', ha='center',
                va='bottom', fontsize=5.5, color=INK, zorder=4)
    ymax_bar = max(100, (int(dr.max() / 100) + 1) * 100)
    ax.set_ylim(0, ymax_bar)
    ax.set_ylabel('Daily Drilling Progress (m)', fontsize=8)
    ax.set_xlabel('Date', fontsize=8)
    ax.grid(axis='y', color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=6.5)
    ax.set_xticks(x)
    ax.set_xticklabels([pd.Timestamp(d).strftime('%d-%b-%y') for d in df['Date']], rotation=45,
                       ha='right', fontsize=6, fontweight='bold')
    ax.set_xlim(-0.6, len(df) - 0.4)
    for s in ('top',):
        ax.spines[s].set_visible(False)

    ax2 = ax.twinx()
    leg_cols = [c for c in df.columns if c.startswith('Leg ')]
    md_max = 0
    labels = []
    handles = [bars]
    for col in leg_cols:
        n = int(col.split()[1])
        s = pd.to_numeric(df[col], errors='coerce')
        if s.notna().sum() == 0:
            continue
        md_max = max(md_max, s.max())
        h, = ax2.plot(x, s, color=leg_color(n), linewidth=1.6, marker='o', markersize=3.2,
                      markerfacecolor=MARKER, markeredgecolor=MARKER, label=col, zorder=5)
        handles.append(h)
        labels += [(i, v, f'{v:,.0f}') for i, v in zip(x, s) if pd.notna(v)]
    top = max(500, (int(md_max / 500) + 1) * 500)
    ax2.set_ylim(0, top)
    ax2.set_ylabel('Measured Depth (m)', fontsize=8)
    ax2.tick_params(labelsize=6.5)
    ax2.spines['top'].set_visible(False)
    gap = top * 0.035
    for i, v, t, off in _place_labels(labels, gap):
        ax2.annotate(t, (i, v), xytext=(0, off), textcoords='offset points', ha='center', fontsize=5.8,
                     fontweight='bold', color=INK, zorder=6,
                     bbox=dict(boxstyle='round,pad=0.1', facecolor='white', edgecolor='none', alpha=0.7))
    ax.legend(handles, [h.get_label() for h in handles], loc='lower center', bbox_to_anchor=(0.5, 1.0),
              ncol=len(handles), fontsize=6.5, frameon=False, handlelength=1.6, columnspacing=1.2)


def build_pdf(rep) -> bytes:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    # page frame like the Excel print area
    frame = fig.add_axes([0, 0, 1, 1]); frame.axis('off'); frame.set_xlim(0, PAGE_W); frame.set_ylim(0, PAGE_H)
    frame.add_patch(Rectangle((0.5, PAGE_H - 10.4), 7.5, 9.9, fill=False, edgecolor=NAVY, linewidth=1.2))
    frame.plot([0.5, 8.0], [PAGE_H - 4.45, PAGE_H - 4.45], color=NAVY, linewidth=1.0)
    _header(fig, rep)
    _kpis(fig, rep)
    _donut(fig, rep)
    _leg_banner(fig, rep)
    _combo(fig, rep)
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        d = pdf.infodict()
        d['Title'] = f"Drilling Operations Report - {rep.well.get('Well Name', '')}"
        d['Author'] = 'Belloy Petroleum Consulting'
        pdf.savefig(fig)
    plt.close(fig)
    return buf.getvalue()
