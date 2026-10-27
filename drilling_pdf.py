"""One-page A4 Drilling Operations Report PDF in the Belloy brand.

Margins: 20 mm on the left (clears 2/3-hole punching), 12 mm right, 10 mm top and 20 mm at the
bottom, so the footer stays clear of the printer's unprintable edge."""
from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use('Agg')
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
ML, MR, MT, MB = 20 * MM, 12 * MM, 10 * MM, 20 * MM   # left margin clears hole punches
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
    name = c.text(0, 0.88, w.get('Well Name') or 'Unnamed well', fontsize=16, fontweight='bold', color=NAVY,
                  va='center')
    width = name.get_window_extent(renderer=fig.canvas.get_renderer()).width / fig.dpi
    if width > CW:                                   # long names shrink to fit inside the margins
        name.set_fontsize(max(9, 16 * CW / width * 0.98))
    sub = '   \u00b7   '.join(v for v in (w.get('Licensee'), w.get('UWI'), w.get('Surface Location')) if v)
    c.text(0, 1.1, sub, fontsize=7.2, color=INK2, va='center')
    return top + 1.25


def multi_tiles(k):
    return [('Total horizontal', f"{k['total_hz_m']:,.0f}", 'm'),
            ('Legs drilled', f"{k['legs_drilled']}", ''),
            ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day'),
            ('Operational days', f"{k['operational_days']}", 'days'),
            ('Drilling days', f"{k['drilling_days']}", 'days'),
            ('Non-drilling days', f"{k['non_drilling_days']}", 'days')]


def single_tiles(k):
    return [('Total depth', f"{k['total_depth_m']:,.0f}", 'm'),
            ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day'),
            ('Operational hours', f"{k['operational_hours']:,.1f}", 'hrs'),
            ('Operational days', f"{k['operational_days']}", 'days'),
            ('Drilling days', f"{k['drilling_days']}", 'days'),
            ('Non-drilling days', f"{k['non_drilling_days']}", 'days')]


def _kpis(fig, rep, y, tiles=None):
    tiles = tiles or multi_tiles(rep.kpis)
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


def _day_axis(ax, dates, top):
    """One slot per report day (no empty stretch when the well was suspended); a dashed line marks each break."""
    d = pd.to_datetime(pd.Series(list(dates))).reset_index(drop=True)
    xn = np.arange(len(d), dtype=float)
    step = max(1, math.ceil(len(d) / 16))
    ax.set_xticks(xn[::step])
    ax.set_xticklabels([v.strftime('%d %b') for v in d[::step]])
    for i in range(1, len(d)):
        gap = (d[i].normalize() - d[i - 1].normalize()).days - 1
        if gap > 0:
            ax.axvline(i - 0.5, color=MUTED, linewidth=0.7, linestyle=(0, (3, 2)), zorder=1.5)
            ax.text(i - 0.5, top * 0.5, f'{gap} days no report', rotation=90, ha='right', va='center',
                    fontsize=5.6, color=INK2, zorder=1.6)
    ax.set_xlim(-0.5, len(d) - 0.5)
    return xn


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
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
    top = max(250, math.ceil(dr.max() / 250) * 250)          # e.g. 908 m -> 0-1,000
    xn = _day_axis(ax, df['Date'], top)
    bars = ax.bar(xn, dr, width=0.7, color=BAR, zorder=1, label='Metres drilled')
    for xv, v in zip(xn, dr):
        ax.text(xv, top * 0.012, f'{v:,.0f}', ha='center', va='bottom', fontsize=4.9,
                color=BAR_TEXT if v > 0 else MUTED, fontweight='bold' if v > 0 else 'normal', zorder=2)
    _style(ax)
    ax.set_ylim(0, top)
    ax.yaxis.set_major_locator(MultipleLocator(top / 5))
    ax.set_ylabel('Metres drilled per day', fontsize=6.3, color=INK2)

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


# ====================================================================== single leg
SECTION_TONES = {'Surface': ('#9aa7b4', '#f1f3f5'), 'Int / Build': ('#c9a227', '#fbf6e6'),
                 'Lateral': ('#255f93', '#eaf1f8')}


def _single_chart(fig, rep, y):
    df = rep.daily
    _section_title(fig, y, 'Daily progress & measured depth',
                   'Bars: metres drilled per report day (left axis)   \u00b7   Line: measured depth (right axis)'
                   '   \u00b7   Shading: well section')
    ax = _ax(fig, ML + 0.45, y + 0.68, CW - 0.95, 2.75)
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
    to = pd.to_numeric(df['To (m)'], errors='coerce').to_numpy(float)
    top = max(250, math.ceil(dr.max() / 250) * 250)
    xn = _day_axis(ax, df['Date'], top)
    # section shading: consecutive report days that end in the same section
    secs = list(df['Section'])
    i = 0
    while i < len(secs):
        j = i
        while j + 1 < len(secs) and secs[j + 1] == secs[i]:
            j += 1
        if secs[i]:
            line, tint = SECTION_TONES[secs[i]]
            ax.axvspan(xn[i] - 0.5, xn[j] + 0.5, color=tint, zorder=0, linewidth=0)
            ax.text((xn[i] + xn[j]) / 2, top * 0.985, secs[i].upper(), ha='center', va='top', fontsize=5.6,
                    color=line, fontweight='bold', zorder=1)
        i = j + 1
    bars = ax.bar(xn, dr, width=0.62, color=BAR, zorder=1, label='Metres drilled')
    for xv, v in zip(xn, dr):
        ax.text(xv, top * 0.012, f'{v:,.0f}', ha='center', va='bottom', fontsize=4.9,
                color=BAR_TEXT if v > 0 else MUTED, fontweight='bold' if v > 0 else 'normal', zorder=2)
    _style(ax)
    ax.grid(False)
    ax.set_ylim(0, top)
    ax.yaxis.set_major_locator(MultipleLocator(top / 5))
    ax.set_ylabel('Metres drilled per day', fontsize=6.3, color=INK2)

    ax2 = ax.twinx()
    ytop = math.ceil(np.nanmax(to) * 1.15 / 500) * 500 if np.isfinite(to).any() else 500
    for r in runs(to):
        sx, sy = pchip(xn[r], to[r])
        ax2.plot(sx, sy, color=NAVY, linewidth=1.8, solid_capstyle='round', zorder=4)
    for xv, v, sec in zip(xn, to, secs):
        if np.isfinite(v):
            colr = SECTION_TONES.get(sec, (NAVY, None))[0]
            ax2.plot([xv], [v], marker='o', markersize=4, color=colr, markeredgecolor='white',
                     markeredgewidth=0.6, zorder=5)
            ax2.annotate(f'{v:,.0f}', (xv, v), xytext=(0, 5), textcoords='offset points', ha='center',
                         va='bottom', fontsize=5.2, color=NAVY, fontweight='bold', zorder=6)
    ax2.set_ylim(0, ytop)
    ax2.yaxis.set_major_locator(MultipleLocator(500 if ytop > 1500 else 250))
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax2.set_ylabel('Measured depth (m)', fontsize=6.3, color=INK2)
    ax2.tick_params(labelsize=6.3, pad=3)
    for sp in ('top', 'left', 'right', 'bottom'):
        ax2.spines[sp].set_visible(False)
    handles = [bars, Line2D([], [], color=NAVY, linewidth=1.8, label='Measured depth')]
    handles += [Rectangle((0, 0), 1, 1, color=SECTION_TONES[n][1], ec=SECTION_TONES[n][0], lw=0.6, label=n)
                for n in ('Surface', 'Int / Build', 'Lateral') if n in secs]
    ax.legend(handles, [h.get_label() for h in handles], loc='lower center', bbox_to_anchor=(0.5, 1.0),
              ncol=len(handles), fontsize=5.8, frameon=False, handlelength=1.3, columnspacing=1.0)
    return y + 0.68 + 2.75 + 0.3


def _single_time(fig, rep, y):
    sec = rep.sections.dropna(subset=['Hours'])
    _section_title(fig, y, 'Time by section', f"{rep.kpis['operational_hours']:,.1f} hrs spud to TD")
    h = 0.2 * max(1, len(sec)) + 0.08
    ax = _ax(fig, ML + 0.8, y + 0.42, CW - 1.55, h)
    names, hrs = list(sec['Section']), list(sec['Hours'])
    yy = range(len(names))
    ax.barh(list(yy), hrs, height=0.6, color=[SECTION_TONES[n][0] for n in names], zorder=2)
    total = sum(hrs) or 1
    for yi, hv in zip(yy, hrs):
        ax.text(hv + max(hrs) * 0.015, yi, f'{hv:,.1f} h  \u00b7  {hv / total:.0%}', va='center',
                fontsize=5.8, color=INK2)
    ax.set_yticks(list(yy)); ax.set_yticklabels(names, fontsize=6.3, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(hrs) * 1.22 if hrs else 1)
    for sp in ('top', 'right', 'bottom', 'left'):
        ax.spines[sp].set_visible(False)
    ax.set_xticks([])
    return y + 0.42 + h + 0.15


def _single_table(fig, rep, y):
    _section_title(fig, y, 'Section summary')
    rows = rep.sections.to_dict('records')
    rh = 0.22
    cols = [('Section', 0.0, 'left'), ('From (m)', 1.55, 'right'), ('To (m)', 2.3, 'right'),
            ('Length (m)', 3.15, 'right'), ('Days', 3.7, 'right'), ('Start', 4.95, 'right'),
            ('End', 6.0, 'right'), ('Hours', CW - 0.08, 'right')]
    c = _canvas(fig, ML, y + 0.4, CW, 0.24 + rh * len(rows) + 0.3)
    c.add_patch(Rectangle((0, 0), CW, 0.22, color=BRAND_TINT))
    for name, x, ha in cols:
        c.text(x + (0.08 if ha == 'left' else 0), 0.11, name.upper(), fontsize=5.6, color=BRAND,
               fontweight='bold', ha=ha, va='center')
    fmt = lambda v, f: '\u2014' if v is None or (isinstance(v, float) and np.isnan(v)) else f.format(v)  # noqa: E731
    for i, r in enumerate(rows):
        yy = 0.22 + rh * (i + 0.5)
        c.plot([0, CW], [0.22 + rh * (i + 1)] * 2, color=GRID, linewidth=0.5)
        c.add_patch(Rectangle((0.08, yy - 0.035), 0.07, 0.07, color=SECTION_TONES[r['Section']][0]))
        vals = [r['Section'], fmt(r['From (m)'], '{:,.0f}'), fmt(r['To (m)'], '{:,.0f}'),
                fmt(r['Length (m)'], '{:,.0f}'), fmt(r['Days'], '{:.0f}'),
                _dt(r['Start'], '%d %b, %H:%M'), _dt(r['End'], '%d %b, %H:%M'), fmt(r['Hours'], '{:,.2f}')]
        for (name, x, ha), v in zip(cols, vals):
            c.text(x + (0.22 if name == 'Section' else 0), yy, v, fontsize=6.6, color=INK, ha=ha, va='center',
                   fontweight='bold' if name in ('Section', 'Length (m)') else 'normal')
    yt = 0.22 + rh * len(rows)
    c.plot([0, CW], [yt, yt], color=BRAND_LINE, linewidth=0.9)
    k = rep.kpis
    c.text(0.22, yt + 0.13, 'Total', fontsize=6.6, fontweight='bold', color=NAVY, va='center')
    c.text(3.15, yt + 0.13, f"{k['total_depth_m']:,.0f}", fontsize=6.6, fontweight='bold', color=NAVY,
           ha='right', va='center')
    c.text(CW - 0.08, yt + 0.13, f"{k['operational_hours']:,.2f}", fontsize=6.6, fontweight='bold',
           color=NAVY, ha='right', va='center')


def build_single_pdf(rep) -> bytes:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    fig.patch.set_facecolor('white')
    fig.canvas.draw()
    y = _header(fig, rep) + 0.12
    y = _kpis(fig, rep, y, single_tiles(rep.kpis)) + 0.22
    y = _single_chart(fig, rep, y)
    y = _single_time(fig, rep, y)
    _single_table(fig, rep, y)
    _footer(fig)
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        d = pdf.infodict()
        d['Title'] = f"Drilling Operations Report - {rep.well.get('Well Name', '')}"
        d['Author'] = 'Belloy Petroleum Consulting LTD.'
        pdf.savefig(fig)
    plt.close(fig)
    return buf.getvalue()
