"""Gastos — expenses and income, as a web app for the phone and the computer (replaces logging them straight into the Google Sheet).

It is the default half of My Money: ../app.py registers this blueprint, so Gastos lives at "/" and the
portfolio tracker at "/portfolio", on the same server.

How it fits together
    db.py      the Movements tab of your Google Sheet
    web/       the whole app: plain HTML/JS/CSS, no build step. Only web/store.js talks to this server.

This file only serves web/ and maps the /api routes to db.py.
"""
import mimetypes
import re
import secrets
from pathlib import Path

from flask import Blueprint, Response, abort, jsonify, request, send_from_directory, session

import gsheet
import storage

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


@bp.errorhandler(PermissionError)
@bp.errorhandler(RuntimeError)
def sheet_problem(exc):
    """No sheet set yet, or not shared with the app: say so on screen instead of a bare error page."""
    return jsonify({"error": str(exc)}), 503


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
    try:
        return jsonify({"deleted": db.delete(entry_id)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/api/rename")
def rename_entries():
    """Merge spellings of a name: {"kind": "expense", "from": ["zara shrt", "ZARA"], "to": "Zara"}."""
    body = request.get_json(force=True)
    try:
        return jsonify({"renamed": db.rename(body.get("kind"), body.get("from") or [], body.get("to") or "")})
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/api/receipts")
def upload_receipt():
    """Save a photo or PDF of a receipt; returns the name to put in the entry's `receipt`."""
    file = request.files.get("file")
    ext = Path(file.filename).suffix.lower() if file else ""
    if ext not in RECEIPT_TYPES:
        return jsonify({"error": "Send an image or a PDF"}), 400
    name = f"{secrets.token_hex(6)}{ext}"
    storage.write(f"receipts/{name}", file.read(), file.mimetype)
    return jsonify({"receipt": name})


@bp.get("/receipts/<name>")
def receipt(name):
    body = storage.read(f"receipts/{name}") if re.fullmatch(r"[0-9a-f]+\.[a-z]+", name) else None
    if body is None:
        abort(404)
    return Response(body, mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",
                    headers={"Cache-Control": "private, max-age=86400"})


@bp.get("/api/info")
def info():
    """For the Settings screen: where the data is and who is signed in."""
    return jsonify({"sheet": gsheet.url(), "email": session.get("email")})


@bp.get("/api/export.csv")
def export_csv():
    return Response(db.to_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gastos.csv"})
