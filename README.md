# My Money

A personal-finance side project, still a work in progress. One website with two halves, and a switcher at the top
to go from one to the other:

- **[Gastos](gastos/)** at `/` (the default, orange): a phone-first app to log expenses and income.
- **Portfolio tracker** at `/portfolio` (blue): net worth from periodic JSON snapshots, money-weighted returns,
  look-through exposure vs a benchmark ETF, and a backtest of today's fund mix.

No personal data lives in this repo. Snapshots (`portfolios/`), savings (`cashflows.csv`) and
`config_local.py` (holdings, benchmark, Google Sheet link) are all git-ignored and stay on your machine.
Without them the pages start empty and tell you what to add.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/python app.py
```

Then open http://127.0.0.1:8050 (Gastos; the portfolio is at http://127.0.0.1:8050/portfolio). The server restarts
by itself whenever you save a `.py` file. Add `MY_MONEY_HOST=0.0.0.0` in front to open it from your phone on the same Wi-Fi.

## Where things are

| File | What it does | Edit it to… |
|---|---|---|
| `config.py` | Every setting, with empty defaults for the private ones | change colours or defaults |
| `config_local.py` | Your own values (git-ignored): `FUND_SOURCES`, `DIRECT_STOCKS`, `PRICE_SOURCES`, benchmark… | add an ETF/stock |
| `etfs.py` | ISIN, issuer and strategy bucket of popular European ETFs, to copy into `config_local.py` | add an ETF to the list |
| `web/pages/overview.py` | Overview page: balance, breakdown, value and growth over time | change or add charts on that page |
| `web/pages/returns.py` | MWR / TWR, money put in vs gain, the "same savings in the benchmark" comparison | — |
| `web/pages/exposure.py` | Look-through vs the benchmark: countries, sectors, companies, overlap… | — |
| `web/pages/backtest_page.py` | Today's fund weights vs the benchmark over time | — |
| `web/data.py` | Loads snapshots and cash flows, runs `mwr.py`, `lookthrough.py` and `backtest.py` (cached) | add a new data source |
| `web/blocks.py` | The building blocks a page is made of: `kpis`, `chart`, `table`, `items`, `notes`… | add a new block type |
| `web/theme.py` | Colours, number formats (`eur`, `pct`) and the Plotly chart style | restyle every chart at once |
| `app.py` | URL routes only (also registers Gastos' routes from `gastos/routes.py`) | add an API endpoint |
| `templates/`, `static/` | The browser side. It has no finance logic: it draws whatever the Python pages return | change the look |

`mwr.py`, `lookthrough.py` and `backtest.py` do the calculations and downloads, and can also be used on their
own (`python mwr.py` prints the returns once there is data).

## Add a chart to a page

Every card on a page is one Python function:

```python
@section("My new chart", "Optional subtitle", width="half")   # width: "full" or "half"
def my_chart(p):                    # p = the values of the page's controls
    _, df_val = data.allocation()
    fig = go.Figure(go.Scatter(x=df_val.index, y=df_val["Total"]))
    return chart(style(fig))        # or a list: [kpis(...), chart(...), table(df)]
```

Then add `my_chart` to the `sections` list in that page's `build()`. If it raises an error, only that
card shows it and the rest of the page still loads.

## Add a snapshot

Click **+ Snapshot**. The editor starts from the latest snapshot (or any older one), and amounts can be
sums like `100 + 50 + 25`. It saves `portfolios/YYYYMMDD.json`.

## Update savings (Google Sheets)

`cashflows.csv` is built from the TOTAL and INGRESOS tabs of the Gastos sheet. To connect it once:

1. Put the sheet's link in `GASTOS_SHEET_URL` in `config_local.py`, and the tab names in `GASTOS_TABS`
   (already set to TOTAL and INGRESOS). The tab IDs are looked up automatically.
2. Give access in one of two ways (details at the top of `sheets.py`):
   - **Link sharing:** Share › "Anyone with the link" › Viewer. Nothing else to do.
   - **Private:** create a Google service account, save its JSON key as `google_credentials.json`
     (git-ignored), and share the sheet with its e-mail as Viewer.

After that, **Returns › Sync from Google Sheets** downloads it, and the Returns page re-syncs by itself
when `cashflows.csv` is older than `SHEET_AUTO_SYNC_HOURS`. From the terminal: `python sheets.py`.
Uploading the two CSV downloads by hand still works too.
