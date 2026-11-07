"""Overview: today's balance, the snapshot breakdown and how the portfolio evolved."""
import pandas as pd
import plotly.graph_objects as go

import config
from web import data
from web.blocks import (chart, empty_page, hero, is_phone, item, items, kpi, kpis, mosaic, param, piece, section,
                        select, shares)
from web.theme import BLUE, MUTED, RED, eur, ink_on, pct, shades, style, tone

TITLE = "Overview"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _start(p):
    """First date of the trend charts (Settings > Overview)."""
    return pd.Timestamp(param(p, "trends_from", config.OVERVIEW_START))


def _colors_by_asset(portfolio):
    """{asset: colour}: every asset gets a shade of its category colour, biggest first."""
    out = {}
    for category, assets in portfolio.items():
        base = config.ASSET_TYPES.get(category, config.ASSET_TYPES["Other"])
        ranked = sorted(assets.items(), key=lambda x: -x[1]) if isinstance(assets, dict) else [(category, assets)]
        for (name, _), color in zip(ranked, shades(base, len(ranked))):
            out[name] = color
    return out


def _center_label(day, total):
    """Date and total written in the hole of a donut."""
    return [dict(text=f"{day:%d %b %Y}", y=0.57, showarrow=False, font=dict(size=13, color=MUTED)),
            dict(text=f"<b>{eur(total)}</b>", y=0.46, showarrow=False, font=dict(size=28))]


def _timed(fig, p):
    """Settings > Look: 1Y / 3Y / All buttons above a time chart (not on a phone: too small for a finger and they
    collide with the legend), and smooth (curved) lines."""
    if param(p, "smooth", True, bool):
        fig.update_traces(line_shape="spline", selector=dict(type="scatter", mode="lines"))
    if param(p, "range_buttons", True, bool) and not is_phone(p):
        fig.update_xaxes(rangeselector=dict(
            buttons=[dict(count=6, label="6M", step="month", stepmode="backward"),
                     dict(count=1, label="1Y", step="year", stepmode="backward"),
                     dict(count=3, label="3Y", step="year", stepmode="backward"), dict(step="all", label="All")],
            x=1, xanchor="right", y=1.12, bgcolor="#F1F3F6", activecolor="#191C1F", bordercolor="rgba(0,0,0,0)",
            font=dict(size=11, color="#505A63")))
    return fig


def _stacked(df, ysuffix, money):
    fig = go.Figure()
    for col in df.columns:
        color = config.ASSET_TYPES.get(col, config.OTHERS_COLOR)
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], name=col, stackgroup="one", mode="lines",
            line=dict(width=1.2, color=color), fillcolor=color, opacity=0.9,
            hovertemplate=(f"{col}: €%{{y:,.0f}}<extra></extra>" if money else f"{col}: %{{y:.1f}}%<extra></extra>")))
    fig.update_yaxes(ticksuffix=ysuffix if not money else "", tickprefix="€" if money else "")
    return style(fig, height=360)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def build(p):
    if not data.portfolios():
        return empty_page("Total wealth", "No snapshots yet: click + Snapshot to add the first one.")
    _, df_val = data.allocation()
    dates = list(df_val.index)
    day, _ = data.snapshot(param(p, "snapshot", None))
    total = df_val["Total"]
    now = total[day]
    stats = []  # what changed: over about a month (the oldest snapshot of the last 30 days) and over a year
    ref = data.reference_day(day)
    if ref is not None:
        d = now - total[ref]
        stats.append((f"Since {ref:%d %b}", f"{eur(d, sign=True)} · {pct(100 * d / total[ref], sign=True).replace('-', '−')}", tone(d)))
    year_ago = total.loc[:day].asof(day - pd.DateOffset(years=1))
    if year_ago == year_ago:  # not NaN
        d = now - year_ago
        stats.append(("Last 12 months", f"{eur(d, sign=True)} · {pct(100 * d / year_ago, sign=True).replace('-', '−')}", tone(d)))

    snapshot_options = [(d.strftime(config.DATE_FORMAT), d.strftime("%d %b %Y")) for d in reversed(dates)]
    # on a phone: no smoothed copy of the allocation chart and no play-button animation (computer only)
    shown = (snapshot_donut, snapshot_list, value_over_time, growth, allocation_over_time, smoothed_allocation,
             drawdown, top_positions, animation)
    if is_phone(p):
        shown = tuple(s for s in shown if s not in (smoothed_allocation, animation))
    return {
        "hero": hero("Total wealth", eur(now), caption=f"{day:%d %B %Y}", stats=stats),
        "controls": [
            select("snapshot", "Snapshot", snapshot_options, day.strftime(config.DATE_FORMAT), arrows=True,
                   groups=[d.year for d in reversed(dates)]),
        ],
        "sections": [s(p) for s in shown],
    }


@section("Breakdown", width="half")
def snapshot_donut(p):
    """The chosen snapshot by category (one bar, its parts named underneath), then every position as a rounded
    tile whose size is its value, grouped by category (drawn by the browser: the "mosaic" block)."""
    day, portfolio = data.snapshot(param(p, "snapshot", None))
    colors = _colors_by_asset(portfolio)
    by_cat = {c: data.category_total(portfolio.get(c) or {}) for c in config.ASSET_TYPES}
    total = sum(v for v in by_cat.values() if v > 0)
    parts = shares([(c, eur(v), 100 * v / total, config.ASSET_TYPES[c]) for c, v in by_cat.items() if v > 0])

    groups = []
    for category in config.ASSET_TYPES:
        assets = portfolio.get(category) or {}
        if not isinstance(assets, dict):
            assets = {category: assets}
        tiles = [piece(name, v, 100 * v / total, colors[name], ink_on(colors[name]), sub=eur(v), detail=name)
                 for name, v in sorted(assets.items(), key=lambda x: -x[1]) if v > 0]
        groups.append((category, tiles))
    return [parts, mosaic(groups)]


@section("Positions", width="half")
def snapshot_list(p):
    """Every position as a list, like the transactions list in a banking app. A row opens its details."""
    day, portfolio = data.snapshot(param(p, "snapshot", None))
    colors = _colors_by_asset(portfolio)
    total = sum(data.category_total(v) for v in portfolio.values())

    # change of each position over about a month (vs the oldest snapshot of the last 30 days)
    df_pos, _ = data.positions()
    ref = data.reference_day(day)
    before = df_pos.loc[ref] if ref is not None else None

    rows = []
    for category in config.ASSET_TYPES:
        for name, v in sorted((portfolio.get(category) or {}).items(), key=lambda x: -x[1]):
            if not v:
                continue
            delta = v - before.get(name, 0) if before is not None else None
            rows.append(item(name, category, eur(v),
                             f"{pct(100 * v / total)}" + (f" · {eur(delta, sign=True)}" if delta else ""),
                             color=colors[name], tone=tone(delta), detail=name))
    return {"blocks": [items(rows)],
            "subtitle": f"{len(rows)} positions" + (f" · change since {ref:%d %b}" if ref is not None else "")}


@section("Value over time")
def value_over_time(p):
    _, df_val = data.allocation()
    return chart(_timed(_stacked(df_val.loc[_start(p):].drop(columns="Total"), "", money=True), p))


@section("Growth")
def growth(p):
    window = config.GROWTH_WINDOW_DAYS
    _, df_val = data.allocation()
    total = df_val.loc[_start(p):, "Total"].sort_index()
    daily = total.resample("D").interpolate("time")          # snapshots are irregular: use a daily grid
    trend = daily.rolling(f"{window}D").mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=total.index, y=total, mode="lines", name="Total wealth",
                             line=dict(color=BLUE, width=1.5), opacity=0.35,
                             hovertemplate="€%{y:,.0f}<extra>snapshot</extra>"))
    fig.add_trace(go.Scatter(x=trend.index, y=trend, mode="lines", name=f"Trend ({window}-day average)",
                             line=dict(color=BLUE, width=3, shape="spline"),
                             hovertemplate="€%{y:,.0f}<extra>trend</extra>"))
    fig.update_yaxes(tickprefix="€")
    full = df_val["Total"]
    year_ago = full.asof(full.index[-1] - pd.DateOffset(years=1))
    if year_ago == year_ago:
        gained = full.iloc[-1] - year_ago
        head = kpis(kpi("Last 12 months", eur(gained, sign=True), f"≈ {eur(gained / 12, sign=True)} a month", tone(gained)))
    else:  # less than a year of snapshots: since the first one
        months = max((full.index[-1] - full.index[0]).days / 30.44, 1)
        gained = full.iloc[-1] - full.iloc[0]
        head = kpis(kpi(f"Since {full.index[0]:%b %Y}", eur(gained, sign=True), f"≈ {eur(gained / months, sign=True)} a month",
                        tone(gained)))
    return [head, chart(_timed(style(fig, height=360), p))]


@section("Allocation over time", width="half")
def allocation_over_time(p):
    df_pct, _ = data.allocation()
    return chart(_timed(_stacked(df_pct.loc[_start(p):], "%", money=False).update_yaxes(range=[0, 100]), p))


@section("Smoothed allocation", width="half")
def smoothed_allocation(p):
    df_pct, _ = data.allocation()
    df = df_pct.rolling(f"{config.SMOOTHING_DAYS}D").mean().loc[_start(p):]
    fig = go.Figure()
    for col in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, mode="lines",
                                 line=dict(width=2.5, shape="spline", color=config.ASSET_TYPES.get(col)),
                                 hovertemplate=f"{col}: %{{y:.1f}}%<extra></extra>"))
    fig.update_yaxes(ticksuffix="%")
    return chart(_timed(style(fig, height=360), p))


@section("Drawdown", width="half")
def drawdown(p):
    _, df_val = data.allocation()
    total = df_val["Total"].loc[_start(p):]
    dd = 100 * (total / total.cummax() - 1)
    fig = go.Figure(go.Scatter(x=dd.index, y=dd, mode="lines", fill="tozeroy", name="Drawdown",
                               line=dict(color=RED, width=2), fillcolor="rgba(217,104,108,.14)",
                               hovertemplate="%{y:.1f}%<extra>below peak</extra>"))
    fig.update_yaxes(ticksuffix="%", range=[min(dd.min() * 1.15, -1), 0.5])
    return [kpis(kpi("Now", pct(dd.iloc[-1]), "below the peak" if dd.iloc[-1] < -0.05 else "at the peak", tone(dd.iloc[-1])),
                 kpi("Deepest", pct(dd.min()), f"{dd.idxmin():%b %Y}", tone(dd.min()))),
            chart(_timed(style(fig, height=300, legend=False), p).update_traces(line_shape="linear"))]  # a curve would overshoot the peak


@section("Biggest positions", width="half")
def top_positions(p):
    day, portfolio = data.snapshot(param(p, "snapshot", None))
    colors = _colors_by_asset(portfolio)
    flat = [(n, v) for assets in portfolio.values() if isinstance(assets, dict) for n, v in assets.items() if v > 0]
    total = sum(v for _, v in flat)
    top = sorted(flat, key=lambda x: -x[1])[:10][::-1]
    fig = go.Figure(go.Bar(y=[n for n, _ in top], x=[100 * v / total for _, v in top], orientation="h",
                           marker=dict(color=[colors.get(n, MUTED) for n, _ in top], cornerradius=6),
                           customdata=[v for _, v in top], text=[pct(100 * v / total) for _, v in top], textposition="outside",
                           cliponaxis=False, hovertemplate="<b>%{y}</b><br>€%{customdata:,.0f}<extra></extra>"))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False)
    top3 = sum(v for _, v in sorted(flat, key=lambda x: -x[1])[:3])
    return [kpis(kpi("Top 3 together", pct(100 * top3 / total), eur(top3))),
            chart(style(fig, height=340, legend=False, hover="closest", margin=dict(l=8, r=48, t=8, b=8)))]


@section("Positions over time")
def animation(p):
    df_pos, asset_to_cat = data.positions()
    df = df_pos.resample(config.ANIMATION_FREQ).mean().interpolate("linear")
    order = [c for cat in config.ASSET_TYPES for c in sorted(df.columns) if asset_to_cat.get(c) == cat]
    colors = {}
    for cat in config.ASSET_TYPES:
        cols = [c for c in order if asset_to_cat.get(c) == cat]
        colors.update(zip(cols, shades(config.ASSET_TYPES[cat], len(cols))))

    def pie(row):
        names = [c for c in order if row[c] > 0]
        values = [row[c] for c in names]
        total = sum(values)
        return go.Pie(labels=names, values=values, hole=0.6, sort=False, direction="clockwise",
                      marker=dict(colors=[colors[c] for c in names], line=dict(color="white", width=1.5)),
                      # name only on slices of at least 6%; the rest are on hover
                      texttemplate=["%{label}<br>%{percent}" if v >= 0.06 * total else "" for v in values],
                      textposition="inside", insidetextorientation="horizontal",
                      hovertemplate="<b>%{label}</b><br>€%{value:,.0f} · %{percent}<extra></extra>")

    frames = [go.Frame(data=[pie(row)], name=f"{d:%Y-%m-%d}", layout=dict(annotations=_center_label(d, row["Total"])))
              for d, row in df.iterrows()]
    fig = go.Figure(data=frames[-1].data, frames=frames, layout=dict(annotations=frames[-1].layout.annotations))
    fig.update_layout(
        updatemenus=[dict(type="buttons", showactive=False, x=0, y=-0.02, xanchor="left", yanchor="top",
                          pad=dict(t=0, r=10), bgcolor="#191C1F", font=dict(color="white"),
                          bordercolor="#191C1F",
                          buttons=[dict(label="▶  Play", method="animate",
                                        args=[None, dict(frame=dict(duration=140, redraw=True), fromcurrent=False,
                                                         transition=dict(duration=0))])])],
        sliders=[dict(active=len(frames) - 1, x=0.12, len=0.88, y=-0.02, pad=dict(t=0),
                      currentvalue=dict(visible=False), bgcolor="#C9D0D8", bordercolor="#C9D0D8", borderwidth=3,
                      activebgcolor=BLUE, tickcolor="rgba(0,0,0,0)", font=dict(color="rgba(0,0,0,0)"),
                      steps=[dict(method="animate", label=f.name,
                                  args=[[f.name], dict(mode="immediate", frame=dict(duration=0, redraw=True))])
                             for f in frames])])
    return chart(style(fig, height=560, legend=False, hover="closest", margin=dict(l=8, r=8, t=10, b=60)))
