"""Gastos — expenses and income, as a phone-first web app (replaces logging them straight into the Google Sheet).

It is the default half of My Money: ../app.py registers this blueprint, so Gastos lives at "/" and the
portfolio tracker at "/portfolio", on the same server.

How it fits together
    db.py      the SQLite table and the Google Sheet import
    web/       the whole app: plain HTML/JS/CSS, no build step. Only web/store.js talks to this server,
               so moving to GitHub Pages + a hosted database means rewriting that one file.

This file only serves web/ and maps the /api routes to db.py.
"""
import secrets
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory

from . import db

WEB = Path(__file__).parent / "web"
RECEIPT_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}

bp = Blueprint("gastos", __name__)


@bp.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@bp.get("/<path:name>")
def static_file(name):
    """web/ files (style.css, app.js…). More specific routes, like /static/… and /portfolio, win over this one."""
    return send_from_directory(WEB, name)


@bp.get("/api/entries")
def list_entries():
    return jsonify(db.all_entries())


@bp.post("/api/entries")
@bp.put("/api/entries/<entry_id>")
def save_entry(entry_id=None):
    try:
        return jsonify(db.save(db.clean(request.get_json(force=True), entry_id)))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.delete("/api/entries/<entry_id>")
def delete_entry(entry_id):
    return jsonify({"deleted": db.delete(entry_id)})


@bp.post("/api/receipts")
def upload_receipt():
    """Save a photo or PDF of a receipt; returns the name to put in the entry's `receipt`."""
    file = request.files.get("file")
    ext = Path(file.filename).suffix.lower() if file else ""
    if ext not in RECEIPT_TYPES:
        return jsonify({"error": "Send an image or a PDF"}), 400
    db.RECEIPTS.mkdir(exist_ok=True)
    name = f"{secrets.token_hex(6)}{ext}"
    file.save(db.RECEIPTS / name)
    return jsonify({"receipt": name})


@bp.get("/receipts/<name>")
def receipt(name):
    return send_from_directory(db.RECEIPTS, name)


@bp.post("/api/import-sheet")
def import_sheet():
    try:
        return jsonify(db.import_sheet())
    except Exception as exc:  # no internet, sheet no longer shared…
        current_app.logger.exception("sheet import failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 400


@bp.get("/api/export.csv")
def export_csv():
    return Response(db.to_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gastos.csv"})
