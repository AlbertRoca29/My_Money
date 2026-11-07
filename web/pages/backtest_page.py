"""Backtest: today's fund weights, held fixed and rebalanced, against the benchmark.

ETF prices come from justETF (EUR, dividends included). The window starts when the newest fund has
data; the "longest history" switch swaps short-history funds for long-running stand-ins
(PROXY / BENCH_PROXY in config.py) so it goes back years further — treat that as indicative.
Both are settings (settings.py), changed from the ⚙ sheet.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
from web import data
from web.blocks import chart, empty_page, fold, hero, kpi, kpis, notes, param, section
from web.theme import BASELINE, BLUE, CORAL, GREEN, MUTED, RED, pct, style, tone

TITLE = "Backtest"


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
        "controls": [],
        "sections": [sec(p) for sec in (stats, growth, contributions)],
    }


@section("Statistics")
def stats(p):
    bt, notes_ = _run(p)
    s, b = bt["stats"]["Portfolio"], bt["stats"][bt["benchmark"]]
    n = bt["benchmark"]
    cards = kpis(
        kpi("Total return", pct(s["Total return %"], 1, sign=True), f"{n} {pct(b['Total return %'], 1, sign=True)}",
            tone(s["Total return %"] - b["Total return %"])),
        kpi("Per year", pct(s["Annualised return %"]), f"{n} {pct(b['Annualised return %'])}",
            tone(s["Annualised return %"] - b["Annualised return %"])),
        kpi("Volatility", pct(s["Volatility %"]), f"{n} {pct(b['Volatility %'])}",
            tone(b["Volatility %"] - s["Volatility %"])),
        kpi("Worst drop", pct(s["Max drawdown %"]), f"{n} {pct(b['Max drawdown %'])}",
            tone(s["Max drawdown %"] - b["Max drawdown %"])))
    return [cards, fold("Notes", blocks=[notes(notes_)])]


@section("Growth of €100")
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


@section("Where the performance came from")
def contributions(p):
    bt, _ = _run(p)
    per = bt["per_position"]
    bench, bret = bt["benchmark"], bt["stats"].loc["Total return %", bt["benchmark"]]

    def bars(df, col, colors, text, title, hover, extra=None, include=0.0):
        fig = go.Figure(go.Bar(y=df["label"], x=df[col], orientation="h", marker_cornerradius=4, marker_color=colors,
                               text=text, textposition="outside", textfont=dict(size=11, color=MUTED), cliponaxis=False,
                               hovertemplate=hover))
        fig.add_vline(x=0, line=dict(color=BASELINE, width=1))
        if extra:
            extra(fig)
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor="#EEF0F3", range=[min(0, df[col].min(), include) * 1.25,
                                                                    max(0.0, df[col].max(), include) * 1.25 + 1e-9])
        return chart(style(fig, height=90 + 34 * len(df), legend=False, hover="closest",
                           title=dict(text=title, x=0, font=dict(size=14)), margin=dict(l=8, r=8, t=44, b=8)))

    r = per.sort_values("Total return %", ascending=False).assign(label=lambda d: [f"{n} · {w:.0f}%" for n, w in zip(d.index, d["Weight %"])])
    c = per.sort_values("Contribution pp", ascending=False).assign(label=lambda d: d.index)
    # the benchmark's own return, as a coral line with its label above the plot
    mark = lambda fig: (fig.add_vline(x=bret, line=dict(color=CORAL, width=2, dash="dot")),
                        fig.add_annotation(x=bret, y=1, yref="paper", yanchor="bottom", showarrow=False,
                                           text=f"{bench} {bret:+.0f}%", font=dict(size=11, color=CORAL)))
    return [bars(r, "Total return %", [GREEN if v >= 0 else RED for v in r["Total return %"]],
                 [f"{v:+.0f}%" for v in r["Total return %"]], "Return of each fund (name · weight)",
                 "%{x:+.1f}%<extra></extra>", mark, include=bret),
            bars(c, "Contribution pp", [BLUE if v >= 0 else RED for v in c["Contribution pp"]],
                 [f"{v:+.1f}" for v in c["Contribution pp"]], "Points each fund added to the total",
                 "%{x:+.2f} pp<extra></extra>")]
