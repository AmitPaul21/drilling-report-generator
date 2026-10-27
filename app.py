"""Drilling Report generator - upload a Well Report (.xlsm), get the single- or multi-leg drilling report."""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from brand import (BAR, BAR_TEXT, BRAND, BRAND_TINT, FOOTER, GRID, INK, INK2, MUTED, NAVY, NEUTRAL,
                   label_offsets, leg_color, logo_png_bytes, pchip, runs, section_color)
from drilling_calc import build_report
from drilling_export import fill_template
from drilling_parser import WellReportError, read_well_report
from drilling_pdf import SECTION_TONES, build_pdf, build_single_pdf
from drilling_single import build_single_report, detect_mode

st.set_page_config(page_title='Drilling Report Generator', page_icon='🛢️', layout='wide')

st.markdown(f"""
<style>
  .kpi {{ background:{BRAND_TINT}; border-radius:10px; padding:12px 16px; margin-bottom:10px; }}
  .kpi .lab {{ color:{BRAND}; font-size:0.72rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }}
  .kpi .val {{ color:{NAVY}; font-size:1.7rem; font-weight:800; line-height:1.2; }}
  .kpi .unit {{ color:{INK2}; font-size:0.85rem; font-weight:500; margin-left:4px; }}
  .eyebrow {{ color:{BRAND}; font-size:0.78rem; font-weight:700; letter-spacing:.05em; }}
  .wellname {{ color:{NAVY}; font-size:2rem !important; font-weight:800; margin:0; line-height:1.15; }}
  .sub {{ color:{INK2}; font-size:0.92rem; }}
  .meta-lab {{ color:{MUTED}; font-size:0.7rem; font-weight:700; letter-spacing:.04em; }}
  .meta-val {{ color:{INK}; font-size:0.95rem; }}
  .sec {{ color:{NAVY}; font-weight:800; font-size:1.15rem; border-left:4px solid {BRAND};
          padding-left:10px; margin:18px 0 2px 0; }}
  .secsub {{ color:{MUTED}; font-size:0.8rem; margin:0 0 6px 14px; }}
  .footer {{ color:{MUTED}; font-size:0.8rem; text-align:center; border-top:1px solid #c9d9ea;
             padding-top:8px; margin-top:24px; }}
  hr.brand {{ border:none; border-top:2px solid {BRAND}; margin:6px 0 10px 0; }}
</style>""", unsafe_allow_html=True)

MODES = {'Auto-detect': None, 'Single leg': 'single', 'Multi-leg': 'multi'}


@st.cache_data(show_spinner=False)
def load(data: bytes, version: str = '2026-10-27-gaps'):
    inp = read_well_report(data)
    xlsm, written = fill_template(data)
    return inp, detect_mode(inp), xlsm, written


@st.cache_data(show_spinner=False)
def make_report(data: bytes, mode: str, version: str = '2026-10-27-gaps'):
    inp = read_well_report(data)
    if mode == 'single':
        rep = build_single_report(inp)
        return rep, build_single_pdf(rep)
    rep = build_report(inp)
    return rep, build_pdf(rep)


def fmt_dt(v, fmt='%d %b %Y, %H:%M'):
    return '—' if v is None or pd.isna(v) else pd.Timestamp(v).strftime(fmt)


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_') or 'Well'


def section(title, sub=None):
    st.markdown(f'<div class="sec">{title}</div>' + (f'<div class="secsub">{sub}</div>' if sub else ''),
                unsafe_allow_html=True)


def kpi_tiles(tiles):
    st.write('')
    for row in (tiles[:3], tiles[3:]):
        cols = st.columns(3)
        for col, (lab, val, unit) in zip(cols, row):
            col.markdown(f'<div class="kpi"><div class="lab">{lab}</div><div class="val">{val}'
                         f'<span class="unit">{unit}</span></div></div>', unsafe_allow_html=True)


def base_combo(df):
    """Bars of daily metres (left axis) with value labels, incl. '0' on idle days. One slot per report day,
    so a suspension does not leave an empty stretch; a dashed line marks it."""
    d = pd.to_datetime(df['Date']).reset_index(drop=True)
    labels = d.dt.strftime('%d %b')
    x = pd.Series(np.arange(len(d), dtype=float))
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0).reset_index(drop=True)
    top = max(250, math.ceil(dr.max() / 250) * 250)
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(x=x, y=dr, name='Metres drilled', marker=dict(color=BAR), width=0.7, customdata=labels,
                         text=[f'{v:,.0f}' for v in dr], textposition='inside', insidetextanchor='start',
                         textfont=dict(size=11, color=[BAR_TEXT if v > 0 else MUTED for v in dr]),
                         constraintext='none', hovertemplate='%{customdata}: %{y:,.0f} m drilled<extra></extra>'),
                  secondary_y=False)
    zeros = dr[dr == 0].index
    if len(zeros):
        fig.add_trace(go.Scatter(x=x[zeros], y=[top * 0.02] * len(zeros), mode='text', text=['0'] * len(zeros),
                                 textfont=dict(size=11, color=MUTED), showlegend=False, hoverinfo='skip'),
                      secondary_y=False)
    for i in range(1, len(d)):
        gap = (d[i].normalize() - d[i - 1].normalize()).days - 1
        if gap > 0:
            fig.add_vline(x=i - 0.5, line=dict(color=MUTED, width=1, dash='dash'))
            fig.add_annotation(x=i - 0.5, y=0.5, yref='paper', text=f'{gap} days no report', textangle=-90,
                               showarrow=False, xshift=-8, font=dict(size=10, color=MUTED))
    step = max(1, math.ceil(len(d) / 20))
    fig.update_xaxes(tickvals=list(x[::step]), ticktext=list(labels[::step]), range=[-0.5, len(d) - 0.5])
    return fig, x, top


def finish_combo(fig, top, ytop, dtick_md=500):
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor='white', paper_bgcolor='white',
                      font=dict(family='Inter, Arial, sans-serif', size=13, color=INK2), bargap=0.3,
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
                      hovermode='closest')
    fig.update_xaxes(showgrid=False, linecolor='#c9d1d9')
    fig.update_yaxes(title_text='Metres drilled per day', range=[0, top], dtick=top / 5, gridcolor=GRID,
                     tickformat=',.0f', zeroline=False, secondary_y=False)
    fig.update_yaxes(title_text='Measured depth (m)', range=[0, ytop], dtick=dtick_md, showgrid=False,
                     tickformat=',.0f', zeroline=False, secondary_y=True)
    st.plotly_chart(fig, width='stretch')


def time_bars(names, hrs, colors, total_label):
    section('Time by section', total_label)
    total = sum(hrs) or 1
    fig3 = go.Figure(go.Bar(y=names, x=hrs, orientation='h', marker=dict(color=colors),
                            text=[f'{h:,.1f} h · {h / total:.0%}' for h in hrs], textposition='outside',
                            textfont=dict(color=INK2), cliponaxis=False,
                            hovertemplate='%{y}: %{x:,.1f} hrs<extra></extra>'))
    fig3.update_layout(height=34 * len(names) + 40, margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor='white',
                       paper_bgcolor='white', font=dict(family='Inter, Arial, sans-serif', size=13, color=INK2),
                       bargap=0.3)
    fig3.update_yaxes(autorange='reversed', color=INK)
    fig3.update_xaxes(visible=False, range=[0, (max(hrs) if hrs else 1) * 1.25])
    st.plotly_chart(fig3, width='stretch')


# ======================================================================= header
logo = logo_png_bytes()
h_left, h_right = st.columns([1, 3])
with h_left:
    if logo:
        st.image(logo, width=260)
with h_right:
    st.markdown('<div style="text-align:right" class="eyebrow">DRILLING REPORT GENERATOR</div>'
                '<div style="text-align:right" class="sub">Upload a Well Report (.xlsm) to build the single- or '
                'multi-leg drilling report and download it as a PDF or Excel workbook.</div>',
                unsafe_allow_html=True)
st.markdown('<hr class="brand">', unsafe_allow_html=True)

up = st.file_uploader('Well Report', type=['xlsm', 'xlsx'], label_visibility='collapsed')
if not up:
    st.info('Waiting for a Well Report file.')
    st.markdown(f'<div class="footer">{FOOTER}</div>', unsafe_allow_html=True)
    st.stop()

with st.spinner('Reading the well report…'):
    try:
        data = up.getvalue()
        inp, auto_mode, xlsm, written = load(data)
    except WellReportError as e:
        st.error(str(e))
        st.stop()

auto_label = {'single': 'Single leg', 'multi': 'Multi-leg'}[auto_mode]
choice = st.radio('Report type', [f'Auto-detect ({auto_label})', 'Single leg', 'Multi-leg'], horizontal=True,
                  help='Auto-detect picks Multi-leg when the Well Report has two or more drilled legs '
                       '(Data rows 40-49) or "Total # of Legs" is 2 or more; otherwise Single leg.')
mode = auto_mode if choice.startswith('Auto') else MODES[choice]
with st.spinner('Building the report…'):
    rep, pdf = make_report(data, mode)

w, k, df = rep.well, rep.kpis, rep.daily
lic = w.get('Licence #') or w.get('Well Name') or 'Well'
tag = 'Single_Leg' if mode == 'single' else 'Multi_Leg'

# ---- downloads first, so they are easy to find
d0, d1, d2 = st.columns(3)
d0.download_button('⬇ Drilling Report (PDF, A4)', pdf, file_name=f'{safe_name(lic)}_Drilling_Report_{tag}.pdf',
                   mime='application/pdf', type='primary', width='stretch')
d1.download_button('⬇ Drilling Report workbook (.xlsm)', xlsm,
                   file_name=f'{safe_name(lic)}_Drilling_Report.xlsm',
                   mime='application/vnd.ms-excel.sheet.macroEnabled.12', width='stretch',
                   help='Contains both the Single Leg and the Multi Leg tabs, filled with this well.')
d2.download_button('⬇ Daily data (.csv)', df.drop(columns=['Report Time']).to_csv(index=False).encode(),
                   file_name=f'{safe_name(lic)}_daily.csv', mime='text/csv', width='stretch')

# ---- well header
eyebrow = 'DRILLING OPERATIONS REPORT' + (f' · LICENCE {w["Licence #"]}' if w.get('Licence #') else '')
c1, c2, c3 = st.columns([4, 1, 1])
with c1:
    sub = ' · '.join(v for v in (w.get('Licensee'), w.get('UWI'), w.get('Surface Location')) if v)
    st.markdown(f'<div class="eyebrow">{eyebrow}</div><div class="wellname">{w.get("Well Name") or "Unnamed well"}</div>'
                f'<div class="sub">{sub}</div>', unsafe_allow_html=True)
c2.markdown(f'<div class="meta-lab">SPUD</div><div class="meta-val">{fmt_dt(rep.milestones["Spud"])}</div>',
            unsafe_allow_html=True)
c3.markdown(f'<div class="meta-lab">TOTAL DEPTH</div><div class="meta-val">{fmt_dt(rep.milestones["Total Depth"])}</div>',
            unsafe_allow_html=True)

for msg in rep.warnings:
    st.warning(msg)

# ======================================================================= single leg
if mode == 'single':
    kpi_tiles([('Total depth', f"{k['total_depth_m']:,.0f}", 'm'),
               ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day'),
               ('Operational hours', f"{k['operational_hours']:,.1f}", 'hrs'),
               ('Operational days', f"{k['operational_days']}", 'days'),
               ('Drilling days', f"{k['drilling_days']}", 'days'),
               ('Non-drilling days', f"{k['non_drilling_days']}", 'days')])

    section('Daily progress & measured depth',
            'Bars: metres drilled per report day (left axis) · Line: measured depth (right axis) · Shading: well section')
    fig, x, top = base_combo(df)
    to = pd.to_numeric(df['To (m)'], errors='coerce').to_numpy(float)
    secs = list(df['Section'])
    i = 0
    while i < len(secs):                         # shaded band per run of days in the same section
        j = i
        while j + 1 < len(secs) and secs[j + 1] == secs[i]:
            j += 1
        if secs[i]:
            line, tint = SECTION_TONES[secs[i]]
            fig.add_vrect(x0=x.iloc[i] - 0.5, x1=x.iloc[j] + 0.5,
                          fillcolor=tint, line_width=0, layer='below', annotation_text=secs[i].upper(),
                          annotation_position='top', annotation_font=dict(size=11, color=line))
        i = j + 1
    xi = x.to_numpy(float)
    for r in runs(to):
        sx, sy = pchip(xi[r], to[r])
        fig.add_trace(go.Scatter(x=sx, y=sy, mode='lines',
                                 line=dict(color=NAVY, width=2.5), name='Measured depth', hoverinfo='skip'),
                      secondary_y=True)
    ok = np.isfinite(to)
    fig.add_trace(go.Scatter(x=x[ok], y=to[ok], mode='markers+text', showlegend=False,
                             marker=dict(size=9, color=[SECTION_TONES.get(s, (NAVY,))[0] for s, o in zip(secs, ok) if o],
                                         line=dict(color='white', width=1)),
                             text=[f'{v:,.0f}' for v in to[ok]], textposition='top center',
                             textfont=dict(size=11, color=NAVY), customdata=pd.to_datetime(df['Date']).dt.strftime('%d %b').to_numpy()[ok],
                             hovertemplate='%{customdata}: %{y:,.0f} m MD<extra></extra>'), secondary_y=True)
    ytop = math.ceil(np.nanmax(to) * 1.15 / 500) * 500 if ok.any() else 500
    finish_combo(fig, top, ytop, 500 if ytop > 1500 else 250)

    sec = rep.sections.dropna(subset=['Hours'])
    time_bars(list(sec['Section']), list(sec['Hours']), [SECTION_TONES[s][0] for s in sec['Section']],
              f"{k['operational_hours']:,.1f} hrs spud to TD")

    section('Section summary')
    tbl = rep.sections.copy()
    tbl['Start'] = tbl['Start'].map(fmt_dt)
    tbl['End'] = tbl['End'].map(fmt_dt)
    st.dataframe(tbl, hide_index=True, width='stretch',
                 column_config={c_: st.column_config.NumberColumn(format='%,.0f')
                                for c_ in ['From (m)', 'To (m)', 'Length (m)']}
                 | {'Hours': st.column_config.NumberColumn(format='%.2f'),
                    'Days': st.column_config.NumberColumn(format='%d')})
    st.caption(f"Total depth: {k['total_depth_m']:,.0f} m · Lateral: {k['lateral_m']:,.0f} m")

# ======================================================================= multi-leg
else:
    legs = [lg for lg in rep.legs if lg.start_idx is not None]
    kpi_tiles([('Total horizontal', f"{k['total_hz_m']:,.0f}", 'm'), ('Legs drilled', f"{k['legs_drilled']}", ''),
               ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day'),
               ('Operational days', f"{k['operational_days']}", 'days'),
               ('Drilling days', f"{k['drilling_days']}", 'days'),
               ('Non-drilling days', f"{k['non_drilling_days']}", 'days')])

    section('Daily progress & measured depth',
            'Bars: metres drilled per report day (left axis) · Lines: measured depth by leg (right axis)')
    fig, x, top = base_combo(df)
    xi = x.to_numpy(float)
    first = legs[0].start_idx if legs else len(df) - 1
    to_md = pd.to_numeric(df['To (m)'], errors='coerce').to_numpy(float)
    series = [('Surface / build', NEUTRAL, np.array([v if i <= first else np.nan for i, v in enumerate(to_md)]))]
    series += [(f'Leg {lg.number}', leg_color(lg.number),
                pd.to_numeric(df[f'Leg {lg.number}'], errors='coerce').to_numpy(float)) for lg in legs]
    md_max = max(np.nanmax(s) for _, _, s in series if np.isfinite(s).any())
    ytop = math.ceil(md_max * 1.12 / 500) * 500
    pts, seen = [], set()
    for name, colr, vals in reversed(series):      # leg start wins over the surface end on the heel point
        for i in range(len(vals)):
            if np.isfinite(vals[i]) and (i, round(vals[i])) not in seen:
                seen.add((i, round(vals[i])))
                pts.append((i, vals[i], f'{vals[i]:,.0f}', colr))
    placement = {(i, round(v), colr): where for i, v, t, colr, where in label_offsets(pts, ytop * 0.045)}
    for name, colr, vals in series:
        for r in runs(vals):
            sx, sy = pchip(xi[r], vals[r])
            fig.add_trace(go.Scatter(x=sx, y=sy, mode='lines',
                                     line=dict(color=colr, width=2.5), showlegend=False, hoverinfo='skip',
                                     legendgroup=name), secondary_y=True)
        idx = [i for i in range(len(vals)) if np.isfinite(vals[i])]
        labels = [f'{vals[i]:,.0f}' if (i, round(vals[i]), colr) in placement else '' for i in idx]
        pos = ['bottom center' if placement.get((i, round(vals[i]), colr)) == 'below' else 'top center' for i in idx]
        fig.add_trace(go.Scatter(x=x.iloc[idx], y=vals[idx], mode='markers+text', name=name, legendgroup=name,
                                 marker=dict(color=colr, size=8, line=dict(color='white', width=1)),
                                 text=labels, textposition=pos, textfont=dict(size=11, color=colr),
                                 hovertemplate=f'{name}: ' + '%{y:,.0f} m<extra></extra>'), secondary_y=True)
    finish_combo(fig, top, ytop)

    sec = rep.sections.dropna(subset=['Hours'])
    time_bars(list(sec['Section']), list(sec['Hours']), [section_color(s) for s in sec['Section']],
              f"{k['total_hours']:,.1f} hrs spud to TD")

    section('Leg summary')
    leg_tbl = pd.DataFrame([{
        'Leg': f'Leg {lg.number}', 'Sidetrack point (m)': lg.kop, 'End MD (m)': lg.td, 'Length (m)': lg.length,
        'Reached': fmt_dt(lg.reached), 'Leg time (hrs)': None if lg.hours is None else round(lg.hours, 2),
        'Status': 'Complete' if lg.complete else ('In progress' if lg.start_idx is not None else 'Not started'),
    } for lg in rep.legs])
    st.dataframe(leg_tbl, hide_index=True, width='stretch',
                 column_config={c_: st.column_config.NumberColumn(format='%,.0f')
                                for c_ in ['Sidetrack point (m)', 'End MD (m)', 'Length (m)']}
                 | {'Leg time (hrs)': st.column_config.NumberColumn(format='%.2f')})
    st.caption(f"Total horizontal: {k['total_hz_m']:,.0f} m")

# ---- daily operations
with st.expander('Daily progress and operations', expanded=False):
    cols = ['Day', 'Date', 'From (m)', 'To (m)', 'Drilled (m)'] + (['Section'] if mode == 'single' else []) + ['Operations']
    st.dataframe(df[cols], hide_index=True, width='stretch',
                 column_config={'Operations': st.column_config.TextColumn(width='large')})

st.markdown(f'<div class="footer">{FOOTER}</div>', unsafe_allow_html=True)
