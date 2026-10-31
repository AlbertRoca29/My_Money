"""Backtest: today's fund weights, held fixed and rebalanced, against the benchmark.

ETF prices come from justETF (EUR, dividends included). The window starts when the newest fund has
data; the "longest history" switch swaps short-history funds for long-running stand-ins
(PROXY / BENCH_PROXY in config.py) so it goes back years further — treat that as indicative.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
from web import data
from web.blocks import chart, empty_page, hero, kpi, kpis, notes, param, section, select, table, toggle
from web.theme import BASELINE, BLUE, CORAL, GREEN, MUTED, RED, pct, style, tone

TITLE = "Backtest"
REBALANCE_OPTIONS = [("ME", "Monthly"), ("QE", "Quarterly"), ("YE", "Yearly"), ("none", "Never (buy & hold)")]


def _run(p):
    rebalance = param(p, "rebalance", config.REBALANCE or "none")
    return data.backtest_result(None if rebalance == "none" else rebalance, param(p, "proxies", False, bool))


def build(p):
    if not (config.PRICE_SOURCES and config.BACKTEST_BENCHMARK):
        return empty_page("Today's fund mix", "Set PRICE_SOURCES and BACKTEST_BENCHMARK in config_local.py "
                                              "(see config.py).")
    if not data.portfolios():
        return empty_page("Today's fund mix", "No snapshots yet: click + Snapshot to add the first one.")
    bt, _ = _run(p)
    s, b = bt["stats"]["Portfolio"], bt["stats"][bt["benchmark"]]
    lead = s["Annualised return %"] - b["Annualised return %"]
    return {
        "hero": hero(f"Today's fund mix since {bt['start']:%b %Y}", pct(s["Total return %"], 1, sign=True),
                     [(f"{pct(s['Annualised return %'])}/yr", tone(s["Annualised return %"])),
                      (f"{pct(lead, 1, sign=True)}/yr vs {bt['benchmark']}", tone(lead)),
                      (f"Max drawdown {pct(s['Max drawdown %'])}", None)],
                     caption=f"{bt['benchmark']}: {pct(b['Total return %'], 1, sign=True)} over the same window"),
        "controls": [
            select("rebalance", "Rebalance", REBALANCE_OPTIONS, param(p, "rebalance", config.REBALANCE or "none")),
            toggle("proxies", "Longest history (with proxies)", param(p, "proxies", False, bool)),
        ],
        "sections": [sec(p) for sec in (stats, growth, contributions)],
    }


@section("Statistics", width="full")
def stats(p):
    bt, notes_ = _run(p)
    s, b = bt["stats"]["Portfolio"], bt["stats"][bt["benchmark"]]
    cards = kpis(
        kpi("Annualised", pct(s["Annualised return %"]), f"{bt['benchmark']} {pct(b['Annualised return %'])}",
            tone(s["Annualised return %"] - b["Annualised return %"])),
        kpi("Volatility", pct(s["Volatility %"]), f"{bt['benchmark']} {pct(b['Volatility %'])}",
            tone(b["Volatility %"] - s["Volatility %"])),
        kpi("Max drawdown", pct(s["Max drawdown %"]), f"{bt['benchmark']} {pct(b['Max drawdown %'])}",
            tone(s["Max drawdown %"] - b["Max drawdown %"])),
        kpi("Months ahead", pct(s["Months ahead of benchmark %"], 0),
            f"correlation {s['Correlation with benchmark']:.2f}"))
    return [cards, table(bt["stats"]), notes(notes_)]


@section("Growth of €100", "Value, drawdown from the peak and the lead over the benchmark")
def growth(p):
    bt, _ = _run(p)
    c, name = bt["curves"] * 100, bt["benchmark"]
    rel = (bt["curves"]["Portfolio"] / bt["curves"][name] - 1) * 100
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.22, 0.23], vertical_spacing=0.05)
    for col, color in (("Portfolio", BLUE), (name, CORAL)):
        fig.add_trace(go.Scatter(x=c.index, y=c[col], name=f"{col} — €{c[col].iloc[-1]:,.0f}",
                                 line=dict(color=color, width=2.5), legendgroup=col,
                                 hovertemplate="€%{y:,.1f}<extra>" + col + "</extra>"), 1, 1)
        dd = (bt["curves"][col] / bt["curves"][col].cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=dd.index, y=dd, line=dict(color=color, width=1.5), fill="tozeroy",
                                 fillcolor=f"rgba({','.join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))},0.10)",
                                 showlegend=False, legendgroup=col,
                                 hovertemplate="%{y:.1f}%<extra>drawdown " + col + "</extra>"), 2, 1)
    fig.add_trace(go.Scatter(x=rel.index, y=rel.clip(lower=0), fill="tozeroy", mode="none", showlegend=False,
                             fillcolor="rgba(0,182,122,0.18)", hoverinfo="skip"), 3, 1)
    fig.add_trace(go.Scatter(x=rel.index, y=rel.clip(upper=0), fill="tozeroy", mode="none", showlegend=False,
                             fillcolor="rgba(229,72,77,0.18)", hoverinfo="skip"), 3, 1)
    fig.add_trace(go.Scatter(x=rel.index, y=rel, name=f"Lead over {name}", showlegend=False,
                             line=dict(color=GREEN if rel.iloc[-1] >= 0 else RED, width=2),
                             hovertemplate="%{y:+.1f}%<extra>lead</extra>"), 3, 1)
    fig.add_hline(y=0, line=dict(color=BASELINE, width=1), row=3, col=1)
    fig.update_yaxes(tickprefix="€", row=1, col=1)
    fig.update_yaxes(ticksuffix="%", title_text="drawdown", row=2, col=1)
    fig.update_yaxes(ticksuffix="%", title_text=f"vs {name}", row=3, col=1)
    return chart(style(fig, height=680))


@section("Where the performance came from", "Return of each fund over the window, and what it contributed")
def contributions(p):
    bt, _ = _run(p)
    per = bt["per_position"]
    bench_ret = bt["stats"].loc["Total return %", bt["benchmark"]]
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.22,
                        subplot_titles=("Total return (name · weight)", "Contribution (percentage points)"))
    r = per.sort_values("Total return %", ascending=False)
    fig.add_trace(go.Bar(y=[f"{n} · {w:.0f}%" for n, w in zip(r.index, r["Weight %"])], x=r["Total return %"],
                         orientation="h", marker_cornerradius=4,
                         marker_color=[GREEN if v >= 0 else RED for v in r["Total return %"]],
                         text=[f"{v:+.0f}%" for v in r["Total return %"]], textposition="outside",
                         textfont=dict(size=10, color=MUTED), cliponaxis=False,
                         hovertemplate="%{x:+.1f}%<extra></extra>"), 1, 1)
    fig.add_vline(x=bench_ret, line=dict(color=CORAL, width=2), row=1, col=1,
                  annotation_text=f"{bt['benchmark']} {bench_ret:+.0f}%", annotation_font_color=CORAL)
    c = per.sort_values("Contribution pp", ascending=False)
    fig.add_trace(go.Bar(y=c.index, x=c["Contribution pp"], orientation="h", marker_cornerradius=4,
                         marker_color=[BLUE if v >= 0 else RED for v in c["Contribution pp"]],
                         text=[f"{v:+.1f}" for v in c["Contribution pp"]], textposition="outside",
                         textfont=dict(size=10, color=MUTED), cliponaxis=False,
                         hovertemplate="%{x:+.2f} pp<extra></extra>"), 1, 2)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=True, gridcolor="#EEF0F3")
    fig.update_annotations(font=dict(size=13))
    height = 120 + 34 * len(per)
    return [chart(style(fig, height=height, legend=False, hover="closest")),
            table(per, {"Weight %": pct, "Total return %": lambda v: pct(v, 1, sign=True),
                        "Contribution pp": lambda v: f"{v:+.2f}"}, toned=("Total return %", "Contribution pp"))]
