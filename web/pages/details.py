"""Details of one position: what opens when a row of Overview > Positions or Exposure > Positions is clicked.

position(name, params) returns {"title", "eyebrow", "value", "blocks"}; static/app.js shows it in a sheet.
It joins what the snapshots know (value over time, change) with what the look-through knows (costs,
valuation, countries, sectors, top companies) when the position is a fund or stock it covers.
"""
import pandas as pd
import plotly.graph_objects as go

import config
from web import data
from web.blocks import chart, is_phone, item, items, kpi, kpis, param, shares, text
from web.theme import BLUE, MUTED, REGION_COLORS, SEQUENTIAL, eur, pct, shades, style, tone


def _history(name):
    """(value per snapshot, category) of one position; snapshots where it was not held count as 0."""
    df, to_cat = data.positions()
    if name not in df.columns:
        return None, None
    return df[name], to_cat.get(name)


def _lookthrough(name):
    """(position, fund profile) from the look-through, or (None, None) when it is not an equity it covers."""
    if not (config.FUND_SOURCES and config.LOOKTHROUGH_BENCHMARK):
        return None, None
    try:
        r = data.lookthrough_result()
    except Exception:  # a download failed: the snapshot part still shows
        return None, None
    pos = next((x for x in r["positions"] if x["label"] == name), None)
    return pos, (r["funds"].get(pos["ticker"]) if pos else None)


def _change(series, day, ref):
    if ref is None:
        return None
    return series[day] - series[ref]


def position(name, p):
    hist, category = _history(name)
    pos, fund = _lookthrough(name)
    if hist is None and pos is None:
        raise KeyError(f"no position called {name!r}")
    blocks = []
    out = {"title": name, "eyebrow": category or (pos or {}).get("type", ""), "value": None, "blocks": blocks}

    if hist is not None:
        day, portfolio = data.snapshot(param(p, "snapshot", None))
        total = sum(data.category_total(v) for v in portfolio.values())
        now = hist.get(day, 0)
        out["value"] = eur(now)
        ref = data.reference_day(day)
        cards = [kpi("Share of your wealth", pct(100 * now / total) if total else "—", f"on {day:%d %b %Y}")]
        d = _change(hist, day, ref)
        if d is not None:
            base = hist[ref]
            cards.append(kpi(f"Since {ref:%d %b}", eur(d, sign=True),
                             pct(100 * d / base, sign=True) if base else "new", tone(d)))
        year = hist.loc[:day].asof(day - pd.DateOffset(years=1)) if len(hist.loc[:day]) else None
        if year is not None and year == year and year > 0 and hist.index[0] <= day - pd.DateOffset(years=1):
            cards.append(kpi("Last 12 months", eur(now - year, sign=True), pct(100 * (now - year) / year, sign=True),
                             tone(now - year)))
        held = hist[hist > 0]
        if len(held):
            cards.append(kpi("Held since", f"{held.index[0]:%b %Y}", f"highest {eur(held.max())}"))
        blocks.append(kpis(*cards))

        color = config.ASSET_TYPES.get(category, BLUE)
        shown = hist.loc[held.index[0]:] if len(held) else hist
        fig = go.Figure(go.Scatter(x=shown.index, y=shown, mode="lines", fill="tozeroy", name=name,
                                   line=dict(color=color, width=2.5, shape="spline", smoothing=0.6),
                                   fillcolor=_alpha(color, 0.12), hovertemplate="€%{y:,.0f}<extra></extra>"))
        fig.update_yaxes(tickprefix="€", rangemode="tozero")
        blocks.append(chart(style(fig, height=240, legend=False, margin=dict(l=8, r=8, t=8, b=8))))

    if pos is not None:
        if out["value"] is None:
            out["value"] = eur(pos["eur"])
        facts = [kpi("Share of your equity", pct(pos["weight"]), pos.get("bucket") or pos["type"])]
        if pos.get("ter") is not None:
            facts.append(kpi("Yearly cost", pct(pos["ter"], 2), f"≈ {eur(pos['eur'] * pos['ter'] / 100)} a year"))
        if pos.get("pe"):
            facts.append(kpi("P/E", f"{pos['pe']:.1f}", f"P/B {pos['pb']:.1f}" if pos.get("pb") else None))
        if pos.get("em_share") is not None and pos["type"] == "ETF":
            facts.append(kpi("Emerging markets", pct(pos["em_share"])))
        blocks.append(kpis(*facts))
    if fund:
        regions = sorted(((k, v) for k, v in fund["regions"].items() if v >= 0.5), key=lambda x: -x[1])
        if regions:
            blocks.append(text("**Where its companies are**"))
            blocks.append(shares([(k, "", v, REGION_COLORS.get(k, MUTED)) for k, v in regions]))
        n = 6 if is_phone(p) else 8
        sectors = sorted(fund["sectors"].items(), key=lambda x: -x[1])[:n]
        if sectors:
            blocks.append(text("**Biggest sectors**"))
            blocks.append(shares([(k, pct(v), v, c) for (k, v), c in
                                  zip(sectors, shades(SEQUENTIAL[4], len(sectors), spread=0.6))], stack=False))
        holdings = fund.get("holdings", [])[:10]
        if holdings and pos["type"] == "ETF":
            blocks.append(text(f"**Top {len(holdings)} companies** · as of {fund.get('as_of') or '—'}"))
            blocks.append(items([item(h["name"], None, pct(h["weight"], 2), color=SEQUENTIAL[4]) for h in holdings]))
    return out


def _alpha(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"
