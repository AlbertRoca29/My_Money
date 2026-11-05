"""Overview: today's balance, the snapshot breakdown and how the portfolio evolved."""
import pandas as pd
import plotly.graph_objects as go

import config
from web import data
from web.blocks import chart, empty_page, hero, item, items, kpi, kpis, param, section, select
from web.theme import BLUE, MUTED, eur, pct, shades, style, tone

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
    df_pct, df_val = data.allocation()
    dates = list(df_val.index)
    latest, prev = df_val["Total"].iloc[-1], df_val["Total"].iloc[-2] if len(df_val) > 1 else None
    year_ago = df_val["Total"].asof(dates[-1] - pd.DateOffset(years=1))
    chips = []
    if prev is not None:
        chips.append((f"{eur(latest - prev, sign=True)} since {dates[-2]:%d %b}", tone(latest - prev)))
    if year_ago == year_ago:  # not NaN
        # wealth change, savings included: the Returns page has the market-only figures
        chips.append((f"{eur(latest - year_ago, sign=True)} in 12 months", tone(latest - year_ago)))

    snapshot_options = [(d.strftime(config.DATE_FORMAT), d.strftime("%d %b %Y")) for d in reversed(dates)]
    return {
        "hero": hero("Total wealth", eur(latest), chips,
                     caption=f"Snapshot of {dates[-1]:%d %B %Y} · {len(dates)} snapshots"),
        "controls": [
            select("snapshot", "Snapshot", snapshot_options, param(p, "snapshot", snapshot_options[0][0])),
        ],
        "sections": [s(p) for s in (snapshot_donut, snapshot_list, value_over_time, growth,
                                     allocation_over_time, smoothed_allocation, animation)],
    }


@section("Breakdown", width="half")
def snapshot_donut(p):
    """Donut of every position in the chosen snapshot, coloured by category."""
    day, portfolio = data.snapshot(param(p, "snapshot", None))
    colors = _colors_by_asset(portfolio)
    labels, values, cats = [], [], []
    for category in config.ASSET_TYPES:
        assets = portfolio.get(category) or {}
        for name, v in sorted(assets.items(), key=lambda x: -x[1]):
            if v > 0:
                labels.append(name), values.append(v), cats.append(category)
    total = sum(values)
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.68, sort=False, direction="clockwise",
        marker=dict(colors=[colors[l] for l in labels], line=dict(color="white", width=2)),
        textinfo="none", customdata=cats,
        hovertemplate="<b>%{label}</b><br>%{customdata}<br>€%{value:,.0f} · %{percent}<extra></extra>"))
    fig.update_layout(annotations=_center_label(day, total))
    by_cat = {c: data.category_total(portfolio.get(c) or {}) for c in config.ASSET_TYPES}
    chips = kpis(*[kpi(c, eur(v), pct(100 * v / total)) for c, v in by_cat.items() if v])
    return [chips, chart(style(fig, height=380, legend=False, hover="closest"))]


@section("Positions", width="half")
def snapshot_list(p):
    """Every position as a list, like the transactions list in a banking app."""
    day, portfolio = data.snapshot(param(p, "snapshot", None))
    colors = _colors_by_asset(portfolio)
    total = sum(data.category_total(v) for v in portfolio.values())

    # change of each position vs the snapshot before this one
    df_pos, _ = data.positions()
    i = df_pos.index.get_loc(day)
    before = df_pos.iloc[i - 1] if i > 0 else None

    rows = []
    for category in config.ASSET_TYPES:
        for name, v in sorted((portfolio.get(category) or {}).items(), key=lambda x: -x[1]):
            if not v:
                continue
            delta = v - before.get(name, 0) if before is not None else None
            rows.append(item(name, category, eur(v),
                             f"{pct(100 * v / total)}" + (f" · {eur(delta, sign=True)}" if delta else ""),
                             color=colors[name], tone=tone(delta)))
    return {"blocks": [items(rows)],
            "subtitle": f"{len(rows)} positions · change vs previous snapshot"}


@section("Value over time", "Stacked by category, in euros")
def value_over_time(p):
    _, df_val = data.allocation()
    return chart(_stacked(df_val.loc[_start(p):].drop(columns="Total"), "", money=True))


@section("Growth", f"Total wealth, savings included, with its {config.GROWTH_WINDOW_DAYS}-day average")
def growth(p):
    window = config.GROWTH_WINDOW_DAYS
    _, df_val = data.allocation()
    total = df_val.loc[_start(p):, "Total"].sort_index()
    daily = total.resample("D").interpolate("time")          # snapshots are irregular: use a daily grid
    trend = daily.rolling(f"{window}D").mean()
    per_day = (daily - daily.shift(window)) / window           # € per day gained over the last `window` days
    span = max((daily.index[-1] - daily.index[0]).days, 1)
    overall = (daily.iloc[-1] - daily.iloc[0]) / span
    months = max(round(span / 30.44), 1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=total.index, y=total, mode="markers", name="Snapshots",
                             marker=dict(size=7, color=BLUE, opacity=0.35),
                             hovertemplate="€%{y:,.0f}<extra>Snapshot</extra>"))
    fig.add_trace(go.Scatter(x=trend.index, y=trend, mode="lines", name=f"{window}-day average",
                             line=dict(color=BLUE, width=3, shape="spline"),
                             hovertemplate="€%{y:,.0f}<extra>average</extra>"))
    fig.update_yaxes(tickprefix="€")
    last = per_day.dropna()
    head = kpis(kpi(f"Last {window} days", f"{eur(last.iloc[-1])}/day" if len(last) else "—",
                    f"≈ {eur(last.iloc[-1] * 30)}/month" if len(last) else None,
                    tone(last.iloc[-1]) if len(last) else None),
                kpi(f"Last {months} months" if months > 1 else "Last month", f"{eur(overall)}/day",
                    f"≈ {eur(overall * 30)}/month", tone(overall)))
    return [head, chart(style(fig, height=360))]


@section("Allocation over time", "Share of the total per category", width="half")
def allocation_over_time(p):
    df_pct, _ = data.allocation()
    return chart(_stacked(df_pct.loc[_start(p):], "%", money=False).update_yaxes(range=[0, 100]))


@section("Smoothed allocation", f"{config.SMOOTHING_DAYS}-day rolling average", width="half")
def smoothed_allocation(p):
    df_pct, _ = data.allocation()
    df = df_pct.rolling(f"{config.SMOOTHING_DAYS}D").mean().loc[_start(p):]
    fig = go.Figure()
    for col in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, mode="lines",
                                 line=dict(width=2.5, shape="spline", color=config.ASSET_TYPES.get(col)),
                                 hovertemplate=f"{col}: %{{y:.1f}}%<extra></extra>"))
    fig.update_yaxes(ticksuffix="%")
    return chart(style(fig, height=360))


@section("Positions over time", "Press play — one frame per week, interpolated between snapshots")
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
