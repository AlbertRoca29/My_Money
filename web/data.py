"""Loading the data every page uses, with a small cache.

Each loader is decorated with @cached: its result is kept until a snapshot, cashflows.csv or the
calendar day changes, so clicking around the site is instant but new data shows up right away.
The heavy lifting (returns, look-through, backtest) is still done by mwr.py, lookthrough.py and
backtest.py — this file only wires them to config.py.
"""
import functools
import json
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import backtest
import config
import lookthrough
import mwr
import sheets

lookthrough.CHINA_REFERENCE = config.CHINA_REFERENCE


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def data_version():
    """Changes whenever a snapshot or cashflows.csv is added/edited, and once a day (for downloads)."""
    files = list(config.SNAPSHOT_DIR.glob(config.SNAPSHOT_GLOB)) + [config.CASHFLOWS_CSV]
    return (date.today(), len(files), max((f.stat().st_mtime for f in files if f.exists()), default=0))


def cached(fn):
    store = {}

    @functools.wraps(fn)
    def wrapper(*args):
        key = (data_version(), args)
        if key not in store:
            if any(k[0] != key[0] for k in store):  # data changed: forget everything
                store.clear()
            store[key] = fn(*args)  # exceptions are not stored, so a failed download is retried
        return store[key]
    wrapper.clear = store.clear
    return wrapper


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def category_total(v):
    """A category's holdings are {asset: amount} (or, in old files, a plain number)."""
    return sum(v.values()) if isinstance(v, dict) else v


def categories():
    return list(config.ASSET_TYPES)


@cached
def portfolios():
    """{Timestamp: snapshot dict}, sorted by date."""
    return {pd.to_datetime(p.stem, format=config.DATE_FORMAT): json.loads(p.read_text())
            for p in sorted(config.SNAPSHOT_DIR.glob(config.SNAPSHOT_GLOB))}


@cached
def allocation():
    """(df_pct, df_val): one row per snapshot, one column per category (+ "Total" in df_val)."""
    rows_val, rows_pct = [], []
    for portfolio in portfolios().values():
        total = sum(category_total(v) for v in portfolio.values())
        values = {c: category_total(portfolio.get(c, 0)) for c in categories()}
        rows_val.append({"Total": total, **values})
        rows_pct.append({c: (v / total * 100 if total else 0) for c, v in values.items()})
    idx = pd.Index(portfolios().keys(), name="Date")
    df_pct, df_val = pd.DataFrame(rows_pct, index=idx), pd.DataFrame(rows_val, index=idx)
    keep = [c for c in categories() if df_val[c].abs().sum() > 0]  # hide categories never used
    return df_pct[keep], df_val[["Total"] + keep]


@cached
def positions():
    """(wide DataFrame: one column per asset + "Total", {asset: category})."""
    asset_to_category, rows = {}, []
    for portfolio in portfolios().values():
        row, total = {}, 0
        for category, assets in portfolio.items():
            pairs = assets.items() if isinstance(assets, dict) else [(category, assets)]
            for name, amount in pairs:
                asset_to_category[name] = category
                row[name] = amount
                total += amount
        row["Total"] = total
        rows.append(row)
    idx = pd.Index(portfolios().keys(), name="Date")
    return pd.DataFrame(rows, index=idx).fillna(0), asset_to_category


def snapshot(day=None):
    """One snapshot dict (latest when day is None). day: Timestamp or 'YYYYMMDD'."""
    ps = portfolios()
    if not ps:  # nothing saved yet: start the first snapshot from scratch
        return pd.Timestamp.today().normalize(), {}
    if day is None:
        return max(ps), ps[max(ps)]
    day = pd.to_datetime(str(day), format=config.DATE_FORMAT) if not isinstance(day, pd.Timestamp) else day
    if day not in ps:  # no snapshot that day: use the closest one before it (or the first one)
        day = max((d for d in ps if d <= day), default=min(ps))
    return day, ps[day]


def parse_amount(v):
    """A number, or a sum typed in the editor like "100 + 50 - 30" (commas count as decimal points)."""
    if isinstance(v, (int, float)):
        return float(v)
    text = str(v).replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?([+-]\d+(\.\d+)?)*", text):
        raise ValueError(f"not a number or a sum: {v!r}")
    return sum(float(t) for t in re.findall(r"[+-]?\d+(?:\.\d+)?", text))


def save_snapshot(day, portfolio):
    """Write portfolios/YYYYMMDD.json. Amounts are cleaned up and every category is kept (even empty)."""
    clean = {}
    for category in list(config.ASSET_TYPES) + [c for c in portfolio if c not in config.ASSET_TYPES]:
        assets = portfolio.get(category) or {}
        clean[category] = {str(name).strip(): round(parse_amount(v), 2)
                           for name, v in assets.items() if str(name).strip() and v not in (None, "")}
    stem = datetime.strptime(str(day), "%Y-%m-%d").strftime(config.DATE_FORMAT) if "-" in str(day) else str(day)
    config.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SNAPSHOT_DIR / f"{stem}.json"
    existed = path.exists()
    path.write_text(json.dumps(clean))
    return path, existed


# ---------------------------------------------------------------------------
# Returns (mwr.py)
# ---------------------------------------------------------------------------
@cached
def snaps_and_flows():
    """(snaps, flows): [(date, total value)] per snapshot and [(date, net savings)] per day."""
    return mwr.load_snapshots(config.SNAPSHOT_DIR), mwr.load_cashflows(config.CASHFLOWS_CSV)


@cached
def benchmark_prices():
    """The benchmark's daily EUR total-return series (downloaded from justETF, cached per day on disk)."""
    return backtest.justetf_series(config.BENCHMARK_ISIN)


@cached
def alternatives():
    """{name: daily value series} of 'the same savings put into the benchmark' for each CASH_BUFFERS entry."""
    snaps, flows = snaps_and_flows()
    prices = benchmark_prices()
    return {name: mwr.simulate(snaps, flows, prices, fixed, share)
            for name, (fixed, share) in config.CASH_BUFFERS.items()}


def save_cashflows(total_csv, ingresos_csv):
    """Rebuild cashflows.csv from the TOTAL and INGRESOS tabs of the Gastos sheet."""
    mwr.build_cashflows(total_csv, ingresos_csv, out=config.CASHFLOWS_CSV)


def sheet_configured():
    return bool(config.GASTOS_SHEET_URL)


def cashflows_age_hours():
    if not config.CASHFLOWS_CSV.exists():
        return float("inf")
    return (datetime.now().timestamp() - config.CASHFLOWS_CSV.stat().st_mtime) / 3600


def sync_sheet():
    """Download the Gastos sheet now and rebuild cashflows.csv (see sheets.py). Returns a status line."""
    return sheets.sync()


last_auto_sync_error = None


def auto_sync_sheet():
    """Called when the Returns page opens: re-download the sheet if cashflows.csv is older than
    SHEET_AUTO_SYNC_HOURS. A failure is remembered (shown on the page) instead of breaking it."""
    global last_auto_sync_error
    hours = config.SHEET_AUTO_SYNC_HOURS
    if not sheet_configured() or hours is None or cashflows_age_hours() < hours:
        return
    try:
        sheets.sync()
        last_auto_sync_error = None
    except Exception as exc:
        last_auto_sync_error = f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Look-through (lookthrough.py)
# ---------------------------------------------------------------------------
@cached
def lookthrough_result():
    """Look-through of the latest snapshot vs the benchmark fund; also saved to LOOKTHROUGH_DIR."""
    day, latest = snapshot()
    r = lookthrough.build_lookthrough(latest, config.FUND_SOURCES, config.DIRECT_STOCKS,
                                      config.FUND_SOURCES[config.LOOKTHROUGH_BENCHMARK],
                                      date=day.strftime(config.DATE_FORMAT))
    lookthrough.save_snapshot(r, config.LOOKTHROUGH_DIR)
    return r


# ---------------------------------------------------------------------------
# Backtest (backtest.py)
# ---------------------------------------------------------------------------
@cached
def backtest_prices():
    return backtest.load_prices(config.PRICE_SOURCES)


@cached
def backtest_result(rebalance, with_proxies):
    """Today's fund weights held fixed against the benchmark. Returns (result, notes)."""
    latest = snapshot()[1]
    weights = latest.get("ETFs", {})  # funds only: direct stocks are left out
    prices, errors = backtest_prices()
    errors = dict(errors)

    if with_proxies:
        prices = prices.drop(columns=[config.PROXY_REPLACES], errors="ignore")
        proxy_prices, proxy_errors = backtest.load_prices({k: spec for k, (spec, _) in config.PROXY.items()})
        errors |= proxy_errors
        if config.BENCH_PROXY:
            bench, bench_errors = backtest.load_prices({config.BACKTEST_BENCHMARK: config.BENCH_PROXY})
            errors |= bench_errors
            prices = prices.drop(columns=[config.BACKTEST_BENCHMARK]).join(bench, how="outer")
        blended = backtest.blend(proxy_prices, {k: w for k, (_, w) in config.PROXY.items()})
        prices = prices.join(blended.rename(config.PROXY_LABEL), how="outer")
        weights = {(config.PROXY_LABEL if k == config.PROXY_REPLACES else k): v for k, v in weights.items()}

    result = backtest.run(weights, prices, config.BACKTEST_BENCHMARK, rebalance=rebalance)
    stocks = sum(latest.get("Stocks", {}).values())
    funds = sum(weights.values())
    notes = [f"Funds only: **{100 * funds / (funds + stocks):.1f}%** of your equity "
             f"(the {len(latest.get('Stocks', {}))} direct stocks are left out and the weights rescaled)."]
    limiter = prices[list(result["weights"])].apply(lambda c: c.first_valid_index()).idxmax()
    notes.append(f"{result['start']:%d %b %Y} → {result['end']:%d %b %Y} "
                 f"({(result['end'] - result['start']).days / 365.25:.1f} years, limited by **{limiter}**).")
    notes += [f"No price history for {k}: left out." for k, v in weights.items() if k not in prices.columns and v]
    notes += [f"Price download failed for {k}: {e}" for k, e in errors.items()]
    return result, notes
