"""Drilling Report generator - upload a Well Report (.xlsm), get the multi-leg drilling report."""
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
from drilling_pdf import build_pdf

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


@st.cache_data(show_spinner=False)
def process(data: bytes, version: str = '2026-10-27-a4'):
    rep = build_report(read_well_report(data))
    xlsm, written = fill_template(data)
    pdf = build_pdf(rep)
    return rep, xlsm, written, pdf


def fmt_dt(v):
    return '—' if v is None or pd.isna(v) else pd.Timestamp(v).strftime('%d %b %Y, %H:%M')


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_') or 'Well'


def section(title, sub=None):
    st.markdown(f'<div class="sec">{title}</div>' + (f'<div class="secsub">{sub}</div>' if sub else ''),
                unsafe_allow_html=True)


# ======================================================================= header
logo = logo_png_bytes()
h_left, h_right = st.columns([1, 3])
with h_left:
    if logo:
        st.image(logo, width=260)
with h_right:
    st.markdown('<div style="text-align:right" class="eyebrow">DRILLING REPORT GENERATOR</div>'
                '<div style="text-align:right" class="sub">Upload a Well Report (.xlsm) to build the '
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
        rep, xlsm, written, pdf = process(up.getvalue())
    except WellReportError as e:
        st.error(str(e))
        st.stop()

w, k, df = rep.well, rep.kpis, rep.daily
legs = [lg for lg in rep.legs if lg.start_idx is not None]
lic = w.get('Licence #') or w.get('Well Name') or 'Well'

# ---- downloads first, so they are easy to find
d0, d1, d2 = st.columns(3)
d0.download_button('⬇ Drilling Report (PDF, A4)', pdf, file_name=f'{safe_name(lic)}_Drilling_Report.pdf',
                   mime='application/pdf', type='primary', width='stretch')
d1.download_button('⬇ Drilling Report workbook (.xlsm)', xlsm,
                   file_name=f'{safe_name(lic)}_Drilling_Report.xlsm',
                   mime='application/vnd.ms-excel.sheet.macroEnabled.12', width='stretch')
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

# ---- KPI tiles (same six as the PDF)
tiles = [('Total horizontal', f"{k['total_hz_m']:,.0f}", 'm'), ('Legs drilled', f"{k['legs_drilled']}", ''),
         ('Avg daily progress', f"{k['avg_daily_m']:,.0f}", 'm/day'),
         ('Operational days', f"{k['operational_days']}", 'days'), ('Drilling days', f"{k['drilling_days']}", 'days'),
         ('Non-drilling days', f"{k['non_drilling_days']}", 'days')]
st.write('')
for row in (tiles[:3], tiles[3:]):
    cols = st.columns(3)
    for col, (lab, val, unit) in zip(cols, row):
        col.markdown(f'<div class="kpi"><div class="lab">{lab}</div><div class="val">{val}'
                     f'<span class="unit">{unit}</span></div></div>', unsafe_allow_html=True)

# ---- combined chart: daily metres (bars, left) + measured depth by leg (smooth lines, right)
section('Daily progress & measured depth',
        'Bars: metres drilled per report day (left axis) · Lines: measured depth by leg (right axis)')
x = pd.to_datetime(df['Date'])
xi = ((x - x.iloc[0]).dt.total_seconds() / 86400).to_numpy(float)
dr = pd.to_numeric(df['Drilled (m)'], errors='coerce').fillna(0)
top = max(250, math.ceil(dr.max() / 250) * 250)
fig = make_subplots(specs=[[{'secondary_y': True}]])
fig.add_trace(go.Bar(x=x, y=dr, name='Metres drilled', marker=dict(color=BAR), width=0.7 * 86400000,
                     text=[f'{v:,.0f}' for v in dr], textposition='inside', insidetextanchor='start',
                     textfont=dict(size=11, color=[BAR_TEXT if v > 0 else MUTED for v in dr]),
                     constraintext='none', hovertemplate='%{x|%d %b}: %{y:,.0f} m drilled<extra></extra>'),
              secondary_y=False)
# zero-metre days have no bar, so place their "0" on the baseline
zeros = dr[dr == 0].index
if len(zeros):
    fig.add_trace(go.Scatter(x=x[zeros], y=[top * 0.02] * len(zeros), mode='text', text=['0'] * len(zeros),
                             textfont=dict(size=11, color=MUTED), showlegend=False, hoverinfo='skip'),
                  secondary_y=False)
first = legs[0].start_idx if legs else len(df) - 1
to_md = pd.to_numeric(df['To (m)'], errors='coerce').to_numpy(float)
series = [('Surface / build', NEUTRAL, np.array([v if i <= first else np.nan for i, v in enumerate(to_md)]))]
series += [(f'Leg {lg.number}', leg_color(lg.number),
            pd.to_numeric(df[f'Leg {lg.number}'], errors='coerce').to_numpy(float)) for lg in legs]
md_max = max(np.nanmax(s) for _, _, s in series if np.isfinite(s).any())
ytop = math.ceil(md_max * 1.12 / 500) * 500
pts, seen = [], set()
for name, colr, vals in reversed(series):          # leg start wins over the surface end on the heel point
    for i in range(len(vals)):
        if np.isfinite(vals[i]) and (i, round(vals[i])) not in seen:
            seen.add((i, round(vals[i])))
            pts.append((i, vals[i], f'{vals[i]:,.0f}', colr, name))
placement = {}
for i, v, t, colr, where in label_offsets([p[:4] for p in pts], ytop * 0.045):
    placement[(i, round(v), colr)] = where
for name, colr, vals in series:
    for r in runs(vals):
        sx, sy = pchip(xi[r], vals[r])
        sx_dt = x.iloc[0] + pd.to_timedelta(sx, unit='D')
        fig.add_trace(go.Scatter(x=sx_dt, y=sy, mode='lines', line=dict(color=colr, width=2.5),
                                 showlegend=False, hoverinfo='skip', legendgroup=name), secondary_y=True)
    idx = [i for i in range(len(vals)) if np.isfinite(vals[i])]
    labels = [f'{vals[i]:,.0f}' if (i, round(vals[i]), colr) in placement else '' for i in idx]
    pos = ['bottom center' if placement.get((i, round(vals[i]), colr)) == 'below' else 'top center' for i in idx]
    fig.add_trace(go.Scatter(x=x.iloc[idx], y=vals[idx], mode='markers+text', name=name, legendgroup=name,
                             marker=dict(color=colr, size=8, line=dict(color='white', width=1)),
                             text=labels, textposition=pos, textfont=dict(size=11, color=colr),
                             hovertemplate=f'{name}: ' + '%{y:,.0f} m<extra></extra>'), secondary_y=True)
fig.update_layout(height=520, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor='white', paper_bgcolor='white',
                  font=dict(family='Inter, Arial, sans-serif', size=13, color=INK2), bargap=0.3,
                  legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
                  hovermode='closest')
fig.update_xaxes(showgrid=False, tickformat='%d %b', dtick=86400000, linecolor='#c9d1d9')
fig.update_yaxes(title_text='Metres drilled per day', range=[0, top], dtick=top / 5, gridcolor=GRID,
                 tickformat=',.0f', zeroline=False, secondary_y=False)
fig.update_yaxes(title_text='Measured depth (m)', range=[0, ytop], dtick=500, showgrid=False,
                 tickformat=',.0f', zeroline=False, secondary_y=True)
st.plotly_chart(fig, width='stretch')

# ---- time by section
section('Time by section', f"{k['total_hours']:,.1f} hrs spud to TD")
sec = rep.sections.dropna(subset=['Hours'])
total = sec['Hours'].sum() or 1
fig3 = go.Figure(go.Bar(y=sec['Section'], x=sec['Hours'], orientation='h',
                        marker=dict(color=[section_color(s) for s in sec['Section']]),
                        text=[f'{h:,.1f} h · {h / total:.0%}' for h in sec['Hours']], textposition='outside',
                        textfont=dict(color=INK2), cliponaxis=False,
                        hovertemplate='%{y}: %{x:,.1f} hrs<extra></extra>'))
fig3.update_layout(height=34 * len(sec) + 40, margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor='white',
                   paper_bgcolor='white', font=dict(family='Inter, Arial, sans-serif', size=13, color=INK2),
                   bargap=0.3)
fig3.update_yaxes(autorange='reversed', color=INK)
fig3.update_xaxes(visible=False, range=[0, sec['Hours'].max() * 1.25])
st.plotly_chart(fig3, width='stretch')

# ---- leg summary
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
    show = df[['Day', 'Date', 'From (m)', 'To (m)', 'Drilled (m)', 'Operations']].copy()
    st.dataframe(show, hide_index=True, width='stretch',
                 column_config={'Operations': st.column_config.TextColumn(width='large')})

st.markdown(f'<div class="footer">{FOOTER}</div>', unsafe_allow_html=True)
