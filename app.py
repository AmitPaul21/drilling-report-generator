"""Drilling Report generator - upload a Well Report (.xlsm), get the multi-leg drilling report."""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from drilling_calc import build_report
from drilling_export import fill_template
from drilling_parser import WellReportError, read_well_report
from drilling_pdf import build_pdf

st.set_page_config(page_title='Drilling Report Generator', page_icon='🛢️', layout='wide')

# ---- validated categorical order (identity follows the leg number, never its rank)
LEG_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
LEG_DASH = ['solid'] * 8 + ['dash', 'dash']          # legs 9-10 reuse slots 1-2 with a dash
NEUTRAL = '#8a8984'
BAR = '#6da7ec'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e7e6e2'


def leg_color(n: int) -> str:
    return LEG_COLORS[(n - 1) % len(LEG_COLORS)]


def base_layout(fig: go.Figure, height: int, y_title: str):
    fig.update_layout(
        height=height, margin=dict(l=10, r=70, t=10, b=10), plot_bgcolor='white', paper_bgcolor='white',
        font=dict(family='Inter, Arial, sans-serif', size=13, color=INK2),
        hovermode='x unified', hoverlabel=dict(bgcolor='white', font_color=INK),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0, font_color=INK2),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickformat='%d-%b', ticks='outside', tickcolor=GRID)
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False, tickformat=',.0f')
    return fig


@st.cache_data(show_spinner=False)
def process(data: bytes):
    rep = build_report(read_well_report(data))
    xlsm, written = fill_template(data)
    pdf = build_pdf(rep)
    return rep, xlsm, written, pdf


def fmt_dt(v):
    return '—' if v is None or pd.isna(v) else pd.Timestamp(v).strftime('%d-%b-%Y %H:%M')


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_') or 'Well'


# ======================================================================= UI
st.title('Drilling Report Generator')
st.caption('Upload a Well Report (.xlsm). The app reads its **Data** and **DSum1** sheets, '
           'builds the multi-leg drilling report, and fills the Drilling Report template for download.')

up = st.file_uploader('Well Report', type=['xlsm', 'xlsx'], label_visibility='collapsed')
if not up:
    st.info('Waiting for a Well Report file.')
    st.stop()

with st.spinner('Reading the well report…'):
    try:
        rep, xlsm, written, pdf = process(up.getvalue())
    except WellReportError as e:
        st.error(str(e))
        st.stop()

w, k, df = rep.well, rep.kpis, rep.daily
legs = [lg for lg in rep.legs if lg.start_idx is not None]

# ---- header
st.subheader(w.get('Well Name') or 'Unnamed well')
h1, h2, h3, h4 = st.columns(4)
h1.markdown(f"**Operator**  \n{w.get('Licensee') or '—'}")
h2.markdown(f"**UWI**  \n{w.get('UWI') or '—'}")
h3.markdown(f"**Surface location**  \n{w.get('Surface Location') or '—'}")
h4.markdown(f"**Spud → TD**  \n{fmt_dt(rep.milestones['Spud'])} → {fmt_dt(rep.milestones['Total Depth'])}")

for msg in rep.warnings:
    st.warning(msg)

# ---- KPIs
c = st.columns(6)
c[0].metric('Total horizontal', f"{k['total_hz_m']:,.0f} m")
c[1].metric('Legs drilled', k['legs_drilled'])
c[2].metric('Operational days', k['operational_days'])
c[3].metric('Drilling days', k['drilling_days'])
c[4].metric('Non-drilling days', k['non_drilling_days'])
c[5].metric('Avg daily progress', f"{k['avg_daily_m']:,.0f} m/day")

# ---- depth by leg
st.markdown('#### Measured depth by leg')
x = pd.to_datetime(df['Date'])
fig = go.Figure()
first_leg_idx = legs[0].start_idx if legs else len(df) - 1
fig.add_trace(go.Scatter(x=x[:first_leg_idx + 1], y=df['To (m)'][:first_leg_idx + 1], name='Surface / build',
                         mode='lines+markers', line=dict(color=NEUTRAL, width=2), marker=dict(size=8),
                         hovertemplate='%{y:,.0f} m'))
for lg in legs:
    col = f'Leg {lg.number}'
    s = pd.to_numeric(df[col], errors='coerce')
    fig.add_trace(go.Scatter(x=x, y=s, name=col, mode='lines+markers', connectgaps=False,
                             line=dict(color=leg_color(lg.number), width=2, dash=LEG_DASH[lg.number - 1]),
                             marker=dict(size=8), hovertemplate='%{y:,.0f} m'))
    last = s.last_valid_index()
    if last is not None and len(legs) <= 4:          # direct labels only when they can't collide
        fig.add_annotation(x=x[last], y=s[last], text=col, showarrow=False, xanchor='left', xshift=8,
                           font=dict(color=INK2, size=12))
base_layout(fig, 380, 'MD (m)')
st.plotly_chart(fig, width='stretch')

# ---- daily metres
st.markdown('#### Daily metres drilled')
fig2 = go.Figure(go.Bar(x=x, y=df['Drilled (m)'], marker=dict(color=BAR, cornerradius=4),
                        name='Drilled', hovertemplate='%{y:,.0f} m<extra></extra>'))
base_layout(fig2, 260, 'Metres')
fig2.update_layout(showlegend=False, bargap=0.25, hovermode='closest')
st.plotly_chart(fig2, width='stretch')
st.caption(f"Total drilled {k['total_drilled_m']:,.0f} m. On days where one leg finished and the next "
           'started, the day counts the progress on both legs.')

# ---- leg summary + section time
left, right = st.columns([3, 2])
with left:
    st.markdown('#### Legs')
    leg_tbl = pd.DataFrame([{
        'Leg': f'Leg {lg.number}', 'Kick-off (m)': lg.kop, 'End MD (m)': lg.td, 'Length (m)': lg.length,
        'Reached': fmt_dt(lg.reached), 'Leg time (hrs)': None if lg.hours is None else round(lg.hours, 2),
        'Status': 'Complete' if lg.complete else ('In progress' if lg.start_idx is not None else 'Not started'),
    } for lg in rep.legs])
    st.dataframe(leg_tbl, hide_index=True, width='stretch',
                 column_config={c_: st.column_config.NumberColumn(format='%,.0f')
                                for c_ in ['Kick-off (m)', 'End MD (m)', 'Length (m)']}
                 | {'Leg time (hrs)': st.column_config.NumberColumn(format='%.2f')})
with right:
    st.markdown('#### Time by section')
    sec = rep.sections.dropna(subset=['Hours'])
    colors = [leg_color(int(s.split()[1])) if s.startswith('Leg') else NEUTRAL for s in sec['Section']]
    fig3 = go.Figure(go.Bar(y=sec['Section'], x=sec['Hours'], orientation='h', marker=dict(color=colors, cornerradius=4),
                            text=[f'{h:,.1f} h' for h in sec['Hours']], textposition='outside',
                            textfont=dict(color=INK2), hovertemplate='%{y}: %{x:,.1f} hrs<extra></extra>'))
    fig3.update_layout(height=40 * len(sec) + 60, margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor='white',
                       paper_bgcolor='white', font=dict(family='Inter, Arial, sans-serif', size=13, color=INK2))
    fig3.update_yaxes(autorange='reversed')
    fig3.update_xaxes(gridcolor=GRID, title_text='Hours', zeroline=False, range=[0, sec['Hours'].max() * 1.2])
    st.plotly_chart(fig3, width='stretch')
    st.caption(f"Total {k['total_hours']:,.1f} hrs spud to TD. Each leg runs from the previous milestone, "
               'so trips and sidetrack set-up count toward the next leg.')

# ---- daily operations
with st.expander('Daily progress and operations', expanded=False):
    show = df[['Day', 'Date', 'From (m)', 'To (m)', 'Drilled (m)', 'Operations']].copy()
    st.dataframe(show, hide_index=True, width='stretch',
                 column_config={'Operations': st.column_config.TextColumn(width='large')})

# ---- downloads
st.markdown('#### Downloads')
lic = w.get('Licence #') or w.get('Well Name') or 'Well'
d0, d1, d2 = st.columns(3)
d0.download_button('Drilling Report (.pdf)', pdf, file_name=f'{safe_name(lic)}_Drilling_Report.pdf',
                   mime='application/pdf', type='primary', width='stretch')
d1.download_button('Drilling Report workbook (.xlsm)', xlsm, file_name=f'{safe_name(lic)}_Drilling_Report.xlsm',
                   mime='application/vnd.ms-excel.sheet.macroEnabled.12', width='stretch')
export = df.drop(columns=['Report Time']).copy()
d2.download_button('Daily data (.csv)', export.to_csv(index=False).encode(), file_name=f'{safe_name(lic)}_daily.csv',
                   mime='text/csv', width='stretch')
st.caption(f"Workbook: the V2.2 template with {written.get('Data', 0)} Data and {written.get('DSum1', 0)} DSum1 "
           'inputs copied from the upload. Excel recalculates the Multi Leg tab when it opens.')
