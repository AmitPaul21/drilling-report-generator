"""Multi-leg drilling report calculations.

* a leg is drilled from the previous leg's "reached" time (the heel time for Leg 1) to its own;
* its depth at the end of a report day is the TD if it was reached that day, else the TO depth
  when that lies on the leg, else the next day's FROM depth (when TO still shows the old leg's TD);
* daily metres = hole drilled down to the heel point + every active leg's progress that day;
* a report time of 00:00 means the report closes at midnight (end of that day).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from drilling_parser import WellInputs, active_hours, idle_days

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
        stamp = dt.datetime.combine(d.date.date(), t)
        if t == dt.time(0, 0):                                   # 00:00 = report closes at midnight
            stamp += dt.timedelta(days=1)
        rows.append({'Report Time': stamp, 'Date': d.date.date(),
                     'From (m)': frm, 'To (m)': d.to_md, 'Operations': d.operations})
        if d.to_md is not None:
            prev_to = d.to_md
    df = pd.DataFrame(rows)
    T, Nd = df['Report Time'].tolist(), df['To (m)'].tolist()
    Fm = df['From (m)'].tolist()
    n_rows = len(df)
    has_to = [v is not None and pd.notna(v) for v in Nd]
    last_t = T[-1] if T else None

    def num(v):
        return None if v is None or pd.isna(v) else float(v)

    # ---- when each leg is being drilled: from the previous leg's "reached" time to its own
    heel_md = inp.heel_md or (inp.legs[0].kop if inp.legs else None)
    starts, ends = [], []
    t_prev = inp.heel_reached
    if t_prev is None and inp.legs and inp.legs[0].kop:         # no heel time: first report past the KOP
        k = next((i for i in range(n_rows) if has_to[i] and Nd[i] >= inp.legs[0].kop), None)
        t_prev = (T[k - 1] if k else T[0] - dt.timedelta(seconds=1)) if k is not None else None
    for lg in inp.legs:
        reached = lg.reached
        if reached is None and t_prev is not None and lg.td:    # no time: first report at the leg's TD
            k = next((i for i in range(n_rows) if T[i] > t_prev and has_to[i] and abs(Nd[i] - lg.td) < 0.5), None)
            reached = T[k] if k is not None else None
        starts.append(t_prev)
        ends.append(reached)
        t_prev = reached if reached is not None else None

    # ---- each leg's depth at the end of every report day, and the metres drilled that day
    depth = {lg.number: [None] * n_rows for lg in inp.legs}
    drilled = []
    for i in range(n_rows):
        lo = T[i - 1] if i else None
        frm, to = num(Fm[i]), num(Nd[i])
        nxt = num(Fm[i + 1]) if i + 1 < n_rows else None
        tot = 0.0
        # surface / build hole down to the heel point
        if to is not None and frm is not None and (inp.heel_reached is None or lo is None or lo < inp.heel_reached):
            cap = heel_md if heel_md is not None and inp.legs else to
            tot += max(0.0, min(to, cap) - min(frm, cap))
        finished_td = {lg.td for lg, e in zip(inp.legs, ends) if e is not None and (lo is None or e > lo) and e <= T[i]}
        for lg, a, e in zip(inp.legs, starts, ends):
            if a is None or not lg.kop or a > T[i] or (e is not None and lo is not None and e <= lo):
                continue                                          # leg not being drilled on this day
            before = depth[lg.number][i - 1] if i else None
            before = lg.kop if before is None else before
            if e is not None and e <= T[i]:
                d_end = lg.td                                     # leg reached its TD on this day
            elif to is not None and lg.kop < to <= (lg.td or 1e9) and to not in finished_td:
                d_end = to                                        # TO depth is on this leg
            elif nxt is not None and lg.kop <= nxt <= (lg.td or 1e9):
                d_end = nxt                                       # TO shows the old leg's TD: use next FROM
            else:
                d_end = before
            d_end = max(d_end, before)
            depth[lg.number][i] = d_end
            tot += d_end - before
        drilled.append(tot if (to is not None or tot) else None)

    # ---- leg rows for the chart: kick-off on the day before the first metres, then daily depth
    legs: list[LegResult] = []
    for lg, a, e in zip(inp.legs, starts, ends):
        vals = depth[lg.number]
        prog = [i for i in range(n_rows) if vals[i] is not None and vals[i] > (vals[i - 1] if i and vals[i - 1] is not None else lg.kop)]
        if not prog:
            df[f'Leg {lg.number}'] = [None] * n_rows
            legs.append(LegResult(lg.number, lg.kop, lg.td, lg.length, lg.reached, None, None, False, None))
            if lg.kop:
                warnings.append(f'Leg {lg.number}: no drilling found for it on the daily progress rows.')
            continue
        first = prog[0]
        s_idx = max(first - 1, 0)
        col = [None] * n_rows
        col[s_idx] = lg.kop
        for i in range(first, n_rows):
            if vals[i] is not None:
                col[i] = vals[i]
        e_idx = max(i for i in range(n_rows) if col[i] is not None)
        df[f'Leg {lg.number}'] = col
        complete = e is not None and last_t is not None and e <= last_t
        legs.append(LegResult(lg.number, lg.kop, lg.td, lg.length, lg.reached, s_idx, e_idx, complete, None))

    # ---- cross-check against the Well Report's own DRILLED column
    diffs = [f'{df.at[i, "Date"]:%d %b} ({d.drilled:,.0f} vs {drilled[i]:,.0f})'
             for i, d in enumerate(inp.daily)
             if d.drilled is not None and drilled[i] is not None and abs(d.drilled - drilled[i]) > 10]
    if diffs:
        warnings.append('Daily metres here differ from the DRILLED column on DSum1 for: ' + ', '.join(diffs)
                        + '. This report counts every leg drilled that day (Well Report value vs this report).')
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
    idle = idle_days(df['Date'])
    sec = []
    for name, a, b in marks:
        sec.append({'Section': name, 'Start': a, 'End': b, 'Hours': active_hours(a, b, idle)})
    sections = pd.DataFrame(sec)
    for lg, h in zip(legs, sections['Hours'].iloc[2:]):
        lg.hours = None if pd.isna(h) else h

    # ---- KPIs (same definitions as the template's KPI boxes)
    dr = pd.to_numeric(df['Drilled (m)'], errors='coerce')
    drilling_days = int((dr > 0).sum())
    dates = pd.to_datetime(df['Date'])
    kpis = {
        'total_hz_m': sum(lg.length for lg in legs),
        'operational_days': int(dates.dt.normalize().nunique()),
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
