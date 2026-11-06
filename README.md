# My Money

A personal-finance side project, still a work in progress. One website with two halves, and a switcher at the top
to go from one to the other:

- **[Gastos](gastos/)** at `/` (the default, orange): a phone-first app to log expenses and income.
- **Portfolio tracker** at `/portfolio` (blue): net worth from periodic snapshots, money-weighted returns
  (your savings come straight from Gastos), look-through exposure vs a benchmark ETF, and a backtest of
  today's fund mix.

Your data lives in **your own Google Sheet** (a Movements tab and a Snapshots tab) plus a private bucket for
receipts, and the app runs on **Google Cloud Run** behind Sign in with Google: see **[DEPLOY.md](DEPLOY.md)**.
No personal data lives in this repo: `config_local.py` (holdings, benchmark, sheet ID) is git-ignored.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/python app.py
```

Then open http://127.0.0.1:8050 (Gastos; the portfolio is at http://127.0.0.1:8050/portfolio). The server restarts
by itself whenever you save a `.py` file. On your computer there's no sign-in, and it reads and writes the same
sheet as the online app (DEPLOY.md, step 6, sets that up).

## Where things are

| File | What it does | Edit it to… |
|---|---|---|
| `config.py` | Every setting, with empty defaults for the private ones | change colours or defaults |
| `settings.py` | What you change from the app itself (the ⚙ in the top bar of both halves): tab bar, benchmark cash, show Backtest, countries shown… | add a setting |
| `static/settings.js`, `settings.css` | The ⚙ sheet itself, shared by both halves (Account, every setting, Data) | change how settings look |
| `config_local.py` | Your own values (git-ignored): `FUND_SOURCES`, `DIRECT_STOCKS`, `PRICE_SOURCES`, benchmark… | add an ETF/stock |
| `demo.py` | The made-up movements and portfolio snapshots behind Settings > Show demo data | change what the demo shows |
| `tidy_names.py` | Not part of the app: merges spellings of a name in your Movements, from a list you write in `name_merges.json` | fix many names at once |
| `etfs.py` | ISIN, issuer and strategy bucket of popular European ETFs, to copy into `config_local.py` | add an ETF to the list |
| `web/pages/overview.py` | Overview page: balance, breakdown, value and growth over time | change or add charts on that page |
| `web/pages/returns.py` | MWR, money put in vs gain, the "same savings in the benchmark" comparison | — |
| `web/pages/exposure.py` | Look-through vs the benchmark: countries, sectors, companies, overlap… | — |
| `web/pages/backtest_page.py` | Today's fund weights vs the benchmark over time | — |
| `web/data.py` | Loads snapshots and cash flows, runs `mwr.py`, `lookthrough.py` and `backtest.py` (cached) | add a new data source |
| `web/blocks.py` | The building blocks a page is made of: `kpis`, `chart`, `table`, `items`, `notes`… | add a new block type |
| `web/theme.py` | Colours, number formats (`eur`, `pct`) and the Plotly chart style | restyle every chart at once |
| `app.py` | URL routes only (also registers Gastos' routes from `gastos/routes.py`) | add an API endpoint |
| `gsheet.py` | Reads and writes your Google Sheet | — |
| `storage.py` | Receipts, downloads and look-through history: the bucket online, `files/` on your computer | — |
| `auth.py` | Sign in with Google, only for `ALLOWED_EMAILS` | — |
| `deploy.sh`, `Dockerfile`, `DEPLOY.md` | Putting it on Google Cloud | change memory, region… |
| `migrate.py` | One-time copy of the old local files into the sheet and bucket | — |
| `templates/`, `static/` | The browser side. It has no finance logic: it draws whatever the Python pages return | change the look |

`mwr.py`, `lookthrough.py` and `backtest.py` do the calculations and downloads; `web/data.py` feeds them
from the sheet.

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
sums like `100 + 50 + 25`. It saves one row per asset in the Snapshots tab (Date | Category | Asset | Amount),
replacing that date's rows if there were any.

## Savings

The Returns page needs to know how much new money went in each day. It takes it from Gastos: income minus
expenses, leaving out income typed **📈 Investments** (that's a return, not new money) and expenses **paid by
others**. Nothing to sync.
