"""Everything you are likely to edit lives here.

The website (app.py) reads everything from here. Change a value, save the file
and the running site reloads by itself (Flask's debug reloader watches every .py file).
"""
import os
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------------------
# Data: your Google Sheet (movements and snapshots) and a private bucket (receipts, downloads)
# ---------------------------------------------------------------------------
# The sheet's ID is the long part of its link: docs.google.com/spreadsheets/d/<ID>/edit. Share the sheet with
# the service account (Editor). deploy.sh sets these on Cloud Run; on your computer put them in config_local.py.
SHEET_ID = os.environ.get("MY_MONEY_SHEET", "")
PROJECT = os.environ.get("MY_MONEY_PROJECT", "")  # your Google Cloud project, e.g. "my-money-153626"
BUCKET = os.environ.get("MY_MONEY_BUCKET", "")   # empty: receipts and downloads go in this folder instead
MOVEMENTS_TAB, SNAPSHOTS_TAB = "Movements", "Snapshots"
SHEET_CACHE_SECONDS = 30   # edits made directly in the sheet show up in the app after at most this long
DATE_FORMAT = "%Y%m%d"

# ---------------------------------------------------------------------------
# Categories: name -> colour. The order is the order used in charts and in the snapshot editor.
# ---------------------------------------------------------------------------
ASSET_TYPES = {
    "Cash":            "#A4B1C0",
    "ETFs":            "#4B80DF",
    "Stocks":          "#DC8C50",
    "Private Markets": "#2FA383",
    "Commodities":     "#D1A93C",
    "Derivatives":     "#C2639A",
    "Crypto":          "#7A6AD0",
    "Other":           "#7D8894",
}
OTHERS_COLOR = "#B3A6E6"  # the grouped "Others" band in the stacked charts

# ---------------------------------------------------------------------------
# Overview page defaults (the start date can also be changed from the app's settings, see settings.py)
# ---------------------------------------------------------------------------
OVERVIEW_START = "2025-09-01"   # first date shown in the trend charts
GROWTH_WINDOW_DAYS = 60         # the "Growth" trend line is averaged over this many trailing days
SMOOTHING_DAYS = 40             # rolling window of the smoothed allocation chart
ANIMATION_FREQ = "W"            # positions animation: one frame per week ("D", "W", "ME"...)

# ---------------------------------------------------------------------------
# Holdings and benchmark. These say what you own, so the real values live in config_local.py
# (git-ignored); the empty defaults below just switch the exposure and backtest features off.
# ---------------------------------------------------------------------------
BENCHMARK_NAME = "Benchmark"     # how the benchmark ETF is called on the pages
BENCHMARK_ISIN = None            # its ISIN (justETF, EUR, dividends included)

# Returns page: "what if every euro had gone into the benchmark instead, with this many k€ kept in cash"
# (the default; change it from the app's settings)
BENCHMARK_CASH_K = 3

# Other indices the Returns page can compare against (chips next to the main benchmark): name -> ISIN
# (accumulating ETFs in EUR on justETF, dividends included)
EXTRA_BENCHMARKS = {"MSCI World": "IE00B4L5Y983", "S&P 500": "IE00B5BMR087"}

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

# Personal settings (holdings, benchmark, SHEET_ID…) go in config_local.py, which is git-ignored.
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
