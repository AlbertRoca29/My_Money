"""Storage for Gastos: one SQLite table of entries (expenses and income), plus the Google Sheet import.

An entry:
    id             8 hex characters, the same kind of ID as the sheet rows, so imported rows keep theirs
    kind           "expense" or "income"
    name           what it was ("Supermarket", "Salary"…)
    category       "🛒 Groceries" for expenses, "💼 Job" for income…
    date           YYYY-MM-DD
    amount         euros, always positive. For income: the amount that reached the account
    gross          income only, optional: the amount before taxes
    paid_by_other  1 when someone else (job, family) paid for it: kept in the list, left out of every total
    receipt        file name in receipts/, or an old path from the sheet ("folder/…", a file left in Google Drive)
    note           free text

The browser never talks to this file directly — only through routes.py's /api routes — so the
database can later be swapped for a hosted one without touching the front-end's screens.
"""
import csv
import io
import os
import re
import secrets
import sqlite3
import urllib.request
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "gastos.db"
RECEIPTS = HERE / "receipts"

# The Google Sheet to import from: set GASTOS_SHEET_URL in the environment, in
# gastos/config_local.py or in the main config_local.py (both git-ignored).
try:
    from .config_local import GASTOS_SHEET_URL
except ImportError:
    try:
        from config_local import GASTOS_SHEET_URL
    except ImportError:
        GASTOS_SHEET_URL = os.environ.get("GASTOS_SHEET_URL", "")
TAB_URL = "https://docs.google.com/spreadsheets/d/{id}/gviz/tq?tqx=out:csv&sheet={tab}"

FIELDS = ["id", "kind", "name", "category", "date", "amount", "gross", "paid_by_other", "receipt", "note"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('expense', 'income')),
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    date          TEXT NOT NULL,
    amount        REAL NOT NULL,
    gross         REAL,
    paid_by_other INTEGER NOT NULL DEFAULT 0,
    receipt       TEXT,
    note          TEXT,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS entries_date ON entries (date);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def new_id():
    return secrets.token_hex(4)


def clean(body, entry_id=None):
    """Validate an entry coming from the browser. Raises ValueError with a readable message."""
    kind = body.get("kind")
    if kind not in ("expense", "income"):
        raise ValueError("kind must be 'expense' or 'income'")
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Name is required")
    category = (body.get("category") or "").strip()
    if not category:
        raise ValueError("Category is required")
    day = date.fromisoformat(body.get("date") or "")  # raises ValueError on a bad date
    amount = float(body.get("amount"))
    if amount <= 0:
        raise ValueError("Amount must be more than 0")
    gross = body.get("gross")
    return {
        "id": entry_id or body.get("id") or new_id(),
        "kind": kind,
        "name": name,
        "category": category,
        "date": day.isoformat(),
        "amount": round(amount, 2),
        "gross": round(float(gross), 2) if gross not in (None, "") and kind == "income" else None,
        "paid_by_other": int(bool(body.get("paid_by_other"))) if kind == "expense" else 0,
        "receipt": body.get("receipt") or None,
        "note": (body.get("note") or "").strip() or None,
    }


def all_entries():
    with connect() as con:
        rows = con.execute(f"SELECT {', '.join(FIELDS)} FROM entries ORDER BY date DESC, updated_at DESC")
        return [dict(r) | {"paid_by_other": bool(r["paid_by_other"])} for r in rows]


def save(entry):
    """Insert or replace one cleaned entry."""
    entry = entry | {"updated_at": datetime.now().isoformat(timespec="seconds")}
    cols = FIELDS + ["updated_at"]
    with connect() as con:
        con.execute(f"INSERT OR REPLACE INTO entries ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [entry[c] for c in cols])
    return entry


def delete(entry_id):
    with connect() as con:
        return con.execute("DELETE FROM entries WHERE id = ?", (entry_id,)).rowcount


# ---------------------------------------------------------------------------
# Google Sheet import (its GASTOS and INGRESOS tabs)
# ---------------------------------------------------------------------------
def _num(text):
    """'1.763,54' or '42,64' -> float; '' -> None."""
    text = (text or "").strip().replace(".", "").replace(",", ".")
    return float(text) if text else None


def _day(text):
    """'14/9/2023' or '12/09/23' (day first) -> '2023-09-14'."""
    d, m, y = (int(p) for p in text.strip().split("/"))
    return date(y + 2000 if y < 100 else y, m, d).isoformat()


def _sheet_id():
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", GASTOS_SHEET_URL)
    if not m:
        raise ValueError("No sheet to import from: set GASTOS_SHEET_URL (see the top of db.py)")
    return m.group(1)


def _tab(tab):
    req = urllib.request.Request(TAB_URL.format(id=_sheet_id(), tab=tab), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return list(csv.DictReader(io.StringIO(resp.read().decode("utf-8"))))


def rows_from_sheet():
    """Every GASTOS and INGRESOS row as entries. The sheet must be shared as "anyone with the link"."""
    entries = []
    for r in _tab("GASTOS"):
        if not r.get("ID") or not r.get("Amount"):
            continue
        entries.append({"id": r["ID"], "kind": "expense", "name": r["Name"], "category": r["Category"],
                        "date": _day(r["Date"]), "amount": _num(r["Amount"]), "gross": None,
                        "paid_by_other": int(r["Supply"].upper() == "TRUE"),
                        "receipt": r.get("Ticket") or None, "note": None})
    for r in _tab("INGRESOS"):
        if not r.get("ID") or not r.get("Import (brut)"):
            continue
        # In the sheet, "Import (brut)" is what reached the account (it is what TOTAL adds up) and
        # "Import (net)" holds the salary before taxes, so they map to amount and gross respectively.
        received, before_tax = _num(r["Import (brut)"]), _num(r["Import (net)"])
        entries.append({"id": r["ID"], "kind": "income", "name": r["Nom"], "category": r["Tipus"],
                        "date": _day(r["Data"]), "amount": received,
                        "gross": before_tax if before_tax and before_tax != received else None,
                        "paid_by_other": 0, "receipt": None, "note": None})
    return entries


def import_sheet():
    """Add or update every sheet row (matched by ID). Entries created in the app are never touched."""
    entries = rows_from_sheet()
    with connect() as con:
        before = con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    for e in entries:
        save(e)
    with connect() as con:
        after = con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    return {"rows": len(entries), "new": after - before}


def to_csv():
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(all_entries())
    return out.getvalue()


if __name__ == "__main__":
    print(import_sheet())
