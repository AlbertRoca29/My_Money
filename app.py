"""My Money — the portfolio tracker as a website.

Run it:
    .venv/bin/python app.py          then open http://127.0.0.1:8050

How it fits together
    config.py          every setting (folders, colours, fund sources, backtest options...)
    web/data.py        loads snapshots / cash flows and runs mwr.py, lookthrough.py, backtest.py (cached)
    web/pages/*.py     one file per page: build(params) returns the hero, the controls and the sections
    web/blocks.py      the building blocks those pages are made of (kpis, chart, table, list...)
    web/theme.py       colours, number formats and the Plotly chart style
    templates/, static/  the browser side: it only draws what the Python pages return

This file only maps URLs to those functions. Every route returns JSON except "/".
"""
import tempfile
from pathlib import Path

import plotly
from flask import Flask, abort, jsonify, render_template, request, send_file

import config
from web import data
from web.pages import PAGES

app = Flask(__name__)
app.json.sort_keys = False  # keep categories and assets in the order they were written


@app.get("/")
def index():
    """The single HTML page. Navigation between pages happens in the browser (static/app.js)."""
    return render_template("index.html", pages={k: m.TITLE for k, m in PAGES.items()})


@app.get("/plotly.min.js")
def plotly_js():
    """Serve the Plotly.js that ships with the installed plotly package, so versions always match."""
    return send_file(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", max_age=86400)


@app.get("/api/page/<name>")
def page(name):
    """Build a page. The query string carries the values of the page's controls."""
    if name not in PAGES:
        abort(404)
    try:
        return jsonify(PAGES[name].build(request.args.to_dict()))
    except Exception as exc:  # e.g. a download failed before any section could run
        app.logger.exception("page %s failed", name)
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


# ---------------------------------------------------------------------------
# Snapshot editor
# ---------------------------------------------------------------------------
@app.get("/api/snapshot")
def get_snapshot():
    """A snapshot to start editing from (the latest unless ?date=YYYYMMDD), plus the known categories."""
    day, portfolio = data.snapshot(request.args.get("date") or None)
    return jsonify({"date": day.strftime("%Y-%m-%d"), "portfolio": portfolio,
                    "categories": config.ASSET_TYPES,
                    "dates": [d.strftime("%Y-%m-%d") for d in reversed(list(data.portfolios()))]})


@app.post("/api/snapshot")
def post_snapshot():
    """Save {"date": "YYYY-MM-DD", "portfolio": {category: {asset: amount}}} as portfolios/YYYYMMDD.json."""
    body = request.get_json(force=True)
    try:
        path, existed = data.save_snapshot(body["date"], body["portfolio"])
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"Could not save: {exc}"}), 400
    return jsonify({"saved": path.name, "replaced": existed})


@app.post("/api/cashflows")
def post_cashflows():
    """Rebuild cashflows.csv from the uploaded TOTAL and INGRESOS CSV downloads."""
    if not {"total", "ingresos"} <= set(request.files):
        return jsonify({"error": "Both TOTAL.csv and INGRESOS.csv are needed."}), 400
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for key in ("total", "ingresos"):
            paths[key] = Path(tmp) / f"{key}.csv"
            request.files[key].save(paths[key])
        try:
            data.save_cashflows(paths["total"], paths["ingresos"])
        except (KeyError, ValueError) as exc:
            return jsonify({"error": f"Unexpected CSV format: {exc}"}), 400
    _, flows = data.snaps_and_flows()
    return jsonify({"status": f"cashflows.csv: {len(flows)} days, last {flows[-1][0]:%d %b %Y}"})


@app.post("/api/sheet-sync")
def sheet_sync():
    """Download the Gastos Google Sheet and rebuild cashflows.csv (sheets.py)."""
    try:
        return jsonify({"status": data.sync_sheet()})
    except Exception as exc:  # no access, wrong link, no internet...
        app.logger.exception("sheet sync failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 400


if __name__ == "__main__":
    # debug=True: the server restarts by itself whenever you save a .py file
    app.run(host=config.HOST, port=config.PORT, debug=True)
