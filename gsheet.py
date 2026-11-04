"""Your Google Sheet (config.SHEET_ID), read and written through the Sheets API.

It holds two tabs, each a plain table with a header row: Movements (Gastos) and Snapshots (the portfolio).
gastos/db.py and web/data.py decide what goes in them; this file only moves rows in and out.

Credentials: on Cloud Run, the app's service account. On your computer, your gcloud login borrowing that same
service account (see DEPLOY.md, "On your computer"), so the sheet is only ever shared with one address.
Reads are kept for config.SHEET_CACHE_SECONDS, so edits made directly in the sheet show up shortly after.
"""
import threading
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import AuthorizedSession

import config

API = "https://sheets.googleapis.com/v4/spreadsheets/{id}"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERIAL_ZERO = date(1899, 12, 30)  # Sheets counts dates as days since this one

lock = threading.Lock()  # one read-change-write at a time (Cloud Run runs a single instance, see deploy.sh)
_session = None
_cache = {}  # tab -> (time read, rows)


def url():
    return f"https://docs.google.com/spreadsheets/d/{config.SHEET_ID}/edit"


def _call(method, path="", **kwargs):
    global _session
    if not config.SHEET_ID:
        raise RuntimeError("No sheet yet: set SHEET_ID in config_local.py (or MY_MONEY_SHEET), see DEPLOY.md")
    if _session is None:
        creds, _ = google.auth.default(scopes=SCOPES)
        if config.PROJECT:  # bill API use to this project, never to whatever gcloud has as default
            creds = creds.with_quota_project(config.PROJECT)
        _session = AuthorizedSession(creds)
    r = _session.request(method, API.format(id=config.SHEET_ID) + path, timeout=30, **kwargs)
    if r.status_code in (403, 404):
        raise PermissionError(f"Can't open the sheet ({r.status_code}). Is it shared (Editor) with the app's "
                              f"service account? {r.json().get('error', {}).get('message', '')}")
    r.raise_for_status()
    return r.json()


def _range(tab, cells=""):
    return quote(f"'{tab}'" + (f"!{cells}" if cells else ""), safe="")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read(tab, cells=""):
    """Rows as lists of plain values (numbers stay numbers, dates are serial numbers, checkboxes are bools)."""
    return _call("GET", f"/values/{_range(tab, cells)}", params={
        "valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "SERIAL_NUMBER"}).get("values", [])


def rows(tab):
    """read(tab), kept for config.SHEET_CACHE_SECONDS."""
    hit = _cache.get(tab)
    if hit and time.monotonic() - hit[0] < config.SHEET_CACHE_SECONDS:
        return hit[1]
    data = read(tab)
    _cache[tab] = (time.monotonic(), data)
    return data


def forget(tab):
    _cache.pop(tab, None)


def blank(row):
    """True for a row with nothing in it (unticked checkboxes count as nothing)."""
    return all(v in ("", None, False) or not str(v).strip() for v in row)


def to_date(v):
    """A date cell: a serial number, or text like '2026-11-04' or '4/11/2026' (day first)."""
    if isinstance(v, (int, float)):
        return SERIAL_ZERO + timedelta(days=int(v))
    v = str(v).strip()
    if "/" in v:
        d, m, y = (int(x) for x in v.split("/"))
        return date(y + 2000 if y < 100 else y, m, d)
    return datetime.fromisoformat(v).date()


# ---------------------------------------------------------------------------
# Writing (values are typed as if by hand, so '2026-11-04' becomes a date and 12.5 a number)
# ---------------------------------------------------------------------------
def append(tab, new_rows):
    _call("POST", f"/values/{_range(tab, 'A1')}:append",
          params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}, json={"values": new_rows})
    forget(tab)


def update(tab, cells, new_rows):
    _call("PUT", f"/values/{_range(tab, cells)}", params={"valueInputOption": "USER_ENTERED"},
          json={"values": new_rows})
    forget(tab)


def delete_row(tab, index):
    """Remove one row (0-based, the header being row 0)."""
    _batch([{"deleteDimension": {"range": {"sheetId": tabs()[tab], "dimension": "ROWS",
                                           "startIndex": index, "endIndex": index + 1}}}])
    forget(tab)


def tabs():
    """{tab title: its numeric id}."""
    meta = _call("GET", "", params={"fields": "sheets.properties(title,sheetId)"})
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}


def _batch(requests):
    return _call("POST", ":batchUpdate", json={"requests": requests})


def ensure_tab(tab, header, date_cols=()):
    """Create the tab with its header row (bold, frozen) if it doesn't exist yet. Columns are 0-based."""
    if tab in tabs():
        return False
    sheet_id = _batch([{"addSheet": {"properties": {"title": tab, "gridProperties": {"frozenRowCount": 1}}}}]
                      )["replies"][0]["addSheet"]["properties"]["sheetId"]
    update(tab, "A1", [header])

    def cols(c):
        return {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": c, "endColumnIndex": c + 1}
    _batch([{"repeatCell": {"range": {"sheetId": sheet_id, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold"}}]
           + [{"repeatCell": {"range": cols(c), "cell": {"userEnteredFormat": {
               "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}}, "fields": "userEnteredFormat.numberFormat"}}
              for c in date_cols])
    return True


def check_header(tab, header, found):
    if [str(h).strip() for h in found[:len(header)]] != header:
        raise ValueError(f"The {tab} tab's first row should be: {' | '.join(header)} (in that order). "
                         f"It is: {' | '.join(map(str, found)) or 'empty'}")
