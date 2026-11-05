"""My Money — Gastos (expenses and income) and the portfolio tracker, on one website.

Run it:
    .venv/bin/python app.py          then open http://127.0.0.1:8050
    MY_MONEY_HOST=0.0.0.0 .venv/bin/python app.py     to open it from your phone on the same Wi-Fi

    /               Gastos, the default (gastos/: its own blueprint, plain HTML/JS in gastos/web/)
    /portfolio      the portfolio tracker (everything below)

How it fits together
    config.py          every setting (folders, colours, fund sources, backtest options...)
    web/data.py        loads snapshots / cash flows and runs mwr.py, lookthrough.py, backtest.py (cached)
    web/pages/*.py     one file per page: build(params) returns the hero, the controls and the sections
    web/blocks.py      the building blocks those pages are made of (kpis, chart, table, list...)
    web/theme.py       colours, number formats and the Plotly chart style
    templates/, static/  the browser side: it only draws what the Python pages return

This file only maps URLs to those functions. Every route returns JSON except "/portfolio".
"""
import os
from pathlib import Path

import plotly
from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

import auth
import config
import settings
from gastos.routes import bp as gastos
from web import data
from web.pages import PAGES

app = Flask(__name__)
app.json.sort_keys = False  # keep categories and assets in the order they were written
if auth.ON_CLOUD_RUN:  # behind Google's proxy: trust its https:// and host, for the sign-in redirect URL
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
auth.init(app)                  # Sign in with Google (auth.py); off on your own computer
app.register_blueprint(gastos)  # "/" and its /api/entries, /api/receipts… routes


@app.get("/portfolio")
def index():
    """The single HTML page. Navigation between pages happens in the browser (static/app.js)."""
    hidden = [] if settings.get("show_backtest") else ["backtest"]  # Settings > Backtest
    return render_template("index.html", pages={k: m.TITLE for k, m in PAGES.items()}, hidden=hidden)


@app.get("/plotly.min.js")
def plotly_js():
    """Serve the Plotly.js that ships with the installed plotly package, so versions always match."""
    return send_file(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", max_age=86400)


@app.get("/api/page/<name>")
def page(name):
    """Build a page. Its params are the saved settings (settings.py), overridden by the query string, which
    carries the values of the page's controls (and phone=1 on a small screen)."""
    if name not in PAGES:
        abort(404)
    try:
        return jsonify(PAGES[name].build({**settings.current(), **request.args.to_dict()}))
    except Exception as exc:  # e.g. a download failed before any section could run
        app.logger.exception("page %s failed", name)
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


# ---------------------------------------------------------------------------
# Settings (the ⚙ sheet; Gastos uses the same ones)
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    return jsonify(settings.schema())


@app.post("/api/settings")
def post_settings():
    try:
        return jsonify(settings.save(request.get_json(force=True)))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


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
    """Save {"date": "YYYY-MM-DD", "portfolio": {category: {asset: amount}}} in the Snapshots tab."""
    body = request.get_json(force=True)
    try:
        day, existed = data.save_snapshot(body["date"], body["portfolio"])
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"Could not save: {exc}"}), 400
    return jsonify({"saved": f"{day:%d %b %Y}", "replaced": existed})


@app.post("/tasks/refresh")
@auth.task
def refresh():
    """Run every night by Cloud Scheduler: download today's prices and fund holdings and work out the
    heavy pages, so they open at once during the day. Each part can fail without stopping the others."""
    done = {}
    jobs = [("benchmark", data.benchmark_prices), ("look-through", data.lookthrough_result)]
    if settings.get("show_backtest"):
        jobs.append(("backtest", lambda: data.backtest_result(config.REBALANCE, False)))
    for name, job in jobs:
        try:
            job()
            done[name] = "ok"
        except Exception as exc:
            app.logger.exception("refresh: %s failed", name)
            done[name] = f"{type(exc).__name__}: {exc}"
    return jsonify(done)


if __name__ == "__main__":
    # debug=True: the server restarts by itself whenever you save a .py file
    app.run(host=os.environ.get("MY_MONEY_HOST", config.HOST), port=config.PORT, debug=True)
