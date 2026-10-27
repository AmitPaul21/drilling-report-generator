"""Drilling Report generator - upload a Well Report (.xlsm), download the drilling report PDF."""
from __future__ import annotations

import re

import streamlit as st

from brand import BRAND, FOOTER, INK2, MUTED, logo_png_bytes
from drilling_calc import build_report
from drilling_parser import WellReportError, read_well_report
from drilling_pdf import build_pdf, build_single_pdf
from drilling_single import build_single_report, detect_mode

st.set_page_config(page_title='Drilling Report Generator', page_icon='🛢️', layout='centered')

st.markdown(f"""
<style>
  .eyebrow {{ color:{BRAND}; font-size:0.78rem; font-weight:700; letter-spacing:.05em; }}
  .sub {{ color:{INK2}; font-size:0.92rem; }}
  .footer {{ color:{MUTED}; font-size:0.8rem; text-align:center; border-top:1px solid #c9d9ea;
             padding-top:8px; margin-top:24px; }}
  hr.brand {{ border:none; border-top:2px solid {BRAND}; margin:6px 0 10px 0; }}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def make_pdf(data: bytes, version: str = '2026-10-27-pdf-only'):
    inp = read_well_report(data)
    mode = detect_mode(inp)
    if mode == 'single':
        return build_single_pdf(build_single_report(inp)), mode, inp.well
    return build_pdf(build_report(inp)), mode, inp.well


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_') or 'Well'


logo = logo_png_bytes()
if logo:
    st.image(logo, width=240)
st.markdown('<div class="eyebrow">DRILLING REPORT GENERATOR</div>'
            '<div class="sub">Upload a Well Report (.xlsm) to download its drilling report as a PDF.</div>',
            unsafe_allow_html=True)
st.markdown('<hr class="brand">', unsafe_allow_html=True)

up = st.file_uploader('Well Report', type=['xlsm', 'xlsx'], label_visibility='collapsed')
if up:
    with st.spinner('Building the report…'):
        try:
            pdf, mode, well = make_pdf(up.getvalue())
        except WellReportError as e:
            st.error(str(e))
            st.stop()
    lic = well.get('Licence #') or well.get('Well Name') or 'Well'
    tag = 'Single_Leg' if mode == 'single' else 'Multi_Leg'
    st.download_button('⬇ Download Drilling Report (PDF)', pdf,
                       file_name=f'{safe_name(lic)}_Drilling_Report_{tag}.pdf',
                       mime='application/pdf', type='primary', width='stretch')

st.markdown(f'<div class="footer">{FOOTER}</div>', unsafe_allow_html=True)
