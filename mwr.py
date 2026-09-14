"""Money-weighted return of the portfolio snapshots, treating net savings as the money put in.

Net savings come from the "Gastos" Google Sheet: "VALOR TOTAL" of every row in TOTAL, except
the rows whose INGRESOS "Tipus" is "📈 Investments" (dividends, interest, sales of positions...),
since those are returns, not new money. They are cached per day in cashflows.csv.

The portfolio value is the sum of every position in a snapshot, cash included, so savings that
are not invested yet count as earning 0%. A flow dated on a snapshot day lands after that snapshot.

Usage:
  python mwr.py                                       # use cashflows.csv
  python mwr.py --total TOTAL.csv --ingresos INGRESOS.csv  # rebuild cashflows.csv first
(the CSVs are File > Download > CSV of each tab of the sheet)
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lookthrough import BENCH_C, DIRECT_C, GRID, MUTED, PORTFOLIO_C, UNDER_C, _legend, _style

HERE = Path(__file__).parent
SNAPSHOT_DIR = HERE / "portfolios"
CASHFLOWS = HERE / "cashflows.csv"


def eur(x, sign=False):
    """€1,234 / +€1,234 / −€1,234."""
    return f"{'−' if x < 0 else '+' if sign else ''}€{abs(x):,.0f}"


def _num(s):
    s = (s or "").strip()
    if "," in s:  # Spanish locale: 1.234,56
        s = s.replace(".", "").replace(",", ".")
    return float(s) if s else 0.0


def _date(s):
    d, m, y = (int(x) for x in s.strip().split("/"))
    return date(y + 2000 if y < 100 else y, m, d)


def build_cashflows(total_csv, ingresos_csv, out=CASHFLOWS):
    with open(ingresos_csv, newline="", encoding="utf-8") as f:
        investments = {r["ID"] for r in csv.DictReader(f) if "Investments" in r["Tipus"]}
    daily = defaultdict(float)
    with open(total_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ID"] and r["ID"] not in investments:
                daily[_date(r["Data"])] += _num(r["VALOR TOTAL"])
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "net"])
        for d, v in sorted(daily.items()):
            if round(v, 2):
                w.writerow([d.isoformat(), round(v, 2)])
    print(f"{out.name}: {len(daily)} days, {len(investments)} investment incomes left out")


def load_cashflows(path=CASHFLOWS):
    with open(path, newline="") as f:
        return [(date.fromisoformat(r["date"]), float(r["net"])) for r in csv.DictReader(f)]


def load_snapshots(snapshot_dir=SNAPSHOT_DIR):
    snaps = []
    for p in sorted(snapshot_dir.glob("2*.json")):
        groups = json.loads(p.read_text())
        snaps.append((datetime.strptime(p.stem, "%Y%m%d").date(),
                      sum(v for g in groups.values() for v in g.values())))
    return snaps


def xirr(cfs):
    """Annual rate r with sum(c / (1+r)^years) == 0, found by bisection."""
    t0 = cfs[0][0]
    npv = lambda r: sum(c / (1 + r) ** ((d - t0).days / 365.25) for d, c in cfs)
    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def mwr(start, end, flows):
    (d0, v0), (d1, v1) = start, end
    inside = [(d, f) for d, f in flows if d0 <= d < d1]
    rate = xirr([(d0, -v0)] + [(d, -f) for d, f in inside] + [(d1, v1)])
    years = (d1 - d0).days / 365.25
    net = sum(f for _, f in inside)
    return {"from": d0, "to": d1, "start": v0, "saved": net, "end": v1, "gain": v1 - v0 - net,
            "annual": rate, "period": (1 + rate) ** years - 1}


def twr(snaps, flows):
    """Time-weighted return, chaining Modified Dietz between consecutive snapshots."""
    growth = 1.0
    for (d0, v0), (d1, v1) in zip(snaps, snaps[1:]):
        span = (d1 - d0).days
        inside = [(d, f) for d, f in flows if d0 <= d < d1]
        net = sum(f for _, f in inside)
        weighted = sum(f * (d1 - d).days / span for d, f in inside)
        growth *= 1 + (v1 - v0 - net) / (v0 + weighted)
    years = (snaps[-1][0] - snaps[0][0]).days / 365.25
    return growth - 1, growth ** (1 / years) - 1


def summary(snaps, flows):
    """MWR since the first snapshot, over the last 12 months and year to date, as a DataFrame."""
    last = snaps[-1]
    first_after = lambda d: next(s for s in snaps if s[0] >= d)
    periods = {"Since first snapshot": snaps[0],
               "Last 12 months": first_after(date(last[0].year - 1, last[0].month, last[0].day)),
               "Year to date": first_after(date(last[0].year, 1, 1))}
    return pd.DataFrame({name: mwr(start, last, flows) for name, start in periods.items()}).T


def intervals(snaps, flows):
    """One row per pair of consecutive snapshots: money saved in between and what the market added."""
    rows = []
    for (d0, v0), (d1, v1) in zip(snaps, snaps[1:]):
        inside = [(d, f) for d, f in flows if d0 <= d < d1]
        net = sum(f for _, f in inside)
        weighted = sum(f * (d1 - d).days / (d1 - d0).days for d, f in inside)
        rows.append({"from": d0, "to": d1, "start": v0, "end": v1, "saved": net,
                     "gain": v1 - v0 - net, "return": (v1 - v0 - net) / (v0 + weighted)})
    return pd.DataFrame(rows)


def plot_money_in(snaps, flows):
    """Portfolio value against the money put in (first snapshot + net savings), and the gap between them."""
    iv = intervals(snaps, flows)
    dates = pd.to_datetime([d for d, _ in snaps])
    value = pd.Series([v for _, v in snaps], index=dates)
    gain = pd.Series(np.r_[0, iv["gain"].cumsum()], index=dates)
    put_in = value - gain

    # money in as a step line: each day's savings land the day after (flows on a snapshot day come after it)
    d0, v0 = snaps[0]
    steps = pd.Series({pd.Timestamp(d) + pd.Timedelta(days=1): f for d, f in flows if d0 <= d < snaps[-1][0]})
    steps = (v0 + steps.groupby(level=0).sum().cumsum()).reindex(
        pd.date_range(dates[0], dates[-1]), method="ffill").fillna(v0)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, height_ratios=[2, 1],
                                   layout="constrained")
    ax1.fill_between(dates, value, put_in, where=value >= put_in, interpolate=True, color=PORTFOLIO_C, alpha=0.15)
    ax1.fill_between(dates, value, put_in, where=value < put_in, interpolate=True, color=UNDER_C, alpha=0.15)
    ax1.plot(steps.index, steps, lw=2, color=BENCH_C, drawstyle="steps-post",
             label=f"Money put in — €{put_in.iloc[-1]:,.0f}")
    ax1.plot(dates, value, lw=2, color=PORTFOLIO_C, marker="o", ms=4, label=f"Portfolio — €{value.iloc[-1]:,.0f}")
    _style(ax1, f"Portfolio value vs money put in (value on {d0:%d %b %Y} + net savings since)", xlabel="")
    ax1.set_ylabel("€", color=MUTED, fontsize=9)
    _legend(ax1, loc="upper left")

    ax2.fill_between(dates, gain, 0, where=gain >= 0, interpolate=True, color=PORTFOLIO_C, alpha=0.25)
    ax2.fill_between(dates, gain, 0, where=gain < 0, interpolate=True, color=UNDER_C, alpha=0.25)
    ax2.plot(dates, gain, lw=2, color=PORTFOLIO_C if gain.iloc[-1] >= 0 else UNDER_C)
    ax2.axhline(0, color=MUTED, lw=1)
    ax2.annotate(eur(gain.iloc[-1], sign=True), (dates[-1], gain.iloc[-1]), xytext=(6, 0),
                 textcoords="offset points", va="center", fontsize=9, color=MUTED)
    _style(ax2, "Investment gain (value − money put in)", xlabel="")
    ax2.set_ylabel("€", color=MUTED, fontsize=9)
    for ax in (ax1, ax2):
        ax.grid(True, axis="y", color=GRID, lw=0.8)
        ax.grid(False, axis="x")
    return fig


def plot_monthly(snaps, flows, max_gap_days=45):
    """Per month, the money you saved vs what the market added (snapshot gaps longer than max_gap_days skipped)."""
    iv = intervals(snaps, flows)
    iv = iv[(pd.to_datetime(iv["to"]) - pd.to_datetime(iv["from"])).dt.days <= max_gap_days]
    m = iv.groupby(pd.to_datetime(iv["to"]).dt.to_period("M"))[["saved", "gain"]].sum()
    # compound the interval returns within each month
    m["return"] = iv.groupby(pd.to_datetime(iv["to"]).dt.to_period("M"))["return"].apply(lambda r: (1 + r).prod() - 1)

    x, w = np.arange(len(m)), 0.38
    fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
    ax.bar(x - w / 2 - 0.01, m["saved"], w, color=BENCH_C, label=f"Saved — €{m['saved'].sum():,.0f}")
    ax.bar(x + w / 2 + 0.01, m["gain"], w, color=[PORTFOLIO_C if g >= 0 else UNDER_C for g in m["gain"]],
           label=f"Market gain — {eur(m['gain'].sum(), sign=True)}")
    for xi, (g, r) in zip(x, m[["gain", "return"]].values):
        ax.annotate(f"{r:+.1%}", (xi + w / 2, g), xytext=(0, 3 if g >= 0 else -3), textcoords="offset points",
                    ha="center", va="bottom" if g >= 0 else "top", fontsize=8, color=MUTED)
    ax.axhline(0, color=MUTED, lw=1)
    ax.set_xticks(x, [p.strftime("%b %y") for p in m.index])
    _style(ax, "Each month: money saved vs market gain (label = market return that month)", xlabel="")
    ax.set_ylabel("€", color=MUTED, fontsize=9)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.grid(False, axis="x")
    _legend(ax, loc="upper left")
    return fig


def simulate(snaps, flows, prices, cash_fixed=3000, cash_pct=0.05):
    """Daily value of an alternative you: the first snapshot's value and the same savings, but held as
    cash_fixed + cash_pct of the total in cash (0%) and the rest in `prices` (EUR, daily), rebalanced
    whenever money comes in or goes out. Values are taken before that day's flow, like the snapshots."""
    d0, v0 = snaps[0]
    days = pd.date_range(pd.Timestamp(d0), pd.Timestamp(snaps[-1][0]))
    px = prices.reindex(prices.index.union(days)).ffill().reindex(days)
    by_day = defaultdict(float)
    for d, f in flows:
        by_day[pd.Timestamp(d)] += f

    def rebalance(total, p):
        cash = min(total, cash_fixed + cash_pct * total)
        return cash, (total - cash) / p

    cash, units = rebalance(v0, px.iloc[0])
    values = []
    for day, p in px.items():
        values.append(cash + units * p)
        if by_day.get(day):
            cash, units = rebalance(values[-1] + by_day[day], p)
    return pd.Series(values, index=days)


def at_snapshots(series, snaps):
    """The (date, value) list of a simulated daily series on the snapshot dates, to reuse mwr()/summary()."""
    return [(d, series[pd.Timestamp(d)]) for d, _ in snaps]


def compare(snaps, flows, alternatives):
    """MWR per period for you and each {name: daily value series}, plus the end value of each."""
    runs = {"You": snaps} | {name: at_snapshots(s, snaps) for name, s in alternatives.items()}
    out = {}
    for name, sn in runs.items():
        s = summary(sn, flows)
        out[(name, "MWR / yr")] = s["annual"]
        out[(name, "end")] = s["end"]
    return pd.DataFrame(out)


def plot_vs_alternatives(snaps, flows, alternatives):
    """Your portfolio against the alternatives fed the same money, and how far ahead or behind you are."""
    colors = [BENCH_C, DIRECT_C]
    dates = pd.to_datetime([d for d, _ in snaps])
    value = pd.Series([v for _, v in snaps], index=dates)
    put_in = value - pd.Series(np.r_[0, intervals(snaps, flows)["gain"].cumsum()], index=dates)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[2, 1.2],
                                   layout="constrained")
    ax1.plot(dates, put_in, lw=1.2, ls=":", color=MUTED, label=f"Money put in — {eur(put_in.iloc[-1])}")
    for (name, s), c in zip(alternatives.items(), colors):
        ax1.plot(s.index, s, lw=1.6, color=c, label=f"{name} — {eur(s.iloc[-1])}")
        diff = value - s.reindex(dates)
        ax2.plot(dates, diff, lw=2, color=c, marker="o", ms=3, label=f"vs {name}: {eur(diff.iloc[-1], sign=True)}")
    ax1.plot(dates, value, lw=2, color=PORTFOLIO_C, marker="o", ms=4, label=f"You — {eur(value.iloc[-1])}")
    _style(ax1, "Your portfolio vs the same savings put into the benchmark", xlabel="")
    ax1.set_ylabel("€", color=MUTED, fontsize=9)
    _legend(ax1, loc="upper left")

    ax2.axhline(0, color=MUTED, lw=1)
    _style(ax2, "You minus the alternative (above 0 = you're ahead)", xlabel="")
    ax2.set_ylabel("€", color=MUTED, fontsize=9)
    _legend(ax2, loc="lower left")
    for ax in (ax1, ax2):
        ax.grid(True, axis="y", color=GRID, lw=0.8)
        ax.grid(False, axis="x")
    return fig


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--total", help="CSV download of the TOTAL tab")
    ap.add_argument("--ingresos", help="CSV download of the INGRESOS tab")
    args = ap.parse_args()
    if args.total or args.ingresos:
        if not (args.total and args.ingresos):
            ap.error("--total and --ingresos go together")
        build_cashflows(args.total, args.ingresos)

    if not CASHFLOWS.exists() or len(load_snapshots()) < 2:
        raise SystemExit("Needs cashflows.csv and at least two snapshots in portfolios/ (see the top of this file).")
    flows, snaps = load_cashflows(), load_snapshots()
    print(f"{'':22}{'from':>12}{'start':>9}{'saved':>9}{'end':>9}{'gain':>8}{'MWR/yr':>9}{'period':>9}")
    for name, r in summary(snaps, flows).iterrows():
        print(f"{name:22}{r['from']!s:>12}{r['start']:>9.0f}{r['saved']:>9.0f}{r['end']:>9.0f}"
              f"{r['gain']:>8.0f}{r['annual']:>9.1%}{r['period']:>9.1%}")
    total, annual = twr(snaps, flows)
    print(f"\nTime-weighted (portfolio alone): {total:.1%} total, {annual:.1%}/yr")


if __name__ == "__main__":
    main()
