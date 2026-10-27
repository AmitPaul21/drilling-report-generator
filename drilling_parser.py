"""Read the inputs a Belloy Well Report (.xlsm) holds on its `Data` and `DSum1`/`DSum2` sheets."""
from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field

import openpyxl

MAX_LEGS = 10
DAILY_FIRST_ROW, DAILY_LAST_ROW = 8, 71          # DSum1 / DSum2 daily rows


class WellReportError(ValueError):
    """The uploaded file is not a Well Report in the expected layout."""


@dataclass
class Leg:
    number: int
    kop: float | None          # start (kick-off) MD
    td: float | None           # end MD
    reached: dt.datetime | None

    @property
    def length(self) -> float:
        if self.kop is None or self.td is None:
            return 0.0
        return max(0.0, self.td - self.kop)


@dataclass
class DailyRow:
    date: dt.datetime
    time: dt.time | None
    from_md: float | None
    to_md: float | None
    operations: str


@dataclass
class WellInputs:
    well: dict
    spud: dt.datetime | None
    surface_casing_md: float | None
    surface_casing_reached: dt.datetime | None
    heel_md: float | None
    heel_reached: dt.datetime | None
    td_md: float | None
    td_reached: dt.datetime | None
    legs: list[Leg]
    daily: list[DailyRow]
    warnings: list[str] = field(default_factory=list)
    drill_out_surface: dt.datetime | None = None      # Data row 27
    int_casing_md: float | None = None                # Data row 31
    int_casing_reached: dt.datetime | None = None
    legs_declared: int | None = None                  # Data D39 'Total # of Legs'


# ---------------------------------------------------------------- helpers
def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(',', '').strip())
        except ValueError:
            return None
    return None


def _date(v):
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime.combine(v, dt.time())
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
        return dt.datetime(1899, 12, 30) + dt.timedelta(days=float(v))
    return None


def _time(v):
    if isinstance(v, dt.time):
        return v
    if isinstance(v, dt.datetime):
        return v.time()
    if isinstance(v, dt.timedelta):
        return (dt.datetime.min + v).time()
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1:
        return (dt.datetime.min + dt.timedelta(days=float(v))).time().replace(microsecond=0)
    if isinstance(v, str) and ':' in v:
        try:
            h, m = v.strip().split(':')[:2]
            return dt.time(int(h) % 24, int(m))
        except ValueError:
            return None
    return None


def _stamp(d, t):
    d, t = _date(d), _time(t)
    if d is None or t is None:
        return None
    return dt.datetime.combine(d.date(), t)


def _text(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _grid(ws, max_row, max_col):
    """Read a sheet block into {(row, col): value} (1-based)."""
    out = {}
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True), 1):
        for c, v in enumerate(row, 1):
            if v is not None:
                out[(r, c)] = v
    return out


# ---------------------------------------------------------------- main entry
def read_well_report(file_bytes: bytes) -> WellInputs:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise WellReportError(f'Could not open the file as an Excel workbook ({exc}).') from exc
    try:
        if 'Data' not in wb.sheetnames or 'DSum1' not in wb.sheetnames:
            raise WellReportError('This workbook has no "Data" and "DSum1" sheets, so it is not a Well Report.')
        D = _grid(wb['Data'], 60, 22)
        g = lambda ref: D.get(_rc(ref))  # noqa: E731
        if not str(g('B40') or '').startswith('Hz Leg 1') or 'Total Depth' not in str(g('B50') or ''):
            raise WellReportError('The "Data" sheet layout does not match the Well Report template '
                                  '(expected "Hz Leg 1 Interval" in B40 and "Total Depth" in B50).')

        warnings: list[str] = []
        well = {
            'Licensee': _text(g('C5')), 'Well Name': _text(g('C6')), 'UWI': _text(g('C7')),
            'Licence #': _text(g('C8')), 'AFE #': _text(g('C9')), 'Province': _text(g('I7')),
            'Field': _text(g('I10')), 'Target Zone': _text(g('I9')), 'Drilling Contractor': _text(g('C12')),
            'Surface Location': _text(g('I14')), 'Bottom Hole Location': _text(g('I15')),
            'Ground Elevation (m)': _num(g('K5')), 'KB Elevation (m)': _num(g('K6')),
        }
        legs = []
        for n in range(1, MAX_LEGS + 1):
            r = 39 + n
            legs.append(Leg(n, _num(g(f'C{r}')), _num(g(f'E{r}')), _stamp(g(f'I{r}'), g(f'K{r}'))))
        legs = [lg for lg in legs if lg.kop or lg.td]

        daily: list[DailyRow] = []
        for sheet in ('DSum1', 'DSum2'):
            if sheet not in wb.sheetnames:
                continue
            S = _grid(wb[sheet], DAILY_LAST_ROW, 15)
            for r in range(DAILY_FIRST_ROW, DAILY_LAST_ROW + 1):
                d, to = _date(S.get((r, 1))), _num(S.get((r, 10)))
                if d is None and to is None:
                    continue
                if d is None:
                    warnings.append(f'{sheet} row {r}: depth {to:g} m has no date and was skipped.')
                    continue
                daily.append(DailyRow(d, _time(S.get((r, 6))), _num(S.get((r, 8))), to, _text(S.get((r, 15)))))
        if not daily:
            raise WellReportError('No daily progress rows were found on "DSum1" (date in column A, TO depth in column J).')
        daily.sort(key=lambda x: x.date)

        return WellInputs(
            well=well, spud=_stamp(g('I20'), g('K20')),
            surface_casing_md=_num(g('C24')), surface_casing_reached=_stamp(g('I24'), g('K24')),
            heel_md=_num(g('C32')), heel_reached=_stamp(g('I32'), g('K32')),
            td_md=_num(g('C50')), td_reached=_stamp(g('I50'), g('K50')),
            legs=legs, daily=daily, warnings=warnings,
            drill_out_surface=_stamp(g('I27'), g('K27')),
            int_casing_md=_num(g('C31')), int_casing_reached=_stamp(g('I31'), g('K31')),
            legs_declared=int(_num(g('D39'))) if _num(g('D39')) else None,
        )
    finally:
        wb.close()


def _rc(ref: str):
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
    col, row = coordinate_from_string(ref)
    return row, column_index_from_string(col)
