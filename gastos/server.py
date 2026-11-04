"""Gastos — expenses and income, as a phone-first web app (replaces the AppSheet app).

Run it:
    ../.venv/bin/python server.py           then open http://127.0.0.1:8060
    GASTOS_HOST=0.0.0.0 ../.venv/bin/python server.py   to open it from your phone on the same Wi-Fi

How it fits together
    db.py      the SQLite table and the Google Sheet import
    web/       the whole app: plain HTML/JS/CSS, no build step. Only web/store.js talks to this server,
               so moving to GitHub Pages + a hosted database means rewriting that one file.

This file only serves web/ and maps the /api routes to db.py.
"""
import os
import secrets
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

import db

WEB = Path(__file__).parent / "web"
RECEIPT_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:name>")
def static_file(name):
    return send_from_directory(WEB, name)


@app.get("/api/entries")
def list_entries():
    return jsonify(db.all_entries())


@app.post("/api/entries")
@app.put("/api/entries/<entry_id>")
def save_entry(entry_id=None):
    try:
        return jsonify(db.save(db.clean(request.get_json(force=True), entry_id)))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/entries/<entry_id>")
def delete_entry(entry_id):
    return jsonify({"deleted": db.delete(entry_id)})


@app.post("/api/receipts")
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


@app.get("/receipts/<name>")
def receipt(name):
    return send_from_directory(db.RECEIPTS, name)


@app.post("/api/import-sheet")
def import_sheet():
    try:
        return jsonify(db.import_sheet())
    except Exception as exc:  # no internet, sheet no longer shared…
        app.logger.exception("sheet import failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 400


@app.get("/api/export.csv")
def export_csv():
    return Response(db.to_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gastos.csv"})


if __name__ == "__main__":
    app.run(host=os.environ.get("GASTOS_HOST", "127.0.0.1"), port=8060, debug=True)
