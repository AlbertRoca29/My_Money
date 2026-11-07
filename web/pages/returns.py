"""Returns: how much the money you put in has earned (MWR) and how the benchmark ETF would have done.

Net savings come from Gastos: income minus expenses per day (see gastos/db.py daily_net). The chips at the
top pick the period: the last 12 months, or one calendar year (same as Gastos' Stats).
"""
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
import mwr
from web import data
from web.blocks import chart, chips, duel, empty_page, hero, kpi, kpis, param, section, side, table
from web.theme import BASELINE, BLUE, CORAL, GREEN, INK, MUTED, RED, eur, frac, style, tone

TITLE = "Returns"


def _window(p, snaps):
    """(period, first snapshot, last snapshot) of the chosen period: "12m" (the default) or a year like "2025".
    A year runs from the last snapshot on or before 1 January to the last one on or before 31 December."""
    period = param(p, "period", "12m")
    last = snaps[-1][0]
    if period == "12m" or not period.isdigit():
        since = date(last.year - 1, last.month, min(last.day, 28))
        return "12m", next(s for s in snaps if s[0] >= since), snaps[-1]
    y = int(period)
    before = [s for s in snaps if s[0] <= date(y, 1, 1)]
    start = before[-1] if before else snaps[0]
    end = [s for s in snaps if s[0] <= date(y, 12, 31)][-1]
    return period, start, end


def _periods(snaps):
    years = range(snaps[-1][0].year, snaps[0][0].year - 1, -1)
    return [("12m", "Last 12 months")] + [(str(y), str(y)) for y in years if date(y, 12, 31) > snaps[0][0]]


def build(p):
    if len(data.portfolios()) < 2:
        return empty_page("Return on the money you put in", "Returns need at least two snapshots (+ Snapshot).")
    snaps, flows = data.snaps_and_flows()
    if not flows:
        return empty_page("Return on the money you put in", "No savings yet: add your income and expenses in Gastos.")
    period, start, end = _window(p, snaps)
    r = mwr.mwr(start, end, flows)
    short = (end[0] - start[0]).days < 330  # too short to annualise honestly: show the plain return
    when = "in the last 12 months" if period == "12m" else f"in {period}"
    return {
        "hero": hero("Return on the money you put in",
                     f"{r['period'] if short else r['annual']:.1%}",
                     [(f"{eur(r['gain'], sign=True)} market gain", tone(r["gain"])),
                      (f"{eur(r['saved'])} saved {when}", None)],
                     caption=f"{start[0]:%d %b %Y} → {end[0]:%d %b %Y} (snapshots)" + (" · not annualised" if short else ""),
                     unit=None if short else "/yr"),
        "controls": [chips("period", _periods(snaps), period)]
                    + ([chips("bench", [(n, n) for n in (config.BENCHMARK_NAME, *config.EXTRA_BENCHMARKS)], _bench(p)[0])]
                       if config.BENCHMARK_ISIN and config.EXTRA_BENCHMARKS else []),
        "sections": [sec(p) for sec in (mwr_evolution, vs_benchmark, periods, money_in, monthly)],
    }


@section("Money-weighted return over time", "From the start of the period, not annualised")
def mwr_evolution(p):
    snaps, flows = data.snaps_and_flows()
    _, start, end = _window(p, snaps)
    pts = [s for s in snaps if start[0] <= s[0] <= end[0]]
    if len(pts) < 2:
        return None
    rows = []
    for i in range(1, len(pts)):
        r = mwr.mwr(start, pts[i], flows)
        rows.append((pd.Timestamp(pts[i][0]), r["period"], r["gain"]))
    x, period, gain = zip(*rows)
    x0 = pd.Timestamp(start[0])
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=BASELINE, width=1))
    if config.BENCHMARK_ISIN:  # the same savings, on the same days, in the benchmark with some cash on the side
        k = param(p, "cash_k", config.BENCHMARK_CASH_K, float)
        label, isin = _bench(p)
        alt = data.alternative_between(1000 * k, start[0], end[0], isin)
        a0 = (start[0], alt.asof(x0))
        theirs = [mwr.mwr(a0, (d.date(), alt.asof(d)), flows)["period"] for d in x]
        fig.add_trace(go.Scatter(x=[x0, *x], y=[0, *theirs], name=f"{_bench_name(k, label)} — {theirs[-1]:+.1%}",
                                 line=dict(color=CORAL, width=2.5), mode="lines+markers", marker=dict(size=4),
                                 hovertemplate="%{y:+.1%}<extra>" + _bench_name(k, label) + "</extra>"))
    fig.add_trace(go.Scatter(x=[x0, *x], y=[0, *period], name=f"You — {period[-1]:+.1%}",
                             line=dict(color=BLUE, width=3), mode="lines+markers", marker=dict(size=5),
                             customdata=[0, *gain], hovertemplate="%{y:+.1%} · %{customdata:+,.0f} €<extra>you</extra>"))
    fig.update_yaxes(tickformat=".0%")
    return chart(style(fig, height=380))


@section("Money-weighted return")
def periods(p):
    snaps, flows = data.snaps_and_flows()
    df = mwr.summary(snaps, flows)
    cards = kpis(*[kpi(name, f"{r['annual']:.1%}/yr", f"{eur(r['gain'], sign=True)} · {r['period']:.1%} over period",
                       tone(r["annual"])) for name, r in df.iterrows()])
    df = df.rename(columns={"annual": "MWR / yr", "period": "MWR over period"})
    fmt = {"start": eur, "saved": eur, "end": eur, "gain": lambda x: eur(x, sign=True),
           "MWR / yr": frac, "MWR over period": frac, "from": str, "to": str}
    return [cards, table(df, fmt, toned=("gain", "MWR / yr", "MWR over period"))]


@section("Portfolio vs money put in")
def money_in(p):
    snaps, flows = data.snaps_and_flows()
    iv = mwr.intervals(snaps, flows)
    dates = pd.to_datetime([d for d, _ in snaps])
    value = pd.Series([v for _, v in snaps], index=dates)
    gain = pd.Series(np.r_[0, iv["gain"].cumsum()], index=dates)
    put_in = value - gain

    # money in as a step line: each day's savings land the day after (flows on a snapshot day come after it)
    d0, v0 = snaps[0]
    steps = pd.Series({pd.Timestamp(d) + pd.Timedelta(days=1): f for d, f in flows if d0 <= d < snaps[-1][0]})
    steps = (v0 + steps.groupby(level=0).sum().cumsum()).reindex(
        pd.date_range(dates[0], dates[-1]), method="ffill").fillna(v0)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.07)
    fig.add_trace(go.Scatter(x=steps.index, y=steps, name=f"Money put in — {eur(put_in.iloc[-1])}",
                             line=dict(color=CORAL, width=2, shape="hv"),
                             hovertemplate="€%{y:,.0f}<extra>put in</extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=dates, y=value, name=f"Portfolio — {eur(value.iloc[-1])}",
                             line=dict(color=BLUE, width=3), mode="lines+markers", marker=dict(size=5),
                             hovertemplate="€%{y:,.0f}<extra>portfolio</extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=dates, y=gain.clip(lower=0), fill="tozeroy", mode="none", showlegend=False,
                             fillcolor="rgba(0,182,122,0.18)", hoverinfo="skip"), 2, 1)
    fig.add_trace(go.Scatter(x=dates, y=gain.clip(upper=0), fill="tozeroy", mode="none", showlegend=False,
                             fillcolor="rgba(229,72,77,0.18)", hoverinfo="skip"), 2, 1)
    fig.add_trace(go.Scatter(x=dates, y=gain, name=f"Investment gain — {eur(gain.iloc[-1], sign=True)}",
                             line=dict(color=GREEN if gain.iloc[-1] >= 0 else RED, width=2),
                             hovertemplate="%{y:+,.0f} €<extra>gain</extra>"), 2, 1)
    fig.add_hline(y=0, line=dict(color=BASELINE, width=1), row=2, col=1)
    fig.update_yaxes(tickprefix="€")
    return chart(style(fig, height=540))


def _short(v):
    """+1.8k / −996: short enough to sit next to a bar on a narrow screen."""
    s = "−" if v < 0 else "+"
    return f"{s}{abs(v) / 1000:.1f}k" if abs(v) >= 1000 else f"{s}{abs(v):.0f}"


@section("Saved vs market", width="half")
def monthly(p, max_gap_days=45):
    snaps, flows = data.snaps_and_flows()
    _, start, end = _window(p, snaps)
    iv = mwr.intervals([s for s in snaps if start[0] <= s[0] <= end[0]], flows)
    iv = iv[(pd.to_datetime(iv["to"]) - pd.to_datetime(iv["from"])).dt.days <= max_gap_days]
    month = pd.to_datetime(iv["to"]).dt.to_period("M")
    m = iv.groupby(month)[["saved", "gain"]].sum().iloc[::-1]  # newest on top
    rows = [p.strftime("%b %y") for p in m.index]

    # One row per month, two columns on the same scale: what you saved and what the market did. Each column has
    # its own zero line, and colour only says in (green) or out (red).
    lim = m.abs().to_numpy().max() * 1.45  # room for the labels
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=(f"Saved {_short(m['saved'].sum())}", f"Market {_short(m['gain'].sum())}"))
    for col, (name, vals) in enumerate(m.items(), start=1):
        fig.add_trace(go.Bar(y=rows, x=vals, orientation="h", width=0.55, marker_cornerradius=3,
                             marker_color=[GREEN if v >= 0 else RED for v in vals],
                             text=[_short(v) for v in vals], textposition="outside", cliponaxis=False,
                             textfont=dict(size=11, color=INK), hovertemplate=f"%{{x:+,.0f}} €<extra>{name}</extra>"),
                      1, col)
        fig.update_xaxes(range=[-lim, lim], showticklabels=False, showgrid=False, zeroline=True,
                         zerolinecolor=BASELINE, zerolinewidth=1, fixedrange=True, row=1, col=col)
    fig.update_yaxes(showgrid=False, autorange="reversed", fixedrange=True)
    fig.update_annotations(font=dict(size=12, color=MUTED))
    return chart(style(fig, height=60 + 26 * len(rows), legend=False, hover="closest",
                       margin=dict(l=4, r=4, t=30, b=4)))


def _bench(p):
    """(label, ISIN) of the index chosen with the chips: the main benchmark unless another one is picked."""
    options = {config.BENCHMARK_NAME: config.BENCHMARK_ISIN, **config.EXTRA_BENCHMARKS}
    label = param(p, "bench", config.BENCHMARK_NAME)
    label = label if label in options else config.BENCHMARK_NAME
    return label, options[label]


def _bench_name(k, label=None):
    label = label or config.BENCHMARK_NAME
    return f"{label} + €{k:g}k cash" if k else f"100% {label}"


@section("You vs the benchmark", width="full")
def vs_benchmark(p):
    if not config.BENCHMARK_ISIN:
        return None  # no benchmark set in config_local.py
    k = param(p, "cash_k", config.BENCHMARK_CASH_K, float)
    label, isin = _bench(p)
    name = _bench_name(k, label)
    snaps, flows = data.snaps_and_flows()
    period, start, end = _window(p, snaps)
    # The benchmark gets the value you had at the start of the period and the same savings on the same days, so
    # its line starts where yours does and the two end values differ by exactly the "ahead / behind" figure.
    alt = data.alternative_between(1000 * k, start[0], end[0], isin)
    alt_start, alt_end = (start[0], alt[pd.Timestamp(start[0])]), (end[0], alt[pd.Timestamp(end[0])])
    you, them = mwr.mwr(start, end, flows), mwr.mwr(alt_start, alt_end, flows)
    short = (end[0] - start[0]).days < 330  # too short to annualise honestly
    rate = lambda r: f"{r['period']:.1%}" if short else f"{r['annual']:.1%}/yr"
    lead = end[1] - alt_end[1]  # same start, same savings: the gap is all market

    dates = pd.to_datetime([d for d, _ in snaps if start[0] <= d <= end[0]])
    value = pd.Series([v for d, v in snaps if start[0] <= d <= end[0]], index=dates)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=alt.index, y=alt, name=name, line=dict(color=CORAL, width=2),
                             hovertemplate="€%{y:,.0f}<extra>" + name + "</extra>"))
    fig.add_trace(go.Scatter(x=dates, y=value, name="You", line=dict(color=BLUE, width=3), mode="lines+markers",
                             marker=dict(size=5), hovertemplate="€%{y:,.0f}<extra>you</extra>"))
    fig.update_yaxes(tickprefix="€")
    when = "the last 12 months" if period == "12m" else period
    return {"subtitle": f"Same savings, same days, in {label} with €{k:g}k kept as cash",
            "blocks": [duel(side("You", eur(you["gain"], sign=True), rate(you), BLUE),
                            side(name, eur(them["gain"], sign=True), rate(them), CORAL),
                            f"You are **{eur(abs(lead))}** {'ahead' if lead >= 0 else 'behind'}", tone(lead)),
                       chart(style(fig, height=340))]}
