"""Multi-leg drilling report calculations.

Mirrors the formulas on the template's "Drilling Report - Multi Leg" tab (V2.2):
* a leg's first plotted day is the day its heel / kick-off point applies, its last day is the
  report that covers its "reached" time (or, without a time, the first day its TO depth is hit);
* a sidetrack drilled on the same day the previous leg finished starts on the day before;
  otherwise it starts the day before the TO depth first changes after the previous leg ended;
* daily metres after Leg 1 starts = the sum of every active leg's progress that day.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from drilling_parser import WellInputs

END_OF_DAY = dt.time(23, 59)


@dataclass
class LegResult:
    number: int
    kop: float | None
    td: float | None
    length: float
    reached: dt.datetime | None
    start_idx: int | None
    end_idx: int | None
    complete: bool
    hours: float | None


@dataclass
class DrillingReport:
    well: dict
    daily: pd.DataFrame          # one row per report day
    legs: list[LegResult]
    sections: pd.DataFrame       # timing per section
    kpis: dict
    milestones: dict
    warnings: list[str]


def build_report(inp: WellInputs) -> DrillingReport:
    warnings = list(inp.warnings)

    # ---- daily table (template columns L, M, N, O)
    rows, prev_to = [], None
    for i, d in enumerate(inp.daily):
        t = d.time
        if t is None:
            t = END_OF_DAY
            warnings.append(f'{d.date:%d-%b-%Y}: no report time entered, assumed 23:59.')
        frm = d.from_md
        if frm is None:
            frm = 0.0 if i == 0 else prev_to
        rows.append({'Report Time': dt.datetime.combine(d.date.date(), t), 'Date': d.date.date(),
                     'From (m)': frm, 'To (m)': d.to_md, 'Operations': d.operations})
        if d.to_md is not None:
            prev_to = d.to_md
    df = pd.DataFrame(rows)
    L, Nd = df['Report Time'].tolist(), df['To (m)'].tolist()
    n_rows = len(df)
    has_to = [v is not None and pd.notna(v) for v in Nd]

    def first_time(t, lo):
        return next((i for i in range(max(lo, 0), n_rows) if L[i] >= t), None)

    def first_depth(md, lo):
        return next((i for i in range(max(lo, 0), n_rows) if has_to[i] and Nd[i] >= md), None)

    last_idx = max((i for i in range(n_rows) if has_to[i]), default=None)

    # ---- leg start / end rows
    legs: list[LegResult] = []
    prev = None
    for lg in inp.legs:
        start = None
        if lg.kop:
            if prev is None:                                   # Leg 1: heel point
                start = first_time(inp.heel_reached, 0) if inp.heel_reached else first_depth(lg.kop, 0)
            elif prev.complete:
                p = prev.end_idx
                same_day = has_to[p] and prev.td is not None and abs(Nd[p] - prev.td) > 0.5
                if same_day:
                    start = p - 1
                else:
                    chg = next((i for i in range(p + 1, n_rows)
                                if has_to[i] and has_to[i - 1] and Nd[i] != Nd[i - 1]), None)
                    start = None if chg is None else chg - 1
                if start is not None:
                    start = max(start, 0)
        found = None
        if start is not None:
            if lg.reached:
                found = first_time(lg.reached, start)
            elif lg.td:
                found = first_depth(lg.td, start)
        end = (found if found is not None else last_idx) if start is not None else None
        res = LegResult(lg.number, lg.kop, lg.td, lg.length, lg.reached, start, end, found is not None, None)
        legs.append(res)
        prev = res if start is not None else (prev if prev and not prev.complete else res)
        if start is None and lg.kop:
            warnings.append(f'Leg {lg.number}: could not place it on the daily progress rows '
                            f'(not drilled yet, or previous leg has no end time/depth).')

    # ---- per-leg depth series
    for lg in legs:
        col = f'Leg {lg.number}'
        vals = [None] * n_rows
        if lg.start_idx is not None:
            for i in range(lg.start_idx, lg.end_idx + 1):
                if i == lg.start_idx:
                    vals[i] = lg.kop
                elif i == lg.end_idx and lg.complete:
                    vals[i] = lg.td
                else:
                    vals[i] = Nd[i] if has_to[i] else None
        df[col] = vals
    leg_cols = [f'Leg {lg.number}' for lg in legs]

    # ---- daily metres drilled
    s1 = legs[0].start_idx if legs else None
    drilled = []
    for i in range(n_rows):
        frm, to = df.at[i, 'From (m)'], Nd[i]
        if not has_to[i] or frm is None or pd.isna(frm):
            drilled.append(None); continue
        active = [c for c in leg_cols if df.at[i, c] is not None and pd.notna(df.at[i, c])]
        if s1 is None or i <= s1 or not active:
            drilled.append(max(0.0, to - frm))
        else:
            tot = 0.0
            for c in active:
                pv = df.at[i - 1, c] if i > 0 else None
                if pv is not None and pd.notna(pv):
                    tot += df.at[i, c] - pv
            drilled.append(tot)
    df['Drilled (m)'] = drilled
    df['Template Drilled (m)'] = [None if not has_to[i] or pd.isna(df.at[i, 'From (m)']) else max(0.0, Nd[i] - df.at[i, 'From (m)'])
                                  for i in range(n_rows)]
    df['Day'] = range(1, n_rows + 1)

    # ---- section timing
    marks = [('Surface', inp.spud, inp.surface_casing_reached),
             ('Int / Build', inp.surface_casing_reached, inp.heel_reached)]
    t_prev = inp.heel_reached
    for lg in legs:
        marks.append((f'Leg {lg.number}', t_prev, lg.reached))
        t_prev = lg.reached
    sec = []
    for name, a, b in marks:
        hrs = (b - a).total_seconds() / 3600 if a and b else None
        sec.append({'Section': name, 'Start': a, 'End': b, 'Hours': hrs})
    sections = pd.DataFrame(sec)
    for lg, h in zip(legs, sections['Hours'].iloc[2:]):
        lg.hours = None if pd.isna(h) else h

    # ---- KPIs (same definitions as the template's KPI boxes)
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce')
    drilling_days = int((dr > 0).sum())
    dates = pd.to_datetime(df['Date'])
    kpis = {
        'total_hz_m': sum(lg.length for lg in legs),
        'operational_days': int((dates.max() - dates.min()).days + 1) if len(dates) else 0,
        'drilling_days': drilling_days,
        'non_drilling_days': int((dr == 0).sum()),
        'avg_daily_m': float(dr[dr > 0].sum() / drilling_days) if drilling_days else 0.0,
        'legs_drilled': sum(1 for lg in legs if lg.length > 0),
        'total_drilled_m': float(dr.sum()),
        'total_hours': float(sections['Hours'].sum(skipna=True)),
        'td_md': inp.td_md,
    }
    milestones = {'Spud': inp.spud, 'Surface Casing': inp.surface_casing_reached,
                  'Heel Point': inp.heel_reached, 'Total Depth': inp.td_reached}
    return DrillingReport(inp.well, df, legs, sections, kpis, milestones, warnings)
