"""Loading the data every page uses, with a small cache.

Snapshots live in the Snapshots tab of your Google Sheet, one row per asset:

    Date | Category | Asset | Amount        (2026-10-31 | ETFs | My world ETF | 12345.67)

and your savings come straight from Gastos (its Movements tab, see gastos/db.py daily_net).

Each loader is decorated with @cached: its result is kept until the snapshots (or, with savings=True, the
movements) or the calendar day change, so clicking around the site is instant but new data shows up.
The heavy lifting (returns, look-through, backtest) is still done by mwr.py, lookthrough.py and
backtest.py — this file only wires them to config.py.
"""
import functools
import json
import re
from datetime import date, datetime

import pandas as pd

import backtest
import config
import demo
import gsheet
import lookthrough
import mwr
import settings
from gastos import db as gastos_db

lookthrough.CHINA_REFERENCE = config.CHINA_REFERENCE


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
SNAPSHOTS = config.SNAPSHOTS_TAB
SNAPSHOT_HEADER = ["Date", "Category", "Asset", "Amount"]


def _fingerprint(tab):
    return hash(json.dumps(gsheet.rows(tab), default=str))


def data_version(savings=False):
    """Changes whenever the snapshots (and with savings=True, the movements) change, and once a day."""
    if settings.get("demo"):
        return date.today(), "demo", None
    return date.today(), _fingerprint(SNAPSHOTS), _fingerprint(config.MOVEMENTS_TAB) if savings else None


def cached(fn=None, *, savings=False):
    if fn is None:
        return functools.partial(cached, savings=savings)
    store = {}

    @functools.wraps(fn)
    def wrapper(*args):
        key = (data_version(savings), args)
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


def setup():
    """Create the Snapshots tab if the sheet doesn't have it yet."""
    return gsheet.ensure_tab(SNAPSHOTS, SNAPSHOT_HEADER, date_cols=[0])


def _category_order(c):
    return list(config.ASSET_TYPES).index(c) if c in config.ASSET_TYPES else len(config.ASSET_TYPES)


@cached
def portfolios():
    """{Timestamp: {category: {asset: amount}}}, sorted by date."""
    if settings.get("demo"):
        return demo.portfolios()
    rows = gsheet.rows(SNAPSHOTS)
    if not rows:
        return {}
    gsheet.check_header(SNAPSHOTS, SNAPSHOT_HEADER, rows[0])
    out = {}
    for row in rows[1:]:
        row = list(row) + [""] * 4
        if gsheet.blank(row) or not str(row[0]).strip() or row[3] in ("", None):
            continue
        day = pd.Timestamp(gsheet.to_date(row[0]))
        out.setdefault(day, {}).setdefault(str(row[1]).strip(), {})[str(row[2]).strip()] = float(row[3])
    return {d: dict(sorted(p.items(), key=lambda kv: _category_order(kv[0]))) for d, p in sorted(out.items())}


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
    """Put one snapshot in the Snapshots tab (replacing that date's rows). Returns (date, it replaced one)."""
    if settings.get("demo"):
        raise ValueError("Demo data is on: turn it off in Settings to save a snapshot")
    day = datetime.strptime(str(day), "%Y-%m-%d" if "-" in str(day) else config.DATE_FORMAT).date()
    new = [[day.isoformat(), category, str(name).strip(), round(parse_amount(v), 2)]
           for category in list(config.ASSET_TYPES) + [c for c in portfolio if c not in config.ASSET_TYPES]
           for name, v in (portfolio.get(category) or {}).items() if str(name).strip() and v not in (None, "")]
    with gsheet.lock:
        rows = gsheet.read(SNAPSHOTS)
        if rows:
            gsheet.check_header(SNAPSHOTS, SNAPSHOT_HEADER, rows[0])
        old = [r for r in rows[1:] if r and str(r[0]).strip()]
        keep = [[gsheet.to_date(r[0]).isoformat(), *(list(r[1:]) + [""] * 3)[:3]] for r in old]
        existed = any(r[0] == day.isoformat() for r in keep)
        table = sorted([r for r in keep if r[0] != day.isoformat()] + new,
                       key=lambda r: (r[0], _category_order(r[1])))
        # One write over the whole table; blank rows wipe what is left of a longer old one
        gsheet.update(SNAPSHOTS, "A2", table + [[""] * 4] * max(0, len(rows) - 1 - len(table)))
    return day, existed


# ---------------------------------------------------------------------------
# Returns (mwr.py)
# ---------------------------------------------------------------------------
@cached(savings=True)
def snaps_and_flows():
    """(snaps, flows): [(date, total value)] per snapshot and [(date, net savings)] per day (from Gastos)."""
    snaps = [(d.date(), sum(category_total(v) for v in p.values())) for d, p in portfolios().items()]
    return snaps, gastos_db.daily_net()


@cached
def benchmark_prices():
    """The benchmark's daily EUR total-return series (downloaded from justETF, cached per day on disk)."""
    return backtest.justetf_series(config.BENCHMARK_ISIN)


@cached(savings=True)
def alternative(cash_eur):
    """Daily value of 'the same savings put into the benchmark, keeping cash_eur in cash'."""
    snaps, flows = snaps_and_flows()
    return mwr.simulate(snaps, flows, benchmark_prices(), cash_eur, 0.0)


@cached(savings=True)
def alternative_between(cash_eur, start, end):
    """Like alternative(), but starting on the snapshot dated `start` with the value you had then, so over a
    window (one year, the last 12 months) both lines begin at the same point and use the same savings."""
    snaps, flows = snaps_and_flows()
    return mwr.simulate([s for s in snaps if start <= s[0] <= end], flows, benchmark_prices(), cash_eur, 0.0)


# ---------------------------------------------------------------------------
# Look-through (lookthrough.py)
# ---------------------------------------------------------------------------
@cached
def lookthrough_result():
    """Look-through of the latest snapshot vs the benchmark fund; also kept as lookthrough/<date>.json."""
    day, latest = snapshot()
    r = lookthrough.build_lookthrough(latest, config.FUND_SOURCES, config.DIRECT_STOCKS,
                                      config.FUND_SOURCES[config.LOOKTHROUGH_BENCHMARK],
                                      date=day.strftime(config.DATE_FORMAT))
    if not settings.get("demo"):  # demo numbers must not overwrite the day's real look-through
        lookthrough.save_snapshot(r)
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
