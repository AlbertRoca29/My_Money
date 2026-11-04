"""How today's equity mix (fixed weights, no cash) would have performed, against a benchmark ETF.

Prices are total-return where available and always in EUR:
  - ETFs: justETF daily series in EUR, dividends included
  - Stocks: Nasdaq daily closes in USD (no dividends), converted with ECB reference rates
The backtest starts when every position has data, so the newest fund sets the length.
"""
import json
import time
import urllib.request
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import storage
from lookthrough import BENCH_C, GRID, INK_2, MUTED, PORTFOLIO_C, UNDER_C, _legend, _style, _suptitle

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
       "Accept": "application/json"}
JUSTETF_URL = ("https://www.justetf.com/api/etfs/{id}/performance-chart?locale=en&currency=EUR"
               "&valuesType=MARKET_VALUE&reduceData=false&includeDividends=true")
NASDAQ_URL = ("https://api.nasdaq.com/api/quote/{id}/historical?assetclass=stocks"
              "&fromdate=2010-01-01&todate={today}&limit=99999")
FX_URL = "https://api.frankfurter.dev/v1/2010-01-01..{today}?base={base}&symbols=EUR"


def _cached(name, fetch):
    """Downloaded once a day and kept under cache/prices/ (see storage.py)."""
    def gently():
        body = fetch()
        time.sleep(0.4)  # be gentle with the free endpoints
        return body
    return json.loads(storage.cached_download("prices", name, gently))


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=90).read()


def justetf_series(isin):
    """Daily EUR total-return series for an ETF (dividends reinvested)."""
    d = _cached(f"justetf_{isin}.json", lambda: _get(JUSTETF_URL.format(id=isin)))
    s = pd.Series({pd.Timestamp(p["date"]): float(p["value"]["raw"]) for p in d["series"]})
    return s.sort_index()


def nasdaq_series(symbol, assetclass="stocks"):
    """Daily close price series for a US-listed stock or ETF, in USD (dividends not included)."""
    url = NASDAQ_URL.format(id=symbol, today=f"{datetime.now():%Y-%m-%d}").replace("assetclass=stocks", f"assetclass={assetclass}")
    d = _cached(f"nasdaq_{assetclass}_{symbol}.json", lambda: _get(url))
    rows = (d.get("data") or {}).get("tradesTable", {}).get("rows") or []
    if not rows:
        raise ValueError(f"Nasdaq has no history for {symbol!r}")
    s = pd.Series({pd.Timestamp(r["date"]): float(r["close"].replace("$", "").replace(",", "")) for r in rows})
    return s.sort_index()


def fx_to_eur(base):
    """Daily <base>→EUR rate from the ECB (via Frankfurter)."""
    if base == "EUR":
        return None
    d = _cached(f"fx_{base}.json", lambda: _get(FX_URL.format(base=base, today=f"{datetime.now():%Y-%m-%d}")))
    return pd.Series({pd.Timestamp(k): v["EUR"] for k, v in d["rates"].items()}).sort_index()


def load_prices(sources):
    """sources: {label: {"justetf": isin} | {"nasdaq": ticker, "currency": "USD"}} -> (EUR prices, errors)."""
    series, errors = {}, {}
    for label, spec in sources.items():
        try:
            if "justetf" in spec:
                s = justetf_series(spec["justetf"])
            else:
                s = nasdaq_series(spec["nasdaq"], spec.get("assetclass", "stocks"))
                fx = fx_to_eur(spec.get("currency", "USD"))
                s = (s * fx.reindex(s.index.union(fx.index)).ffill().reindex(s.index)).dropna()
            series[label] = s
        except Exception as exc:  # a missing price source must not kill the whole backtest
            errors[label] = f"{type(exc).__name__}: {exc}"
    prices = pd.DataFrame(series).sort_index()
    return prices, errors


def blend(prices, weights, rebalance="ME"):
    """One synthetic price series from several, held at fixed `weights` (a stand-in for an index)."""
    px = prices[list(weights)].dropna()
    return _constant_mix(px.pct_change().fillna(0), weights, rebalance)


def _constant_mix(returns, weights, rebalance="ME"):
    """Growth of 1 for a fixed-weight portfolio, rebalanced at each period end ("ME", "QE", "YE" or None)."""
    w0 = np.array([weights[c] for c in returns.columns], dtype=float)
    w0 /= w0.sum()
    marks = set() if rebalance is None else set(returns.resample(rebalance).last().index)
    w, out = w0.copy(), []
    level = 1.0
    for date, row in zip(returns.index, returns.to_numpy()):
        grown = w * (1 + row)
        level *= grown.sum()
        w = grown / grown.sum()
        out.append(level)
        if date in marks:
            w = w0.copy()
    return pd.Series(out, index=returns.index)


def metrics(series, periods=252):
    r = series.pct_change().dropna()
    years = (series.index[-1] - series.index[0]).days / 365.25
    dd = series / series.cummax() - 1
    monthly = series.resample("ME").last().pct_change().dropna()
    return {"Total return %": 100 * (series.iloc[-1] / series.iloc[0] - 1),
            "Annualised return %": 100 * ((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1),
            "Volatility %": 100 * r.std() * np.sqrt(periods),
            "Max drawdown %": 100 * dd.min(),
            "Best month %": 100 * monthly.max(),
            "Worst month %": 100 * monthly.min()}


def run(weights, prices, benchmark, rebalance="ME", start=None):
    """Backtest fixed `weights` (label -> % of equity) against the `benchmark` column of `prices`."""
    held = {k: v for k, v in weights.items() if k in prices.columns and v > 0}
    cols = list(dict.fromkeys(list(held) + [benchmark]))
    px = prices[cols].dropna(how="all")
    px = px.loc[px.dropna().index[0] if start is None else pd.Timestamp(start):].ffill().dropna()
    returns = px[list(held)].pct_change().fillna(0)

    portfolio = _constant_mix(returns, held, rebalance)
    bench = px[benchmark] / px[benchmark].iloc[0]
    curves = pd.DataFrame({"Portfolio": portfolio, benchmark: bench})
    per_position = pd.DataFrame({
        "Weight %": pd.Series(held) / sum(held.values()) * 100,
        "Total return %": (px[list(held)].iloc[-1] / px[list(held)].iloc[0] - 1) * 100,
    })
    per_position["Contribution pp"] = per_position["Weight %"] * per_position["Total return %"] / 100
    stats = pd.DataFrame({"Portfolio": metrics(portfolio), benchmark: metrics(bench)})
    monthly = curves.resample("ME").last().pct_change().dropna()
    stats.loc["Months ahead of benchmark %"] = [100 * (monthly["Portfolio"] > monthly[benchmark]).mean(), np.nan]
    stats.loc["Correlation with benchmark"] = [curves.pct_change().corr().iloc[0, 1], np.nan]
    return {"curves": curves, "stats": stats.round(2), "per_position": per_position.round(2).sort_values("Contribution pp", ascending=False),
            "start": px.index[0], "end": px.index[-1], "benchmark": benchmark, "rebalance": rebalance,
            "weights": held}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def plot_growth(bt, start_value=100):
    """Growth of a lump sum, drawdowns, and the portfolio's lead over the benchmark."""
    c, bt_name = bt["curves"] * start_value, bt["benchmark"]
    rel = (bt["curves"]["Portfolio"] / bt["curves"][bt_name] - 1) * 100
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, height_ratios=[2.2, 1, 1],
                             layout="constrained")
    for name, color in [("Portfolio", PORTFOLIO_C), (bt_name, BENCH_C)]:
        axes[0].plot(c.index, c[name], lw=2, color=color,
                     label=f"{name} — €{c[name].iloc[-1]:,.0f} ({c[name].iloc[-1] / start_value - 1:+.1%})")
        dd = (bt["curves"][name] / bt["curves"][name].cummax() - 1) * 100
        axes[1].plot(dd.index, dd, lw=1.6, color=color, label=name)
        axes[1].fill_between(dd.index, dd, 0, color=color, alpha=0.12)
    axes[0].set_ylabel(f"value of €{start_value} (€)", color=MUTED, fontsize=9)
    _style(axes[0], f"Today's equity mix vs {bt_name} — €{start_value} invested on "
                    f"{bt['start']:%d %b %Y}", xlabel="")
    _legend(axes[0], loc="upper left")
    _style(axes[1], "Drawdown", xlabel="")
    axes[1].set_ylabel("% from peak", color=MUTED, fontsize=9)
    _legend(axes[1], loc="lower left")

    axes[2].fill_between(rel.index, rel, 0, where=rel >= 0, color=PORTFOLIO_C, alpha=0.25)
    axes[2].fill_between(rel.index, rel, 0, where=rel < 0, color=UNDER_C, alpha=0.25)
    axes[2].plot(rel.index, rel, lw=1.8, color=PORTFOLIO_C if rel.iloc[-1] >= 0 else UNDER_C)
    axes[2].axhline(0, color=BENCH_C, lw=1.5)
    _style(axes[2], f"Lead over {bt_name} (cumulative)", xlabel="")
    axes[2].set_ylabel(f"% vs {bt_name}", color=MUTED, fontsize=9)
    for ax in axes:
        ax.grid(True, axis="y", color=GRID, lw=0.8)
        ax.grid(False, axis="x")
    return fig


def plot_contributions(bt):
    """Each position's return over the window and what it contributed to the portfolio."""
    p = bt["per_position"].sort_values("Total return %")
    bench_ret = bt["stats"].loc["Total return %", bt["benchmark"]]
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.42 * len(p) + 2.2), layout="constrained")
    labels = [f"{name}  ·  {w:.0f}%" for name, w in zip(p.index, p["Weight %"])]
    axes[0].barh(labels, p["Total return %"], height=0.6,
                 color=[PORTFOLIO_C if v >= 0 else UNDER_C for v in p["Total return %"]])
    axes[0].axvline(0, color=MUTED, lw=1)
    axes[0].axvline(bench_ret, color=BENCH_C, lw=2, label=f"{bt['benchmark']} {bench_ret:+.1f}%")
    for i, v in enumerate(p["Total return %"]):
        axes[0].text(v + (2 if v >= 0 else -2), i, f"{v:+.0f}%", va="center",
                     ha="left" if v >= 0 else "right", fontsize=8, color=INK_2)
    _style(axes[0], f"Return per position since {bt['start']:%b %Y}  (name · weight)", xlabel="% total return")
    axes[0].margins(x=0.12)
    _legend(axes[0], loc="lower right")

    c = bt["per_position"].sort_values("Contribution pp")
    axes[1].barh(c.index, c["Contribution pp"], height=0.6,
                 color=[PORTFOLIO_C if v >= 0 else UNDER_C for v in c["Contribution pp"]])
    axes[1].axvline(0, color=MUTED, lw=1)
    for i, v in enumerate(c["Contribution pp"]):
        axes[1].text(v + (0.3 if v >= 0 else -0.3), i, f"{v:+.1f}", va="center",
                     ha="left" if v >= 0 else "right", fontsize=8, color=INK_2)
    _style(axes[1], "Contribution to portfolio return", xlabel="percentage points")
    axes[1].margins(x=0.15)
    _suptitle(fig, "Where the performance came from")
    return fig
