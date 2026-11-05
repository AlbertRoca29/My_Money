"""Settings you change from the app itself (the ⚙ sheet, the same in Portfolio and Gastos).

They are kept as settings.json in storage (the bucket online, files/ on your computer), so they are the
same on your phone and your computer. config.py still holds the defaults and everything private.

To add a setting: add a field to FIELDS, then read it with settings.get("name") where you need it.
"""
import json
import threading
import time

import config
import storage

KEY = "settings.json"

# Each field: name, label, type ("number" | "toggle" | "select" | "date"), default, plus group (the heading it
# sits under in the settings sheet) and, for some, help / min / max / step / options.
FIELDS = [
    dict(name="nav", group="Look", label="Tabs on the phone", type="select", default="top",
         help="Mixed: Gastos at the bottom, Portfolio at the top",
         options=[("mixed", "Mixed"), ("bottom", "Bottom on both"), ("top", "Top on both")]),
    dict(name="top_min", group="Gastos", label="Biggest expenses: 4th and 5th from (€)", type="number", default=30,
         min=0, max=10000, step=1, help="Home always lists the top 3; the 4th and 5th only if they're above this"),
    dict(name="home_trend", group="Gastos", label="12-month trend on Home", type="toggle", default=True),
    dict(name="hide_others", group="Gastos", label="Hide what someone else paid", type="toggle", default=False,
         help="Leaves them out of Movements and Home"),
    dict(name="trends_from", group="Overview", label="Charts start on", type="date", default=config.OVERVIEW_START),
    dict(name="cash_k", group="Returns", label=f"Cash next to {config.BENCHMARK_NAME} (k€)", type="number",
         default=config.BENCHMARK_CASH_K, min=0, max=500, step=1,
         help=f"The benchmark is “{config.BENCHMARK_NAME} + this much cash”"),
    dict(name="countries", group="Exposure", label="Countries shown", type="number", default=20, min=5, max=60),
    dict(name="companies", group="Exposure", label="Companies shown", type="number", default=20, min=5, max=50),
    dict(name="show_backtest", group="Backtest", label="Show the Backtest tab", type="toggle", default=False,
         help="Off hides the tab and skips its nightly download"),
    dict(name="rebalance", group="Backtest", label="Rebalance", type="select", default=config.REBALANCE or "none",
         options=[("ME", "Monthly"), ("QE", "Quarterly"), ("YE", "Yearly"), ("none", "Never (buy & hold)")]),
    dict(name="proxies", group="Backtest", label="Longest history (with stand-ins)", type="toggle", default=False),
]
DEFAULTS = {f["name"]: f["default"] for f in FIELDS}
_CAST = {"number": float, "toggle": bool, "select": str, "date": str}

_lock = threading.Lock()
_cache = {"at": 0.0, "values": None}


def current():
    """Every setting: the saved ones over the defaults. Re-read from storage at most once a minute."""
    with _lock:
        if _cache["values"] is None or time.monotonic() - _cache["at"] > 60:
            raw = storage.read(KEY)
            saved = json.loads(raw) if raw else {}
            _cache.update(at=time.monotonic(), values={**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}})
        return dict(_cache["values"])


def get(name):
    return current()[name]


def _clean(field, v):
    v = _CAST[field["type"]](v)
    if field["type"] == "number":
        v = max(field.get("min", v), min(field.get("max", v), v))
        v = int(v) if float(v).is_integer() else v
    if field["type"] == "select" and v not in [o[0] for o in field["options"]]:
        raise ValueError(f"{field['label']}: {v!r} is not an option")
    return v


def save(changes):
    """Merge {name: value} into the saved settings. Raises ValueError on a bad value."""
    fields = {f["name"]: f for f in FIELDS}
    values = current()
    for k, v in changes.items():
        if k in fields:
            values[k] = _clean(fields[k], v)
    storage.write(KEY, json.dumps(values, indent=1).encode(), "application/json")
    with _lock:
        _cache.update(at=time.monotonic(), values=values)
    return values


def schema():
    """What the browser needs to draw the settings sheet."""
    return {"values": current(), "fields": [{**f, "options": [{"value": o[0], "label": o[1]} for o in f.get("options", [])]}
                                        for f in FIELDS]}
