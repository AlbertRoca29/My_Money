"""Download the Gastos Google Sheet and rebuild cashflows.csv from it — the same as
File › Download › CSV of the TOTAL and INGRESOS tabs followed by `python mwr.py --total … --ingresos …`.

Set in config.py: GASTOS_SHEET_URL (the sheet's link) and GASTOS_TABS (which tab is which, by name).

Two ways to give access:

  1. Link sharing (simplest): in the sheet, Share › General access › "Anyone with the link" › Viewer.
     Nothing else to set up. Anyone who has the link can read the sheet.

  2. Private sheet with a service account (sheet stays private):
     a. console.cloud.google.com › create a project › APIs & Services › enable "Google Drive API"
     b. IAM & Admin › Service accounts › create one › Keys › Add key › JSON › save the file as
        google_credentials.json next to this file (it is in .gitignore)
     c. In the sheet: Share › paste the service account's e-mail (…@….iam.gserviceaccount.com) › Viewer

If config.GOOGLE_CREDENTIALS exists it is used; otherwise the sheet must be link-shared.

Usage:  python sheets.py          (or the "Sync from Google Sheets" button on the Returns page)
"""
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import config
import mwr

EXPORT_URL = "https://docs.google.com/spreadsheets/d/{id}/export?format=csv&gid={gid}"
TABS_URL = "https://docs.google.com/spreadsheets/d/{id}/htmlview"   # lists every tab with its gid
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def sheet_id(url):
    """'https://docs.google.com/spreadsheets/d/<id>/edit…' -> '<id>'."""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url or "")
    if not m:
        raise ValueError(f"Not a Google Sheets link: {url!r} — set GASTOS_SHEET_URL in config.py")
    return m.group(1)


def _token():
    """An access token from the service account file, or None to download without logging in."""
    creds_file = Path(config.GOOGLE_CREDENTIALS)
    if not creds_file.exists():
        return None
    from google.auth.transport.requests import Request  # only needed for private sheets
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(str(creds_file), scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def _get(url, token):
    """(body, content type) of a Google URL, turning 'no access' into a clear PermissionError."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body, content_type = r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise PermissionError(_no_access_message(token)) from None
        raise
    if b"accounts.google.com" in body[:5000] and "text/csv" not in content_type:  # Google's login page
        raise PermissionError(_no_access_message(token))
    return body, content_type


def _no_access_message(token):
    if token:
        return ("The service account can't read the sheet: share it with the e-mail in "
                f"{Path(config.GOOGLE_CREDENTIALS).name} (Viewer).")
    return ("The sheet is private. Either share it as 'Anyone with the link › Viewer', or set up a "
            "service account (see sheets.py).")


def tab_gids(sid, token=None):
    """{tab name: gid} for every tab of the sheet."""
    page, _ = _get(TABS_URL.format(id=sid), token)
    found = re.findall(r'\{name: "((?:[^"\\]|\\.)*)", pageUrl: "[^"]*?gid=(\d+)', page.decode("utf-8", "replace"))
    if not found:
        raise ValueError("Could not read the list of tabs — put the tab's gid number in GASTOS_TABS instead "
                         "(it's the number after #gid= in the address bar when the tab is open).")
    return {name.encode().decode("unicode_escape"): gid for name, gid in found}


def download_tab(sid, gid, token=None):
    """One tab as CSV bytes, exactly like File › Download › CSV."""
    body, content_type = _get(EXPORT_URL.format(id=sid, gid=gid), token)
    if "text/csv" not in content_type:
        raise PermissionError(_no_access_message(token))
    return body


def sync():
    """Download the TOTAL and INGRESOS tabs and rebuild cashflows.csv. Returns a short status line."""
    token = _token()
    sid = sheet_id(config.GASTOS_SHEET_URL)
    names = config.GASTOS_TABS
    # a tab can be given by name ("TOTAL") or directly by its gid number (the number after "gid=" in its link)
    gids = tab_gids(sid, token) if any(isinstance(v, str) for v in names.values()) else {}
    missing = [v for v in names.values() if isinstance(v, str) and v not in gids]
    if missing:
        raise ValueError(f"No tab called {', '.join(missing)} in the sheet (it has: {', '.join(gids)}).")
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        for key, tab in names.items():
            files[key] = Path(tmp) / f"{key}.csv"
            files[key].write_bytes(download_tab(sid, gids.get(tab, tab), token))
        try:
            mwr.build_cashflows(files["total"], files["ingresos"], out=config.CASHFLOWS_CSV)
        except KeyError as exc:
            raise ValueError(f"Column {exc} not found — does GASTOS_TABS point at the right tabs?") from None
    flows = mwr.load_cashflows(config.CASHFLOWS_CSV)
    return f"cashflows.csv: {len(flows)} days, last {flows[-1][0]:%d %b %Y}"


if __name__ == "__main__":
    print(sync())
