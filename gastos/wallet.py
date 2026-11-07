"""Card payments from Google Wallet, sent by the phone app in ../android/ (no service in between).

The phone reads Wallet's payment notification and POSTs it here as it is:
    title  "BALUARD VALENCIA"                              (the merchant)
    text   "€6.03 with Trade Republic Visa Card ••7469"   (or "6,03 € con …" in Spanish)
    when   the notification's time, in milliseconds

A payment at a place you already have ("BALUARD VALENCIA" when you have "baluard") is added straight to the
sheet with that name and its last category, unless the wallet_auto setting is off. Its ID starts with "w",
which is how Gastos knows to mark it 📲 (no extra column in the sheet).

Anything else lands in a short "to review" list (wallet/pending.json in storage): a new merchant alone
rarely says the category. Gastos shows the list at the top; tapping one opens the usual Add sheet,
filled in, and saving it removes it from the list.

The phone proves it is yours with WALLET_TOKEN (a long random secret, Secret Manager on Cloud Run; see
deploy.sh). Without WALLET_TOKEN set, /api/wallet/notify refuses everything.
"""
import hmac
import hashlib
import json
import os
import re
import logging
import threading
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import settings
import storage

from . import db

KEY = "wallet/pending.json"
TZ = ZoneInfo("Europe/Madrid")
_lock = threading.Lock()
log = logging.getLogger(__name__)

# "€6.03", "€1,234.50", "6,03 €", "1.234,50 €", "EUR 6.03", "-€6.03" (a refund: skipped)
AMOUNT = re.compile(r"(?P<neg>[-−])?\s*(?:€|EUR)\s*(?P<a>\d[\d.,]*)|(?P<neg2>[-−])?(?P<b>\d[\d.,]*)\s*(?:€|EUR)")
CARD = re.compile(r"(?:with|con|amb)\s+(?P<card>.+?)\s*$", re.I)


def token_ok(header):
    expected = os.environ.get("WALLET_TOKEN", "")
    given = header.removeprefix("Bearer ").strip()
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def _number(s):
    """'1.234,50' or '1,234.50' or '6.03' or '6,03' -> float. The last separator with 1–2 digits after it is the decimal one."""
    m = re.fullmatch(r"(.*?)[.,](\d{1,2})", s)
    whole, cents = (m.group(1), m.group(2)) if m else (s, "0")
    return float(re.sub(r"[.,]", "", whole) + "." + cents)


def parse(title, text):
    """The notification -> {"name", "amount", "card"}, or None when it is not a payment."""
    m = AMOUNT.search(text or "")
    if not m or not (title or "").strip():
        return None
    if m.group("neg") or m.group("neg2"):
        return None
    amount = _number(m.group("a") or m.group("b"))
    if amount <= 0:
        return None
    card = CARD.search(text[m.end():])
    return {"name": tidy_name(title), "amount": round(amount, 2), "card": card.group("card") if card else None}


def tidy_name(title):
    """'BALUARD VALENCIA' -> 'Baluard Valencia' (names you already use win later, in the browser)."""
    name = re.sub(r"\s+", " ", title).strip().rstrip("…").strip()
    return name.title() if name.isupper() else name


def norm(s):
    """Same as norm() in web/app.js: no accents, lower case, letters and digits only."""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", "", s.lower())


def known(name, entries):
    """The latest expense whose name is this one, or starts it ("baluard" for "Baluard Valencia"), or None."""
    n = norm(name)
    mine = [e for e in entries if e["kind"] == "expense" and e["category"]]
    return next((e for e in mine if norm(e["name"]) == n), None) or next(
        (e for e in mine if len(norm(e["name"])) >= 4 and (n.startswith(norm(e["name"])) or norm(e["name"]).startswith(n))), None)


def auto_add(item):
    """Put the payment straight in the sheet when its place is known. Returns the entry, or None."""
    if not settings.get("wallet_auto") or settings.get("demo"):
        return None
    try:
        match = known(item["name"], db.all_entries())
        if not match:
            return None
        # The ID comes from the payment, so the phone sending it twice replaces the row instead of adding one
        return db.save(db.clean({"kind": "expense", "name": match["name"], "category": match["category"],
                                 "date": item["date"], "amount": item["amount"]}, "w" + item["id"][:7]))
    except Exception:  # the sheet unreachable, say: keep it for review rather than lose it
        log.exception("Wallet payment %s not added by itself", item["id"])
        return None


def _load():
    body = storage.read(KEY)
    return json.loads(body) if body else []


def _save(items):
    storage.write(KEY, json.dumps(items, ensure_ascii=False).encode(), "application/json")


def add(title, text, when_ms=None):
    """Keep a payment for review. Returns (item, created); item is None when the text is not a payment."""
    p = parse(title, text)
    if not p:
        return None, False
    at = datetime.fromtimestamp(when_ms / 1000, TZ) if when_ms else datetime.now(TZ)
    # Same merchant, amount and minute = the same payment (the phone retried, or Wallet updated it)
    pid = hashlib.sha1(f"{p['name']}|{p['amount']}|{at:%Y-%m-%dT%H:%M}".encode()).hexdigest()[:10]
    item = {"id": pid, **p, "date": at.date().isoformat(), "time": at.strftime("%H:%M"), "raw": f"{title} · {text}"}
    with _lock:
        items = _load()
        if any(i["id"] == pid for i in items):
            return item, False
        entry = auto_add(item)
        if entry:
            return {**item, "added": entry}, True
        items.append(item)
        _save(items)
    return item, True


def pending():
    return sorted(_load(), key=lambda i: (i["date"], i.get("time", "")), reverse=True)


def dismiss(pid):
    with _lock:
        items = _load()
        kept = [i for i in items if i["id"] != pid]
        if len(kept) != len(items):
            _save(kept)
    return len(items) - len(kept)
