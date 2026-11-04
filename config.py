"""Everything you are likely to edit lives here.

The website (app.py) reads everything from here. Change a value, save the file
and the running site reloads by itself (Flask's debug reloader watches every .py file).
"""
import os
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
SNAPSHOT_DIR = HERE / "portfolios"              # one YYYYMMDD.json per snapshot
LOOKTHROUGH_DIR = SNAPSHOT_DIR / "lookthrough"  # every look-through run is saved here
CASHFLOWS_CSV = HERE / "cashflows.csv"          # net savings per day (built by mwr.py / sheets.py)

# The Gastos Google Sheet that cashflows.csv is built from (see sheets.py for how to give access).
GASTOS_SHEET_URL = os.environ.get("GASTOS_SHEET_URL", "")  # or set it in config_local.py
GASTOS_TABS = {"total": "TOTAL", "ingresos": "INGRESOS"}   # tab names (or gid numbers) in that sheet
GOOGLE_CREDENTIALS = HERE / "google_credentials.json"  # only for a private sheet (service account key)
SHEET_AUTO_SYNC_HOURS = 12   # Returns page re-downloads the sheet when cashflows.csv is older; None = button only
DATE_FORMAT = "%Y%m%d"
SNAPSHOT_GLOB = "[0-9]" * 8 + ".json"           # anything not named YYYYMMDD.json is ignored

# ---------------------------------------------------------------------------
# Categories: name -> colour. The order is the order used in charts and in the snapshot editor.
# ---------------------------------------------------------------------------
ASSET_TYPES = {
    "Cash":            "#A9B4C2",
    "ETFs":            "#0666EB",
    "Stocks":          "#8E5CF7",
    "Private Markets": "#00A2C7",
    "Commodities":     "#F2B705",
    "Derivatives":     "#F0506E",
    "Crypto":          "#FF7A1A",
    "Other":           "#6B7785",
}
OTHERS_COLOR = "#B79CFA"  # the grouped "Others" band in the stacked charts

# ---------------------------------------------------------------------------
# Overview page defaults (all of them can also be changed from the page itself)
# ---------------------------------------------------------------------------
OVERVIEW_START = "2025-09-01"   # first date shown in the trend charts
GROWTH_WINDOW_DAYS = 60         # "growth per day" is averaged over this many trailing days
SMOOTHING_DAYS = 40             # rolling window of the smoothed allocation chart
ANIMATION_FREQ = "W"            # positions animation: one frame per week ("D", "W", "ME"...)

# ---------------------------------------------------------------------------
# Holdings and benchmark. These say what you own, so the real values live in config_local.py
# (git-ignored); the empty defaults below just switch the exposure and backtest features off.
# ---------------------------------------------------------------------------
BENCHMARK_NAME = "Benchmark"     # how the benchmark ETF is called on the pages
BENCHMARK_ISIN = None            # its ISIN (justETF, EUR, dividends included)

# Returns page: "what if every euro had gone into the benchmark instead"
CASH_BUFFERS = {                 # name: (fixed € kept in cash, share of the total kept in cash)
    "100% benchmark": (0, 0),
}

# Exposure page (look-through). Every ETF (current or past) needs a data source and a strategy bucket:
#   "My world ETF": {"ticker": "ABCD", "provider": "ishares" | "vanguard" | "avantis", "id": "<fund id>",
#                    "bucket": "Core index"}
# "proxy": True when another provider's ETF on the same index stands in for your fund (its fee is then
#          not used: add "ter": <your fund's ongoing charge in %>); "emerging": True for EM funds.
FUND_SOURCES = {}
# Every direct stock (current or past): name in the snapshots -> (company name, ISO country code, GICS sector)
#   "Some Company": ("Some Company Inc", "US", "Information Technology")
DIRECT_STOCKS = {}
LOOKTHROUGH_BENCHMARK = None     # key of FUND_SOURCES used as the comparison fund
CHINA_REFERENCE = None           # an emerging-markets FUND_SOURCES-style spec whose HKD/CNY holdings mark
                                 # HK-listed Chinese companies in Vanguard data (None: no split)
N_COUNTRIES, N_COMPANIES = 25, 50     # detail in the country / company charts (companies: max 100)

# Backtest page: where each position's price history comes from. ETFs by ISIN (justETF):
#   "My world ETF": {"justetf": "<ISIN>"}; US stocks as {"nasdaq": "TICKER", "currency": "USD"}.
#   etfs.py lists ISINs and buckets of popular European ETFs: etfs.price_source("IWDA"), etfs.spec("IWDA").
PRICE_SOURCES = {}
BACKTEST_BENCHMARK = None        # key of PRICE_SOURCES that doubles as the benchmark
REBALANCE = "ME"                 # "ME" monthly, "QE" quarterly, "YE" yearly, None = never (buy & hold)

# "Longest history" variant: a short-history position swapped for long-running stand-ins.
PROXY = {}                       # {"stand-in name": ({"justetf": "<ISIN>"}, weight), ...}
PROXY_REPLACES, PROXY_LABEL = None, None   # the position they replace, and the label of the blend
BENCH_PROXY = None               # a longer-running stand-in for the benchmark, e.g. {"justetf": "<ISIN>"}

# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
HOST, PORT = "127.0.0.1", 8050

# Personal settings (holdings, benchmark, GASTOS_SHEET_URL) go in config_local.py, which is git-ignored.
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
