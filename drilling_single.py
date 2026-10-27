"""Single-leg drilling report: one well bore split into Surface, Intermediate / Build and Lateral.

Mirrors the template's "Drilling Report - Single Leg" tab:
* Surface = first FROM depth to the surface casing depth (Data C24); spud -> drill-out of surface casing
* Int / Build = surface casing -> heel point (C32, else intermediate casing C31, else TD); drill-out -> heel time
* Lateral = heel point -> TD (C50), only when TD is deeper than the heel; heel time -> TD time
* section days = report days whose FROM depth falls inside the section (as in the template)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from drilling_parser import WellInputs

END_OF_DAY = dt.time(23, 59)
SECTIONS = ('Surface', 'Int / Build', 'Lateral')


@dataclass
class SingleReport:
    well: dict
    daily: pd.DataFrame
    sections: pd.DataFrame      # Section, From (m), To (m), Length (m), Days, Start, End, Hours
    kpis: dict
    milestones: dict
    warnings: list


def detect_mode(inp: WellInputs) -> str:
    """'multi' when the report has two or more drilled legs, otherwise 'single'."""
    drilled = sum(1 for lg in inp.legs if lg.length > 0)
    if drilled >= 2 or (inp.legs_declared or 0) >= 2:
        return 'multi'
    return 'single'


def build_single_report(inp: WellInputs) -> SingleReport:
    warnings = list(inp.warnings)
    rows, prev_to = [], None
    for i, d in enumerate(inp.daily):
        t = d.time or END_OF_DAY
        if d.time is None:
            warnings.append(f'{d.date:%d-%b-%Y}: no report time entered, assumed 23:59.')
        frm = d.from_md if d.from_md is not None else (0.0 if i == 0 else prev_to)
        rows.append({'Report Time': dt.datetime.combine(d.date.date(), t), 'Date': d.date.date(),
                     'From (m)': frm, 'To (m)': d.to_md, 'Operations': d.operations})
        if d.to_md is not None:
            prev_to = d.to_md
    df = pd.DataFrame(rows)
    to = pd.to_numeric(df['To (m)'], errors='coerce')
    frm = pd.to_numeric(df['From (m)'], errors='coerce')
    df['Drilled (m)'] = (to - frm).clip(lower=0)
    df['Day'] = range(1, len(df) + 1)

    # ---- section depth limits
    start_md = float(frm.iloc[0]) if len(df) and pd.notna(frm.iloc[0]) else 0.0
    surf = inp.surface_casing_md
    heel = inp.heel_md or inp.int_casing_md or inp.td_md
    td = inp.td_md or (float(to.max()) if to.notna().any() else None)
    heel_time = inp.heel_reached or inp.int_casing_reached or inp.td_reached
    drill_out = inp.drill_out_surface or inp.surface_casing_reached
    limits = [('Surface', start_md, surf, inp.spud, drill_out),
              ('Int / Build', surf, heel, drill_out, heel_time),
              ('Lateral', heel, td if (td and heel and td > heel) else None, heel_time,
               inp.td_reached if (td and heel and td > heel) else None)]

    sec_rows = []
    for k, (name, a, b, t0, t1) in enumerate(limits):
        if a is None or b is None or b <= a:
            sec_rows.append({'Section': name, 'From (m)': a, 'To (m)': b, 'Length (m)': None, 'Days': None,
                             'Start': t0, 'End': t1, 'Hours': None})
            continue
        last = name == 'Lateral'
        days = int(((frm >= a) & ((frm <= b) if last else (frm < b))).sum())
        hrs = (t1 - t0).total_seconds() / 3600 if t0 and t1 else None
        sec_rows.append({'Section': name, 'From (m)': a, 'To (m)': b, 'Length (m)': b - a, 'Days': days,
                         'Start': t0, 'End': t1, 'Hours': hrs})
    sections = pd.DataFrame(sec_rows)
    if surf is None:
        warnings.append('Surface casing depth (Data C24) is blank, so the Surface section could not be split.')
    if heel is None:
        warnings.append('No heel point, intermediate casing or TD depth entered (Data C32 / C31 / C50).')

    # ---- which section each report day ends in (for the chart bands)
    def sec_of(v):
        if pd.isna(v):
            return None
        if surf is not None and v <= surf:
            return 'Surface'
        if heel is not None and v <= heel:
            return 'Int / Build'
        return 'Lateral'
    df['Section'] = [sec_of(v) for v in to]

    dr = df['Drilled (m)']
    drilling_days = int((dr > 0).sum())
    dates = pd.to_datetime(df['Date'])
    lat = sections.loc[sections['Section'] == 'Lateral', 'Length (m)'].iloc[0]
    kpis = {
        'total_depth_m': float(to.max()) if to.notna().any() else 0.0,
        'lateral_m': float(lat) if pd.notna(lat) else 0.0,
        'operational_days': int((dates.max() - dates.min()).days + 1) if len(dates) else 0,
        'drilling_days': drilling_days,
        'non_drilling_days': int((dr == 0).sum()),
        'avg_daily_m': float(dr[dr > 0].sum() / drilling_days) if drilling_days else 0.0,
        'operational_hours': float(pd.to_numeric(sections['Hours'], errors='coerce').sum(skipna=True)),
        'total_drilled_m': float(dr.sum()),
    }
    milestones = {'Spud': inp.spud, 'Surface Casing': inp.surface_casing_reached, 'Drill Out': drill_out,
                  'Heel Point': heel_time, 'Total Depth': inp.td_reached}
    return SingleReport(inp.well, df, sections, kpis, milestones, warnings)
