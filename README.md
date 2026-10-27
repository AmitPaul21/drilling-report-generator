# Drilling Report Generator

Upload a Well Report (`.xlsm`). The app:

1. reads the well's inputs from the **Data** and **DSum1** sheets (and **DSum2** if a well runs past 64 days);
2. shows the multi-leg drilling report: well header, KPIs, measured depth by leg, daily metres, a leg table, time by section, and the daily operations log;
3. lets you download the **Drilling Report template (V2.2)** filled with that well's inputs. Excel recalculates the *Drilling Report - Multi Leg* tab when the file opens, and the charts, KPI boxes and macros are kept.

## Run it

```bash
git clone https://github.com/AmitPaul21/drilling-report-generator.git
cd drilling-report-generator
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. To share it on the office network, run
`streamlit run app.py --server.address 0.0.0.0` and give colleagues `http://<your-PC-name>:8501`.
Other options are Streamlit Community Cloud (it needs a GitHub repo, so check that well data is allowed there) or an internal server.

## Files

| Path | What it does |
|---|---|
| `app.py` | Streamlit page: upload, report, downloads |
| `drilling_parser.py` | Reads Well Report inputs (Data, DSum1/DSum2) and checks the layout |
| `drilling_calc.py` | Leg placement, daily metres, section timing, KPIs (same logic as the V2.2 Multi Leg tab) |
| `drilling_export.py` | Copies typed inputs into the template at XML level, so charts, shapes and VBA survive |
| `Drilling_Report_Template_V2.2.xlsm` | Blank template. Replace it with a newer version if the layout stays the same |

## What the Well Report needs

* `Data`: heel point and leg intervals (rows 32 and 40-49: start MD, end MD, reached date and time) and TD (row 50).
* `DSum1`: one row per report day, with the date (A), time (F), FROM (H) and TO (J).
* **Reached times matter for sidetracks.** When one leg ends and the next starts on the same day, the leg's reached time places it on the right day. Without a time, the app falls back to depths.

## How legs and daily metres are worked out

* Leg 1 starts on the report that covers the heel point time.
* Each leg ends on the first report at or after its reached time.
* If the next leg was drilled on the same day, it starts the day before. Otherwise it starts the day before the TO depth first changes, so idle days such as lost circulation stay with the previous leg.
* Daily metres = TO - FROM until Leg 1 starts, and the sum of each active leg's progress after that. This counts metres on both legs on sidetrack days, which the plain TO - FROM in DSum1 misses.
