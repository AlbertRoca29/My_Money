"""Storage for Gastos: the Movements tab of your Google Sheet, one row per expense or income.

    ID | Date | Kind | Name | Category | Amount | Gross | Paid by others | Note | Receipt

    ID             8 hex characters, made by the app
    Date           a date (the app writes 2026-11-04)
    Kind           Expense or Income
    Name           what it was ("Supermarket", "Salary"…)
    Category       "🛒 Groceries" for expenses, "💼 Job" for income…
    Amount         euros, positive. For income: the amount that reached the account; a negative income is a
                   loss (say an investment sold below cost) and counts against the month's income
    Gross          income only, optional: the amount before taxes
    Paid by others TRUE when someone else (job, family) paid for it: listed, but left out of every total
    Note           free text
    Receipt        file name in the bucket's receipts/ (see storage.py), or an old AppSheet path

You can edit, sort or fix rows in the sheet itself; keep the header row as it is. A row the app can't read
(say, text in Amount) is skipped and named in the log, never deleted.

The browser never talks to this file directly, only through routes.py's /api routes.
"""
import csv
import io
import logging
import secrets
from datetime import date

import config
import demo
import gsheet
import settings

TAB = config.MOVEMENTS_TAB
HEADER = ["ID", "Date", "Kind", "Name", "Category", "Amount", "Gross", "Paid by others", "Note", "Receipt"]
FIELDS = ["id", "kind", "name", "category", "date", "amount", "gross", "paid_by_other", "receipt", "note"]
log = logging.getLogger(__name__)


def setup():
    """Create the Movements tab if the sheet doesn't have it yet."""
    return gsheet.ensure_tab(TAB, HEADER, date_cols=[1])


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
    if kind == "expense" and amount <= 0:
        raise ValueError("Amount must be more than 0")
    if amount == 0:
        raise ValueError("Amount can't be 0")  # income may be negative: a loss
    gross = body.get("gross")
    return {
        "id": entry_id or body.get("id") or new_id(),
        "kind": kind,
        "name": name,
        "category": category,
        "date": day.isoformat(),
        "amount": round(amount, 2),
        "gross": round(float(gross), 2) if gross not in (None, "") and kind == "income" else None,
        "paid_by_other": bool(body.get("paid_by_other")) and kind == "expense",
        "receipt": body.get("receipt") or None,
        "note": (body.get("note") or "").strip() or None,
    }


# ---------------------------------------------------------------------------
# Rows <-> entries
# ---------------------------------------------------------------------------
def _number(v):
    return None if v in (None, "") else float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)


def _entry(row):
    row = list(row) + [""] * (len(HEADER) - len(row))
    eid, day, kind, name, category, amount, gross, other, note, receipt = row[:len(HEADER)]
    kind = str(kind).strip().lower()
    if kind not in ("expense", "income"):
        raise ValueError(f"Kind is {kind!r}, not Expense or Income")
    if _number(amount) is None:
        raise ValueError("no Amount")
    return {
        "id": str(eid).strip(),
        "kind": kind,
        "name": str(name).strip(),
        "category": str(category).strip(),
        "date": gsheet.to_date(day).isoformat(),
        "amount": _number(amount) if kind == "income" else abs(_number(amount)),
        "gross": _number(gross) if kind == "income" else None,
        "paid_by_other": other is True or str(other).strip().upper() == "TRUE",
        "receipt": str(receipt).strip() or None,
        "note": str(note).strip() or None,
    }


def _row(e):
    return [e["id"], e["date"], e["kind"].capitalize(), e["name"], e["category"], e["amount"],
            "" if e["gross"] is None else e["gross"], True if e["paid_by_other"] else "", e["note"] or "", e["receipt"] or ""]


def all_entries():
    """Every readable row, newest first (rows added later come first within a day)."""
    if settings.get("demo"):
        return demo.entries()
    rows = gsheet.rows(TAB)
    if not rows:
        return []
    gsheet.check_header(TAB, HEADER, rows[0])
    entries = []
    for n, row in enumerate(rows[1:], start=2):
        if gsheet.blank(row):
            continue
        try:
            e = _entry(row)
        except (ValueError, TypeError) as exc:
            log.warning("%s row %d skipped: %s", TAB, n, exc)
            continue
        entries.append((e["date"], n, e))
    return [e for *_, e in sorted(entries, key=lambda t: (t[0], t[1]), reverse=True)]


def _row_number(entry_id):
    """1-based row of this ID in the sheet as it is right now (rows may have been sorted by hand)."""
    ids = [r[0] if r else "" for r in gsheet.read(TAB, "A:A")]
    return ids.index(entry_id) + 1 if entry_id in ids else None


def refuse_in_demo():
    if settings.get("demo"):
        raise ValueError("Demo data is on: turn it off in Settings to add or change anything")


def save(entry):
    """Add the entry, or replace the row with the same ID."""
    refuse_in_demo()
    with gsheet.lock:
        n = _row_number(entry["id"])
        if n:
            gsheet.update(TAB, f"A{n}", [_row(entry)])
        else:
            gsheet.append(TAB, [_row(entry)])
    return entry


def delete(entry_id):
    refuse_in_demo()
    with gsheet.lock:
        n = _row_number(entry_id)
        if n:
            gsheet.delete_row(TAB, n - 1)
    return int(bool(n))


def rename(kind, old_names, new_name):
    """Give every `kind` entry named in `old_names` the name `new_name` (merging spellings into one).
    Only the Name cells change. Returns how many entries were renamed."""
    refuse_in_demo()
    old = set(old_names)
    new_name = new_name.strip()
    if kind not in ("expense", "income") or not new_name:
        raise ValueError("kind and a new name are required")
    with gsheet.lock:
        rows = gsheet.read(TAB)
        gsheet.check_header(TAB, HEADER, rows[0] if rows else [])
        cells = {}
        for n, row in enumerate(rows[1:], start=2):
            row = list(row) + [""] * (len(HEADER) - len(row))
            if str(row[2]).strip().lower() == kind and str(row[3]).strip() in old and str(row[3]).strip() != new_name:
                cells[f"D{n}"] = new_name
        gsheet.update_cells(TAB, cells)
    return len(cells)


def daily_net():
    """[(date, net savings)] per day, oldest first: income minus expenses, what the portfolio's Returns page
    calls "money put in". Income typed 📈 Investments is left out (it is a return, not new money), and so are
    expenses paid by others."""
    net = {}
    for e in all_entries():
        if e["kind"] == "income" and "Investments" in e["category"]:
            continue
        if e["kind"] == "expense" and e["paid_by_other"]:
            continue
        net[e["date"]] = net.get(e["date"], 0) + (e["amount"] if e["kind"] == "income" else -e["amount"])
    return [(date.fromisoformat(d), round(v, 2)) for d, v in sorted(net.items()) if round(v, 2)]


def to_csv():
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(all_entries())
    return out.getvalue()
