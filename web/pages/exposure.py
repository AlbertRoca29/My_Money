"""Exposure: look-through of the equity part of the latest snapshot vs the benchmark fund.

Holdings, fees and valuation ratios are downloaded from iShares, Vanguard and Avantis (cached per day,
see lookthrough.py). Cash, gold, crypto, options and private markets are excluded.
"""
import math

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
import lookthrough
from web import data
from web.blocks import chart, empty_page, hero, kpi, kpis, notes, number, param, section, table
from web.theme import (BASELINE, BLUE, BUCKET_COLORS, CORAL, GREEN, INK, MUTED, RED, REGION_COLORS, REST_COLOR,
                       SEQUENTIAL, eur, pct, shades, style, tone)

TITLE = "Exposure"
CATCH_ALL = lookthrough.CATCH_ALL


def _bt():
    return data.lookthrough_result()["benchmark"]["ticker"]


def _tables():
    return lookthrough.tables(data.lookthrough_result(), n_countries=config.N_COUNTRIES,
                              n_holdings=config.N_COMPANIES)


def _grouped_bars(df, height=None):
    """Horizontal bars: portfolio vs benchmark for each row of a lookthrough.tables() comparison."""
    bt = _bt()
    fig = go.Figure()
    for col, name, color in [("Portfolio %", "Portfolio", BLUE), (f"{bt} %", bt, CORAL)]:
        fig.add_trace(go.Bar(y=df.index, x=df[col], name=name, orientation="h", marker_color=color,
                             marker_cornerradius=4, hovertemplate=f"{name}: %{{x:.2f}}%<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#EEF0F3")
    return style(fig, height=height or 60 + 34 * len(df), barmode="group", hover="y unified", bargap=0.25)


def _diverging(series, height=None, labels=None):
    """Over/underweights in percentage points (blue = over, red = under)."""
    fig = go.Figure(go.Bar(y=series.index, x=series.values, orientation="h", marker_cornerradius=4,
                           marker_color=[BLUE if v >= 0 else RED for v in series.values],
                           text=labels, textposition="outside", textfont=dict(size=10, color=MUTED),
                           cliponaxis=False, hovertemplate="%{y}: %{x:+.2f} pp<extra></extra>"))
    lim = max(abs(series).max() * (1.6 if labels is not None else 1.15), 1)
    fig.update_xaxes(range=[-lim, lim], ticksuffix=" pp", showgrid=True, gridcolor="#EEF0F3", zeroline=True,
                     zerolinecolor=BASELINE)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return style(fig, height=height or 60 + 26 * len(series), legend=False, hover="closest")


def build(p):
    if not (config.FUND_SOURCES and config.LOOKTHROUGH_BENCHMARK):
        return empty_page("Equity analysed", "Set FUND_SOURCES and LOOKTHROUGH_BENCHMARK in config_local.py "
                                             "(see config.py).")
    if not data.portfolios():
        return empty_page("Equity analysed", "No snapshots yet: click + Snapshot to add the first one.")
    r = data.lookthrough_result()
    sp, sb, bt = r["stats"]["portfolio"], r["stats"]["benchmark"], r["benchmark"]["ticker"]
    return {
        "hero": hero("Equity analysed", eur(r["total_equity_eur"]),
                     [(f"Active share {sp['Active share vs benchmark %']:.0f}% vs {bt}", None),
                      (f"{sp['Companies held']:,} companies", None),
                      (f"Fees ≈ {eur(sp['Cost €/year'])}/yr", None)],
                     caption=f"Look-through of the {r['date'][6:]}/{r['date'][4:6]}/{r['date'][:4]} snapshot · "
                             f"fund data as of {r['benchmark']['as_of']}"),
        "controls": [number("countries", "Countries shown", param(p, "countries", 20, int), min=5, max=60),
                     number("companies", "Companies shown", param(p, "companies", 20, int), min=5, max=50)],
        "sections": [s(p) for s in (insights, scorecard, positions, market, regions, sectors, currencies,
                                     countries, active, active_companies, top_holdings, attribution,
                                     country_pies, fund_profiles, concentration, overlap, holdings_table)],
    }


@section("Key insights")
def insights(p):
    return notes(data.lookthrough_result()["insights"])


@section("Scorecard", width="half")
def scorecard(p):
    r = data.lookthrough_result()
    sp, sb = r["stats"]["portfolio"], r["stats"]["benchmark"]
    cards = kpis(kpi("P/E", f"{sp['P/E']:.1f}", f"{_bt()} {sb['P/E']:.1f}", tone(sb["P/E"] - sp["P/E"])),
                 kpi("TER", pct(sp["TER %"], 2), f"{_bt()} {pct(sb['TER %'], 2)}", tone(sb["TER %"] - sp["TER %"])),
                 kpi("Effective # companies", f"{sp['Effective # of companies']:.0f}",
                     f"{_bt()} {sb['Effective # of companies']:.0f}"))
    return [cards, table(_tables()["scorecard"])]


@section("Positions", "What each holding is and where its data comes from", width="half")
def positions(p):
    df = _tables()["positions"][["Bucket", "Data from", "€", "Weight %", "TER %", "P/E", "EM %"]]
    return table(df, {"€": eur, "Weight %": pct, "TER %": lambda v: pct(v, 2), "EM %": pct,
                      "P/E": lambda v: "—" if v != v or v is None else f"{v:.1f}"}, bar="Weight %")


@section("Developed vs emerging", "MSCI classification", width="half")
def market(p):
    m = _tables()["market"].reindex(["Developed", "Emerging", "Frontier"]).fillna(0)
    return chart(_grouped_bars(m, height=240))


@section("Sectors", "GICS", width="half")
def sectors(p):
    return chart(_grouped_bars(_tables()["sectors"]))


@section("Regions", width="half")
def regions(p):
    return chart(_grouped_bars(_tables()["regions"]))


@section("Currency of the listing market", width="half")
def currencies(p):
    cur = _tables()["currencies"]
    named = cur.drop("Other", errors="ignore")
    tail = pd.concat([named.iloc[12:], cur.loc[["Other"]] if "Other" in cur.index else None])
    cur = pd.concat([named.iloc[:12], pd.DataFrame([tail.drop(columns="Active (pp)").sum()], index=["Other"])])
    return chart(_grouped_bars(cur))


@section("Countries")
def countries(p):
    n, bt = param(p, "countries", 20, int), _bt()
    df = _tables()["countries"].drop(CATCH_ALL, errors="ignore")
    us = df.loc["United States"] if "United States" in df.index else None
    df = df.drop("United States", errors="ignore").head(n)
    sub = (f"Top {n} ex-US — United States is {us['Portfolio %']:.1f}% vs {us[f'{bt} %']:.1f}% in {bt}"
           if us is not None else f"Top {n}")
    return {"blocks": [chart(_grouped_bars(df))], "subtitle": sub}


@section("Active weights", "Percentage points over (blue) or under (red) the benchmark")
def active(p):
    n, t = param(p, "countries", 20, int), _tables()
    s = t["sectors"]["Active (pp)"].sort_values(ascending=False)
    c = t["countries"]["Active (pp)"].drop(CATCH_ALL, errors="ignore")
    c = c.reindex(c.abs().sort_values(ascending=False).index[:n]).sort_values(ascending=False)
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Sectors", f"Countries (largest {n} gaps)"),
                        horizontal_spacing=0.18)
    for col, ser in ((1, s), (2, c)):
        fig.add_trace(go.Bar(y=ser.index, x=ser.values, orientation="h", marker_cornerradius=4,
                             marker_color=[BLUE if v >= 0 else RED for v in ser.values],
                             hovertemplate="%{y}: %{x:+.2f} pp<extra></extra>"), 1, col)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(ticksuffix=" pp", showgrid=True, gridcolor="#EEF0F3", zeroline=True, zerolinecolor=BASELINE)
    fig.update_annotations(font=dict(size=13, color=INK), x=None, xanchor="left")
    for a, x in zip(fig.layout.annotations, (0, 0.59)):
        a.x = x
    return chart(style(fig, height=80 + 26 * max(len(s), len(c)), legend=False, hover="closest"))


@section("Companies: biggest over- and underweights")
def active_companies(p):
    n, bt = param(p, "companies", 20, int), _bt()
    a = sorted(data.lookthrough_result().get("active_holdings", []), key=lambda x: x["active"])
    rows = list(reversed(a[-n:])) + [x for x in reversed(a[:n]) if x not in a[-n:]]
    ser = pd.Series([x["active"] for x in rows], index=[x["name"] for x in rows])
    labels = [f"{x['weight']:.2f}% vs {x['benchmark_weight']:.2f}%" for x in rows]
    return {"blocks": [chart(_diverging(ser, labels=labels))],
            "subtitle": f"Labels: your weight vs {bt}"}


@section("Top underlying companies", "Through funds (blue), direct stake (green) and the benchmark weight (coral tick)")
def top_holdings(p):
    n, bt = param(p, "companies", 20, int), _bt()
    t = lookthrough.tables(data.lookthrough_result(), n_holdings=n)["holdings"]
    via = t["Portfolio %"] - t["Direct %"]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=t["Company"], x=via, name="Through funds", orientation="h", marker_color=BLUE,
                         customdata=t["Via"], hovertemplate="%{x:.2f}%<br>%{customdata}<extra>funds</extra>"))
    fig.add_trace(go.Bar(y=t["Company"], x=t["Direct %"], name="Direct stake", orientation="h",
                         marker_color=GREEN, hovertemplate="%{x:.2f}%<extra>direct</extra>",
                         text=[f"{v:.2f}%" for v in t["Portfolio %"]], textposition="outside",
                         textfont=dict(size=10, color=MUTED), cliponaxis=False))
    fig.add_trace(go.Scatter(y=t["Company"], x=t[f"{bt} %"], name=f"{bt} weight", mode="markers",
                             marker=dict(symbol="line-ns", size=16, line=dict(width=3, color=CORAL)),
                             hovertemplate="%{x:.2f}%<extra>" + bt + "</extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#EEF0F3")
    return chart(style(fig, height=80 + 26 * len(t), barmode="stack", hover="y unified"))


@section("Where each exposure comes from", "Stacked by strategy bucket; coral tick = benchmark weight")
def attribution(p):
    r = data.lookthrough_result()
    bt, attr, n = r["benchmark"]["ticker"], r["attribution"], param(p, "countries", 20, int)
    buckets = [b for b in BUCKET_COLORS if b in attr["sectors"]] + [b for b in attr["sectors"] if b not in BUCKET_COLORS]
    figs = []
    for dim, limit in (("sectors", None), ("regions", None), ("countries", n)):
        order = sorted(r["portfolio"][dim], key=lambda k: -r["portfolio"][dim][k])
        order = [k for k in order if r["portfolio"][dim][k] >= 0.05
                 and not (limit and k in {"United States"} | CATCH_ALL)][:limit]
        fig = go.Figure()
        for b in buckets:
            fig.add_trace(go.Bar(y=order, x=[attr[dim].get(b, {}).get(k, 0) for k in order], name=b, orientation="h",
                                 marker_color=BUCKET_COLORS.get(b, MUTED), showlegend=dim == "sectors",
                                 legendgroup=b, hovertemplate=f"{b}: %{{x:.2f}}%<extra></extra>"))
        fig.add_trace(go.Scatter(y=order, x=[r["benchmark"][dim].get(k, 0) for k in order], name=f"{bt} weight",
                                 mode="markers", showlegend=dim == "sectors",
                                 marker=dict(symbol="line-ns", size=16, line=dict(width=3, color=CORAL)),
                                 hovertemplate=f"{bt}: %{{x:.2f}}%<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#EEF0F3")
        title = {"sectors": "Sectors", "regions": "Regions", "countries": f"Top {n} countries, ex-US"}[dim]
        figs.append(chart(style(fig, height=(110 if dim == "sectors" else 60) + 28 * len(order), barmode="stack",
                                hover="y unified", title=dict(text=title, x=0, font=dict(size=14)),
                                margin=dict(l=8, r=8, t=90 if dim == "sectors" else 40, b=8))))
    return figs


def _country_slices(countries, min_pct=1.0, max_slices=12):
    """(labels, values, colours) for one pie: countries grouped by region (hue), then 'Rest of the world'."""
    labels, values, colors = lookthrough._country_slices(countries, min_pct, max_slices)
    by_region = {}
    for label in labels:
        by_region.setdefault(lookthrough.region(lookthrough.COUNTRY_CODES.get(label, label)), []).append(label)
    out_colors = {}
    for reg, names in by_region.items():
        out_colors.update(zip(names, shades(REGION_COLORS.get(reg, MUTED), len(names))))
    return labels, values, [out_colors[l] if not l.startswith("Rest of") else REST_COLOR for l in labels]


@section("Country mix — portfolio, benchmark and each fund", "Colour = continent (blue Americas, green Europe, "
         "violet Asia-Pacific, coral Middle East & Africa); lighter = smaller country; grey = countries under 1%")
def country_pies(p):
    r = data.lookthrough_result()
    bt = r["benchmark"]["ticker"]
    panels = [("Portfolio", r["portfolio"]["countries"]), (f"{bt} (benchmark)", r["benchmark"]["countries"])]
    for pos in sorted((x for x in r["positions"] if x["type"] == "ETF"), key=lambda x: -x["weight"]):
        panels.append((f"{pos['label']} · {pos['weight']:.0f}%", r["funds"][pos["ticker"]]["countries"]))
    direct = r.get("attribution", {}).get("countries", {}).get("Direct stocks")
    if direct:
        panels.append(("Direct stocks", direct))

    ncols = 3
    nrows = math.ceil(len(panels) / ncols)
    fig = make_subplots(rows=nrows, cols=ncols, specs=[[{"type": "domain"}] * ncols] * nrows,
                        subplot_titles=[t for t, _ in panels], vertical_spacing=0.06)
    for i, (title, ctry) in enumerate(panels):
        labels, values, colors = _country_slices(ctry)
        codes = [lookthrough.COUNTRY_CODES.get(l, "") for l in labels]
        fig.add_trace(go.Pie(labels=labels, values=values, hole=0.55, sort=False, direction="clockwise",
                             marker=dict(colors=colors, line=dict(color="white", width=1.5)),
                             text=codes, textinfo="text", textposition="inside",
                             texttemplate=["%{text}" if v >= 6 else "" for v in values],
                             hovertemplate="<b>%{label}</b><br>%{value:.1f}%<extra>" + title + "</extra>"),
                      i // ncols + 1, i % ncols + 1)
    fig.update_annotations(font=dict(size=13, color=INK))
    return chart(style(fig, height=300 * nrows, legend=False, hover="closest", margin=dict(l=8, r=8, t=40, b=8)))


@section("What each fund brings", "Sector and country mix of every fund, next to the portfolio and the benchmark (%)")
def fund_profiles(p):
    r = data.lookthrough_result()
    n, bt = param(p, "countries", 20, int), r["benchmark"]["ticker"]
    cols = [("Portfolio", r["portfolio"]), (f"{bt}", r["benchmark"])]
    cols += [(x["label"], r["funds"][x["ticker"]]) for x in r["positions"] if x["type"] == "ETF" and x["ticker"] != bt]
    blocks = []
    for dim, rows in (("sectors", [s for s in r["portfolio"]["sectors"] if r["portfolio"]["sectors"][s] >= 0.05]),
                      ("countries", [c for c in r["portfolio"]["countries"] if c not in CATCH_ALL][:n])):
        z = [[c[dim].get(k, 0) for _, c in cols] for k in rows]
        fig = go.Figure(go.Heatmap(
            z=z, x=[c for c, _ in cols], y=rows, colorscale=[[i / 6, c] for i, c in enumerate(SEQUENTIAL)],
            showscale=False, xgap=3, ygap=3, text=[[("·" if v < 0.05 else f"{v:.1f}") for v in row] for row in z],
            texttemplate="%{text}", textfont=dict(size=10),
            hovertemplate="%{x} · %{y}: %{z:.2f}%<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(side="top", tickangle=-30)
        blocks.append(chart(style(fig, height=120 + 30 * len(rows), legend=False, hover="closest")))
    return blocks


@section("Concentration", "Weight held by the largest N companies (log scale)", width="half")
def concentration(p):
    r = data.lookthrough_result()
    bt, sp, sb = r["benchmark"]["ticker"], r["stats"]["portfolio"], r["stats"]["benchmark"]
    fig = go.Figure()
    for key, color, name, stats in (("portfolio", BLUE, "Portfolio", sp), ("benchmark", CORAL, bt, sb)):
        x, y = zip(*r["concentration"][key])
        fig.add_trace(go.Scatter(x=x, y=y, name=f"{name} ≈ {stats['Effective # of companies']:.0f} equal-weight cos.",
                                 line=dict(color=color, width=3, shape="spline"),
                                 hovertemplate="top %{x}: %{y:.1f}%<extra>" + name + "</extra>"))
    fig.update_xaxes(type="log", title="number of companies")
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    return chart(style(fig, height=380, hover="closest"))


@section("Fund overlap", "% of holdings two funds have in common", width="half")
def overlap(p):
    o = data.lookthrough_result()["overlap"]
    z = [[None if i == j else v for j, v in enumerate(row)] for i, row in enumerate(o["matrix"])]
    fig = go.Figure(go.Heatmap(z=z, x=o["labels"], y=o["labels"], zmin=0, zmax=100, showscale=False, xgap=3, ygap=3,
                               colorscale=[[i / 6, c] for i, c in enumerate(SEQUENTIAL)],
                               text=[["—" if v is None else f"{v:.0f}%" for v in row] for row in z],
                               texttemplate="%{text}", hovertemplate="%{y} & %{x}: %{z:.0f}%<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(tickangle=-30)
    return chart(style(fig, height=380, legend=False, hover="closest"))


@section("Top companies — table", "Your weight, the euros behind it and which funds it comes from")
def holdings_table(p):
    bt = _bt()
    t = _tables()["holdings"]
    return table(t, {"Portfolio %": lambda v: pct(v, 2), "€": eur, f"{bt} %": lambda v: pct(v, 2),
                     "Direct %": lambda v: pct(v, 2) if v else "—"}, index=False)
