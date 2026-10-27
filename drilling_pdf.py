"""One-page A4 Drilling Operations Report PDF in the Belloy brand.

Margins: 25 mm on the left (room for 2/3-hole punching) and 15 mm elsewhere, so nothing is cut
off when printed and punched."""
from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator  # noqa: E402

from brand import (BAR, BAR_TEXT, BRAND, BRAND_LINE, BRAND_TINT, FOOTER, GRID, INK, INK2, MUTED,  # noqa: E402
                   NAVY, NEUTRAL, label_offsets, leg_color, load_logo, pchip, runs, section_color)

plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 7.5,
    'axes.edgecolor': '#c9d1d9', 'axes.linewidth': 0.6, 'xtick.color': INK2, 'ytick.color': INK2,
    'xtick.major.size': 0, 'ytick.major.size': 0, 'pdf.fonttype': 42,
})

MM = 1 / 25.4
PAGE_W, PAGE_H = 210 * MM, 297 * MM            # A4 portrait
ML, MR, MT, MB = 25 * MM, 15 * MM, 15 * MM, 13 * MM   # left margin clears hole punches
CW = PAGE_W - ML - MR                           # content width (~6.7 in)


def _ax(fig, x, y, w, h, **kw):
    """Axes placed in inches from the page's top-left corner."""
    return fig.add_axes([x / PAGE_W, 1 - (y + h) / PAGE_H, w / PAGE_W, h / PAGE_H], **kw)


def _canvas(fig, x, y, w, h):
    ax = _ax(fig, x, y, w, h)
    ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.axis('off')   # inch units, y downwards
    return ax


def _dt(v, fmt='%d %b %Y, %H:%M'):
    return '—' if v is None or pd.isna(v) else pd.Timestamp(v).strftime(fmt)


def _style(ax):
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.grid(axis='y', color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=6.3, pad=3)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))


def _section_title(fig, y, title, sub=None):
    c = _canvas(fig, ML, y, CW, 0.36)
    c.add_patch(Rectangle((0, 0.04), 0.035, 0.17, color=BRAND))
    c.text(0.1, 0.125, title, fontsize=9.5, fontweight='bold', color=NAVY, va='center')
    if sub:
        c.text(0.1, 0.31, sub, fontsize=6.3, color=MUTED, va='center')


# ---------------------------------------------------------------- blocks
def _header(fig, rep):
    w = rep.well
    top = MT
    c = _canvas(fig, ML, top, CW, 1.25)
    logo = load_logo()
    if logo is not None:
        lh = 0.38
        lw = lh * logo.shape[1] / logo.shape[0]
        lax = _ax(fig, ML, top, lw, lh)
        lax.imshow(logo, interpolation='none')      # embed at full resolution -> crisp
        lax.axis('off')
    # spud / TD top-right, beside the logo
    for i, (lab, val) in enumerate((('SPUD', rep.milestones.get('Spud')),
                                    ('TOTAL DEPTH', rep.milestones.get('Total Depth')))):
        x = CW - (1 - i) * 1.4 - 1.3
        c.text(x, 0.09, lab, fontsize=5.6, color=MUTED, fontweight='bold', va='center')
        c.text(x, 0.26, _dt(val), fontsize=7, color=INK, va='center')
    c.plot([0, CW], [0.5, 0.5], color=BRAND, linewidth=1.4)
    lic = w.get('Licence #')
    eyebrow = 'DRILLING OPERATIONS REPORT' + (f'   \u00b7   LICENCE {lic}' if lic else '')
    c.text(0, 0.66, eyebrow, fontsize=6.5, color=BRAND, fontweight='bold', va='center')
    c.text(0, 0.88, w.get('Well Name') or 'Unnamed well', fontsize=16, fontweight='bold', color=NAVY,
           va='center')
    sub = '   \u00b7   '.join(v for v in (w.get('Licensee'), w.get('UWI'), w.get('Surface Location')) if v)
    c.text(0, 1.1, sub, fontsize=7.2, color=INK2, va='center')
    return top + 1.25


def _kpis(fig, rep, y):
    k = rep.kpis
    tiles = [('Total horizontal', f"{k['total_hz_m']:,.0f}", 'm'),
             ('Legs drilled', f"{k['legs_drilled']}", ''),
             ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day'),
             ('Operational days', f"{k['operational_days']}", 'days'),
             ('Drilling days', f"{k['drilling_days']}", 'days'),
             ('Non-drilling days', f"{k['non_drilling_days']}", 'days')]
    gap, th = 0.09, 0.5
    tw = (CW - 2 * gap) / 3
    c = _canvas(fig, ML, y, CW, 2 * th + gap)
    renderer = fig.canvas.get_renderer()
    for i, (lab, val, unit) in enumerate(tiles):
        x, yy = (i % 3) * (tw + gap), (i // 3) * (th + gap)
        c.add_patch(FancyBboxPatch((x, yy), tw, th, boxstyle='round,pad=0,rounding_size=0.06',
                                   facecolor=BRAND_TINT, edgecolor='none'))
        c.text(x + 0.14, yy + 0.15, lab.upper(), fontsize=5.6, color=BRAND, fontweight='bold', va='center')
        t = c.text(x + 0.14, yy + 0.35, val, fontsize=14, color=NAVY, fontweight='bold', va='center')
        if unit:
            wid = t.get_window_extent(renderer=renderer).width / fig.dpi
            c.text(x + 0.14 + wid + 0.05, yy + 0.38, unit, fontsize=6.5, color=INK2, va='center')
    return y + 2 * th + gap


def _smooth(ax, xn, vals, color, z):
    for r in runs(vals):
        sx, sy = pchip(xn[r], vals[r])
        ax.plot(sx, sy, color=color, linewidth=1.8, solid_capstyle='round', zorder=z)
        ax.plot(xn[r], vals[r], linestyle='none', marker='o', markersize=3.6, color=color,
                markeredgecolor='white', markeredgewidth=0.6, zorder=z + 0.5)


def _combo_chart(fig, rep, y):
    df = rep.daily
    _section_title(fig, y, 'Daily progress & measured depth',
                   'Bars: metres drilled per report day (left axis)   ·   Lines: measured depth by leg (right axis)')
    ax = _ax(fig, ML + 0.45, y + 0.68, CW - 0.95, 2.75)
    x = pd.to_datetime(df['Date'])
    xn = mdates.date2num(x)
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
    bars = ax.bar(xn, dr, width=0.7, color=BAR, zorder=1, label='Metres drilled')
    top = max(250, math.ceil(dr.max() / 250) * 250)          # e.g. 908 m -> 0-1,000
    for xv, v in zip(xn, dr):
        ax.text(xv, top * 0.012, f'{v:,.0f}', ha='center', va='bottom', fontsize=4.9,
                color=BAR_TEXT if v > 0 else MUTED, fontweight='bold' if v > 0 else 'normal', zorder=2)
    _style(ax)
    ax.set_ylim(0, top)
    ax.yaxis.set_major_locator(MultipleLocator(top / 5))
    ax.set_ylabel('Metres drilled per day', fontsize=6.3, color=INK2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(df) // 12)))
    ax.set_xlim(xn.min() - 0.6, xn.max() + 0.6)

    ax2 = ax.twinx()
    legs = [lg for lg in rep.legs if lg.start_idx is not None]
    first = legs[0].start_idx if legs else len(df) - 1
    to_md = pd.to_numeric(df['To (m)'], errors='coerce').to_numpy(float)
    series = [('Surface / build', NEUTRAL,
               np.array([v if i <= first else np.nan for i, v in enumerate(to_md)], float))]
    series += [(f'Leg {lg.number}', leg_color(lg.number),
                pd.to_numeric(df[f'Leg {lg.number}'], errors='coerce').to_numpy(float)) for lg in legs]
    md_max = max(np.nanmax(s) for _, _, s in series if np.isfinite(s).any())
    ytop = math.ceil(md_max * 1.12 / 500) * 500
    handles = [bars]
    pts, seen = [], set()
    for z, (name, colr, vals) in reversed(list(enumerate(series))):
        _smooth(ax2, xn, vals, colr, 3 + z * 0.01)
        handles.insert(1, Line2D([], [], color=colr, linewidth=1.8, marker='o', markersize=3.6,
                                 markeredgecolor='white', label=name))
        pts += [(i, vals[i], f'{vals[i]:,.0f}', colr) for i in range(len(vals))
                if np.isfinite(vals[i]) and (i, round(vals[i])) not in seen and not seen.add((i, round(vals[i])))]
    for i, v, t, colr, where in label_offsets(pts, ytop * 0.045):
        ax2.annotate(t, (xn[i], v), xytext=(0, 5 if where == 'above' else -6), textcoords='offset points',
                     ha='center', va='bottom' if where == 'above' else 'top', fontsize=5, color=colr,
                     fontweight='bold', zorder=6)
    ax2.set_ylim(0, ytop)
    ax2.yaxis.set_major_locator(MultipleLocator(500))
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax2.set_ylabel('Measured depth (m)', fontsize=6.3, color=INK2)
    ax2.tick_params(labelsize=6.3, pad=3)
    for sp in ('top', 'left', 'right', 'bottom'):
        ax2.spines[sp].set_visible(False)
    ax.legend(handles, [h.get_label() for h in handles], loc='lower center', bbox_to_anchor=(0.5, 1.0),
              ncol=min(len(handles), 8), fontsize=5.8, frameon=False, handlelength=1.3, columnspacing=0.9)
    return y + 0.68 + 2.75 + 0.3


def _time_chart(fig, rep, y):
    sec = rep.sections.dropna(subset=['Hours'])
    _section_title(fig, y, 'Time by section', f"{rep.kpis['total_hours']:,.1f} hrs spud to TD")
    h = 0.15 * len(sec) + 0.08
    ax = _ax(fig, ML + 0.8, y + 0.42, CW - 1.55, h)
    names, hrs = list(sec['Section']), list(sec['Hours'])
    yy = range(len(names))
    ax.barh(list(yy), hrs, height=0.62, color=[section_color(n) for n in names], zorder=2)
    total = sum(hrs) or 1
    for yi, hv in zip(yy, hrs):
        ax.text(hv + max(hrs) * 0.015, yi, f'{hv:,.1f} h  ·  {hv / total:.0%}', va='center',
                fontsize=5.8, color=INK2)
    ax.set_yticks(list(yy)); ax.set_yticklabels(names, fontsize=6.3, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(hrs) * 1.22 if hrs else 1)
    for sp in ('top', 'right', 'bottom', 'left'):
        ax.spines[sp].set_visible(False)
    ax.set_xticks([])
    return y + 0.42 + h + 0.15


def _leg_table(fig, rep, y, y_max):
    _section_title(fig, y, 'Leg summary')
    rows = list(rep.legs)
    rh = max(0.12, min(0.19, (y_max - (y + 0.4) - 0.5) / max(1, len(rows))))
    cols = [('Leg', 0.0, 'left'), ('Sidetrack point (m)', 1.75, 'right'), ('End MD (m)', 2.7, 'right'),
            ('Length (m)', 3.6, 'right'), ('Reached', 5.25, 'right'), ('Leg time (hrs)', CW - 0.08, 'right')]
    c = _canvas(fig, ML, y + 0.4, CW, 0.24 + rh * len(rows) + 0.25)
    c.add_patch(Rectangle((0, 0), CW, 0.22, color=BRAND_TINT))
    for name, x, ha in cols:
        c.text(x + (0.08 if ha == 'left' else 0), 0.11, name.upper(), fontsize=5.6, color=BRAND,
               fontweight='bold', ha=ha, va='center')
    for i, lg in enumerate(rows):
        yy = 0.22 + rh * (i + 0.5)
        c.plot([0, CW], [0.22 + rh * (i + 1)] * 2, color=GRID, linewidth=0.5)
        c.add_patch(Rectangle((0.08, yy - 0.035), 0.07, 0.07, color=leg_color(lg.number)))
        vals = [f'Leg {lg.number}', f'{lg.kop:,.0f}' if lg.kop else '—', f'{lg.td:,.0f}' if lg.td else '—',
                f'{lg.length:,.0f}', _dt(lg.reached), '—' if lg.hours is None else f'{lg.hours:,.2f}']
        for (name, x, ha), v in zip(cols, vals):
            c.text(x + (0.22 if name == 'Leg' else 0), yy, v, fontsize=6.8, color=INK, ha=ha, va='center',
                   fontweight='bold' if name in ('Leg', 'Length (m)') else 'normal')
    yt = 0.22 + rh * len(rows)
    c.plot([0, CW], [yt, yt], color=BRAND_LINE, linewidth=0.9)
    c.text(0.22, yt + 0.12, 'Total', fontsize=6.8, fontweight='bold', color=NAVY, va='center')
    c.text(3.6, yt + 0.12, f"{rep.kpis['total_hz_m']:,.0f}", fontsize=6.8, fontweight='bold', color=NAVY,
           ha='right', va='center')


def _footer(fig):
    c = _canvas(fig, ML, PAGE_H - MB - 0.2, CW, 0.2)
    c.plot([0, CW], [0.02, 0.02], color=BRAND_LINE, linewidth=0.6)
    c.text(CW / 2, 0.13, FOOTER, fontsize=6, color=MUTED, ha='center', va='center')


def build_pdf(rep) -> bytes:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    fig.patch.set_facecolor('white')
    fig.canvas.draw()
    y = _header(fig, rep) + 0.12
    y = _kpis(fig, rep, y) + 0.22
    y = _combo_chart(fig, rep, y)
    y = _time_chart(fig, rep, y)
    _leg_table(fig, rep, y, PAGE_H - MB - 0.25)
    _footer(fig)
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        d = pdf.infodict()
        d['Title'] = f"Drilling Operations Report - {rep.well.get('Well Name', '')}"
        d['Author'] = 'Belloy Petroleum Consulting LTD.'
        pdf.savefig(fig)
    plt.close(fig)
    return buf.getvalue()
