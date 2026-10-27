"""Fill the bundled Drilling Report template with a Well Report's typed inputs.

Only the `Data` and `DSum1` sheets are written, and only cells the user typed (constants) -
every formula in the uploaded report is left to the template. The workbook is edited at the
XML level so charts, KPI boxes and VBA macros survive (openpyxl would drop them on save)."""
from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from pathlib import Path

import openpyxl
from lxml import etree
from openpyxl.utils import column_index_from_string as ci

HERE = Path(__file__).resolve().parent
# newest template first; the Multi Leg tab is brought up to date in code (see _refine_multileg)
TEMPLATE = next((HERE / n for n in ('Field_Sheets_Template_Updated_V2.2.xlsm', 'Drilling_Report_Template_V2.2.xlsm')
                 if (HERE / n).exists()), HERE / 'Drilling_Report_Template_V2.2.xlsm')
MULTI_LEG = 'Drilling Report - Multi Leg'
SHEETS = ('Data', 'DSum1')
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
N = '{%s}' % NS
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def _constants(source, sheets=SHEETS):
    """{sheet: {coord: value}} of non-formula cells."""
    wb = openpyxl.load_workbook(source, read_only=True, data_only=False, keep_links=False)
    try:
        out = {}
        for name in sheets:
            vals = {}
            for row in wb[name].iter_rows():
                for c in row:
                    v = getattr(c, 'value', None)
                    if v is None or (isinstance(v, str) and v.startswith('=')):
                        continue
                    vals[c.coordinate] = v
            out[name] = vals
        return out
    finally:
        wb.close()


class _SheetXML:
    def __init__(self, xml: bytes):
        self.root = etree.fromstring(xml)
        self.sd = self.root.find(N + 'sheetData')
        self.rows = {int(r.get('r')): r for r in self.sd.findall(N + 'row')}

    @staticmethod
    def _split(ref):
        m = re.match(r'([A-Z]+)(\d+)$', ref)
        return m.group(1), int(m.group(2))

    def _row(self, r):
        if r in self.rows:
            return self.rows[r]
        el = etree.Element(N + 'row', r=str(r))
        before = [k for k in self.rows if k < r]
        if before:
            self.rows[max(before)].addnext(el)
        else:
            self.sd.insert(0, el)
        self.rows[r] = el
        return el

    def _cell(self, ref):
        col, r = self._split(ref)
        row = self._row(r)
        for c in row.findall(N + 'c'):
            cc, _ = self._split(c.get('r'))
            if cc == col:
                return c
            if ci(cc) > ci(col):
                el = etree.Element(N + 'c', r=ref)
                c.addprevious(el)
                return el
        return etree.SubElement(row, N + 'c', r=ref)

    def set_value(self, ref, v):
        c = self._cell(ref)
        for ch in list(c):
            c.remove(ch)
        for a in ('t', 'cm', 'vm'):
            c.attrib.pop(a, None)
        if isinstance(v, str):
            c.set('t', 'inlineStr')
            t = etree.SubElement(etree.SubElement(c, N + 'is'), N + 't')
            t.text = v
            if v != v.strip():
                t.set(XML_SPACE, 'preserve')
            return
        if isinstance(v, bool):
            c.set('t', 'b')
            etree.SubElement(c, N + 'v').text = '1' if v else '0'
            return
        if isinstance(v, dt.datetime):
            d = v - dt.datetime(1899, 12, 30)
            v = d.days + d.seconds / 86400
        elif isinstance(v, dt.date):
            v = (v - dt.date(1899, 12, 30)).days
        elif isinstance(v, dt.time):
            v = (v.hour * 3600 + v.minute * 60 + v.second) / 86400
        elif isinstance(v, dt.timedelta):
            v = v.total_seconds() / 86400
        etree.SubElement(c, N + 'v').text = repr(float(v)) if isinstance(v, float) else str(v)

    def set_formula(self, ref, f, array=False):
        c = self._cell(ref)
        for ch in list(c):
            c.remove(ch)
        for a in ('t', 'cm', 'vm'):
            c.attrib.pop(a, None)
        fe = etree.SubElement(c, N + 'f')
        fe.text = f
        if array:
            fe.set('t', 'array')
            fe.set('ref', ref)

    def to_bytes(self):
        return etree.tostring(self.root, xml_declaration=True, encoding='UTF-8', standalone=True)


_TEMPLATE_CONSTANTS = None


def _refine_multileg(sheet: _SheetXML):
    """Leg placement + daily metres on the Multi Leg tab (same rules as drilling_calc):
    a sidetrack drilled the same day the previous leg ended starts the day before; otherwise it
    starts the day before the TO depth first changes; daily metres sum each leg's progress."""
    def first_change(p):
        return ('MIN(IF(IFERROR($N$3:$N$65<>$N$2:$N$64,FALSE)*(ROW($N$3:$N$65)>' + p + '),ROW($N$3:$N$65)))')
    for k in range(5, 14):
        p = f'$AO${k-1}'
        sheet.set_formula(f'AD{k}',
            f'IF(AND(N($AA${k})>0,N({p})>0),'
            f'IF(IFERROR(ABS(INDEX($N:$N,{p})-$AB${k-1})>0.5,FALSE),{p}-1,'
            f'IFERROR(1/(1/{first_change(p)}),NA())-1),NA())', array=True)
    sheet.set_formula('M2', 'IF(DSum1!H8="",IF(DSum1!J8="",NA(),0),DSum1!H8)')
    sheet.set_formula('O2', 'IF(OR(ISNA(M2),ISNA(N2)),NA(),MAX(0,N2-M2))')
    for r in range(3, 66):
        sheet.set_formula(f'O{r}',
            f'IF(OR(ISNA(M{r}),ISNA(N{r})),NA(),'
            f'IF(OR(NOT(ISNUMBER($AD$4)),ROW()<=$AD$4,COUNT(P{r}:Y{r})=0),MAX(0,N{r}-M{r}),'
            f'SUM(IFERROR(P{r}:Y{r}-P{r-1}:Y{r-1},0))))', array=True)


def fill_template(report_bytes: bytes, template_path: Path = TEMPLATE) -> tuple[bytes, dict]:
    """Return (filled .xlsm bytes, {sheet: cells written})."""
    global _TEMPLATE_CONSTANTS
    if _TEMPLATE_CONSTANTS is None:
        _TEMPLATE_CONSTANTS = _constants(str(template_path))
    src = _constants(io.BytesIO(report_bytes))

    z = zipfile.ZipFile(template_path)
    files = {i.filename: z.read(i.filename) for i in z.infolist()}
    wbx = etree.fromstring(files['xl/workbook.xml'])
    rels = {r.get('Id'): r.get('Target') for r in etree.fromstring(files['xl/_rels/workbook.xml.rels'])}

    written = {}
    for s in wbx.iter(N + 'sheet'):
        name = s.get('name')
        if name not in SHEETS and name != MULTI_LEG:
            continue
        target = rels[s.get('{%s}id' % RNS)]
        path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        sheet = _SheetXML(files[path])
        if name == MULTI_LEG:
            if b'$AO$' in files[path]:          # only on a template that has the leg helper columns
                _refine_multileg(sheet)
                files[path] = sheet.to_bytes()
            continue
        n = 0
        for ref, v in src[name].items():
            if _TEMPLATE_CONSTANTS[name].get(ref) == v:
                continue                      # labels / unchanged defaults
            sheet.set_value(ref, v)
            n += 1
        files[path] = sheet.to_bytes()
        written[name] = n

    # Excel rebuilds its calculation chain and recalculates everything on open
    files.pop('xl/calcChain.xml', None)
    files['xl/_rels/workbook.xml.rels'] = re.sub(rb'<Relationship [^>]*calcChain[^>]*/>', b'',
                                                 files['xl/_rels/workbook.xml.rels'])
    files['[Content_Types].xml'] = re.sub(rb'<Override [^>]*calcChain[^>]*/>', b'', files['[Content_Types].xml'])
    files['xl/workbook.xml'] = re.sub(rb'<calcPr([^>]*?)\s*/>',
                                      lambda m: b'<calcPr' + m.group(1).replace(b' fullCalcOnLoad="1"', b'')
                                      + b' fullCalcOnLoad="1"/>', files['xl/workbook.xml'])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as out:
        for info in z.infolist():
            if info.filename in files:
                out.writestr(info, files[info.filename])
    return buf.getvalue(), written
