"""Returns: how much the money you put in has earned (MWR / TWR) and how the benchmark ETF would have done.

Net savings come from cashflows.csv (see mwr.py for how it is built from the Gastos sheet).
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
import mwr
from web import data
from web.blocks import action, chart, empty_page, hero, kpi, kpis, notes, raw, section, table, text
from web.theme import BASELINE, BLUE, CORAL, GREEN, MUTED, RED, eur, frac, style, tone

TITLE = "Returns"


def build(p):
    data.auto_sync_sheet()  # re-download the Gastos sheet if cashflows.csv is old (config.SHEET_AUTO_SYNC_HOURS)
    if len(data.portfolios()) < 2:
        return empty_page("Return on the money you put in", "Returns need at least two snapshots (+ Snapshot).")
    if not config.CASHFLOWS_CSV.exists():
        return empty_page("Return on the money you put in", "No savings yet: add them below.", [update_savings(p)])
    snaps, flows = data.snaps_and_flows()
    s = mwr.summary(snaps, flows).iloc[0]
    _, twr_annual = mwr.twr(snaps, flows)
    return {
        "hero": hero("Return on the money you put in", f"{s['annual']:.1%}",
                     [(f"{eur(s['gain'], sign=True)} market gain", tone(s["gain"])),
                      (f"{eur(s['saved'])} saved since {s['from']:%b %Y}", None),
                      (f"Time-weighted {twr_annual:.1%}/yr", tone(twr_annual))],
                     caption=f"Savings up to {flows[-1][0]:%d %b %Y} · latest snapshot {snaps[-1][0]:%d %b %Y}",
                     unit="/yr"),
        "controls": [],
        "sections": [sec(p) for sec in (periods, money_in, monthly, vs_benchmark, update_savings)],
    }


@section("Money-weighted return", "Your net savings count as deposits; the snapshot total (cash included) "
                                  "is what they grew into")
def periods(p):
    snaps, flows = data.snaps_and_flows()
    df = mwr.summary(snaps, flows)
    twr_total, twr_annual = mwr.twr(snaps, flows)
    cards = kpis(*[kpi(name, f"{r['annual']:.1%}/yr", f"{eur(r['gain'], sign=True)} · {r['period']:.1%} over period",
                       tone(r["annual"])) for name, r in df.iterrows()],
                 kpi("Time-weighted", f"{twr_annual:.1%}/yr", f"{twr_total:.1%} total · ignores when money came in",
                     tone(twr_annual)))
    df = df.rename(columns={"annual": "MWR / yr", "period": "MWR over period"})
    fmt = {"start": eur, "saved": eur, "end": eur, "gain": lambda x: eur(x, sign=True),
           "MWR / yr": frac, "MWR over period": frac, "from": str, "to": str}
    return [cards, table(df, fmt, toned=("gain", "MWR / yr", "MWR over period"))]


@section("Portfolio vs money put in", "Money put in = value on the first snapshot + net savings since")
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


@section("Each month: saved vs market gain", "Label = market return that month (gaps over 45 days skipped)")
def monthly(p, max_gap_days=45):
    snaps, flows = data.snaps_and_flows()
    iv = mwr.intervals(snaps, flows)
    iv = iv[(pd.to_datetime(iv["to"]) - pd.to_datetime(iv["from"])).dt.days <= max_gap_days]
    month = pd.to_datetime(iv["to"]).dt.to_period("M")
    m = iv.groupby(month)[["saved", "gain"]].sum()
    m["return"] = iv.groupby(month)["return"].apply(lambda r: (1 + r).prod() - 1)  # compound within the month
    x = [p.strftime("%b %y") for p in m.index]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=m["saved"], name=f"Saved — {eur(m['saved'].sum())}", marker_color=CORAL,
                         marker_cornerradius=6, hovertemplate="€%{y:,.0f}<extra>saved</extra>"))
    fig.add_trace(go.Bar(x=x, y=m["gain"], name=f"Market gain — {eur(m['gain'].sum(), sign=True)}",
                         marker_color=[GREEN if g >= 0 else RED for g in m["gain"]], marker_cornerradius=6,
                         text=[f"{r:+.1%}" for r in m["return"]], textposition="outside",
                         textfont=dict(color=MUTED, size=10), cliponaxis=False,
                         hovertemplate="%{y:+,.0f} €<extra>market</extra>"))
    fig.update_yaxes(tickprefix="€")
    return chart(style(fig, height=400, barmode="group"))


@section(f"Benchmark: the same savings in {config.BENCHMARK_NAME}", "Each alternative starts with your first snapshot's value, gets "
         "exactly the same savings on the same days, and keeps a cash buffer (earning 0%)")
def vs_benchmark(p):
    if not config.BENCHMARK_ISIN:
        return None  # no benchmark set in config_local.py
    snaps, flows = data.snaps_and_flows()
    alts = data.alternatives()
    cmp = mwr.compare(snaps, flows, alts)
    # one column per scenario: "11.6%/yr · €23,098"
    table_df = pd.DataFrame({who: [f"{frac(m)}/yr · {eur(e)}" for m, e in zip(cmp[(who, 'MWR / yr')], cmp[(who, 'end')])]
                             for who in dict.fromkeys(w for w, _ in cmp.columns)}, index=cmp.index)

    dates = pd.to_datetime([d for d, _ in snaps])
    value = pd.Series([v for _, v in snaps], index=dates)
    put_in = value - pd.Series(np.r_[0, mwr.intervals(snaps, flows)["gain"].cumsum()], index=dates)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.07)
    fig.add_trace(go.Scatter(x=dates, y=put_in, name=f"Money put in — {eur(put_in.iloc[-1])}",
                             line=dict(color=MUTED, width=1.5, dash="dot"),
                             hovertemplate="€%{y:,.0f}<extra>put in</extra>"), 1, 1)
    lines, colors = [], [CORAL, GREEN, "#F2B705"]
    for (name, s), c in zip(alts.items(), colors):
        fig.add_trace(go.Scatter(x=s.index, y=s, name=f"{name} — {eur(s.iloc[-1])}", line=dict(color=c, width=2),
                                 hovertemplate="€%{y:,.0f}<extra>" + name + "</extra>"), 1, 1)
        diff = value - s.reindex(dates)
        fig.add_trace(go.Scatter(x=dates, y=diff, name=f"You vs {name}: {eur(diff.iloc[-1], sign=True)}",
                                 mode="lines+markers", marker=dict(size=4), line=dict(color=c, width=2),
                                 hovertemplate="%{y:+,.0f} €<extra>vs " + name + "</extra>"), 2, 1)
        total, annual = mwr.twr(mwr.at_snapshots(s, snaps), flows)
        lines.append(f"{name}: time-weighted **{total:.1%}** total, **{annual:.1%}/yr**")
    fig.add_trace(go.Scatter(x=dates, y=value, name=f"You — {eur(value.iloc[-1])}", line=dict(color=BLUE, width=3),
                             mode="lines+markers", marker=dict(size=5),
                             hovertemplate="€%{y:,.0f}<extra>you</extra>"), 1, 1)
    fig.add_hline(y=0, line=dict(color=BASELINE, width=1), row=2, col=1)
    fig.update_yaxes(tickprefix="€")
    you_total, you_annual = mwr.twr(snaps, flows)
    lines.insert(0, f"You: time-weighted **{you_total:.1%}** total, **{you_annual:.1%}/yr**. "
                    "Lower chart: above 0 means you are ahead.")
    return [table(table_df), chart(style(fig, height=600)), notes(lines)]


@section("Update savings", "Net savings come from the TOTAL and INGRESOS tabs of the Gastos sheet. "
         "Rows typed “📈 Investments” are returns, so they are left out.")
def update_savings(p):
    snaps, flows = data.snaps_and_flows()
    age = data.cashflows_age_hours()
    status = (f"cashflows.csv: {len(flows)} days, last {flows[-1][0]:%d %b %Y} · "
              f"updated {'less than an hour' if age < 1 else f'{age:.0f} hours' if age < 48 else f'{age / 24:.0f} days'} ago")
    blocks = []
    if data.sheet_configured():
        auto = config.SHEET_AUTO_SYNC_HOURS
        blocks.append(action("Sync from Google Sheets", "/api/sheet-sync",
                             status + (f" · syncs by itself when older than {auto} h" if auto else "")))
        if data.last_auto_sync_error:
            blocks.append(notes([f"**Automatic sync failed:** {data.last_auto_sync_error}"]))
    else:
        blocks.append(notes(["**Connect the sheet:** paste its link into GASTOS_SHEET_URL in config.py "
                             "(see sheets.py for access)."]))
    blocks.append(text("Or upload the CSV downloads by hand (File › Download › CSV):"))
    blocks.append(raw("upload", action="/api/cashflows", fields=[("total", "TOTAL.csv"), ("ingresos", "INGRESOS.csv")],
                      status="" if data.sheet_configured() else status))
    return blocks
