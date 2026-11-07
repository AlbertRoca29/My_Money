"""The building blocks a page is made of.

A page (see web/pages/) returns a dict like

    {"hero": hero(...), "controls": [...], "sections": [...]}

and every section is a titled card holding a list of blocks. The browser (static/app.js) only
knows how to draw these block types; everything you see is decided here in Python.

    kpis      a row of big numbers              kpis(kpi("MWR", "11.6%"), ...)
    chart     a Plotly figure                   chart(fig)
    table     a pandas DataFrame                table(df, formats={"€": eur})
    items     a list of rows                   items([item("Apple", "Stocks", "€1,200")])
    notes     bullet points (**bold** allowed)  notes(["first", "second"])
    text      one paragraph                     text("...")
    fold      a collapsed "show more" row          fold("Notes", blocks=[notes([...])]) or fold("More", cards=[...])
    tabs      a collapsible panel of tabs          tabs("More details", [("🌍", "Countries", "blurb", [card, ...])])
    tiles     a grid of icon tiles                 tiles([tile("💻", "Technology", "28%", "All-World 26%")])
    duel      two sides compared, and a verdict duel(side("You", "€23k"), side("VWCE", "€22k"), "You lead")

To add a section to a page, write a function decorated with @section and add it to the page's
`sections` list. If it raises, only that card shows the error; the rest of the page still loads.
"""
import functools
import html
import json
import re
import traceback

import pandas as pd

from web.theme import tone


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def section(title, subtitle=None, width="full"):
    """Decorator: turns `fn(params) -> block | [blocks]` into a card. width: "full" | "half"."""
    def wrap(fn):
        @functools.wraps(fn)
        def run(params):
            card = {"title": title, "subtitle": subtitle, "width": width, "id": fn.__name__}
            try:
                out = fn(params)
                if out is None:
                    return None  # nothing to show (e.g. no data for this period)
                if isinstance(out, dict) and "blocks" in out:  # the function overrode title/subtitle
                    card.update(out)
                else:
                    card["blocks"] = out if isinstance(out, list) else [out]
            except Exception as exc:  # one broken card must not take the page down
                traceback.print_exc()
                card["error"] = f"{type(exc).__name__}: {exc}"
            return card
        return run
    return wrap


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------
def hero(label, value, chips=(), caption=None, unit=None):
    """The big balance at the top of a page. chips: [(text, tone)], tone in {"pos", "neg", None}.
    unit: small text after the value, e.g. "/yr"."""
    return {"label": label, "value": value, "unit": unit, "caption": caption,
            "chips": [{"text": t, "tone": tn} for t, tn in chips]}


def empty_page(label, message, sections=()):
    """A page with nothing to show yet: the reason in the hero, plus any sections that still apply."""
    return {"hero": hero(label, "—", caption=message), "controls": [], "sections": list(sections)}


def kpi(label, value, sub=None, tone=None):
    return {"label": label, "value": value, "sub": sub, "tone": tone}


def kpis(*items):
    return {"type": "kpis", "items": list(items)}


def chart(fig):
    """A Plotly figure. Python decides everything (data, colours, layout); the browser just draws it."""
    return {"type": "chart", "figure": json.loads(fig.to_json())}


def table(df, formats=None, index=True, toned=(), max_rows=None, bar=None):
    """A DataFrame as a table.

    formats: {column: function(value) -> str}; other numbers are shown with 2 decimals
    toned:   columns whose cells turn green when > 0 and red when < 0
    bar:     a column drawn as an in-cell bar (0..100 %) next to its value
    """
    formats = formats or {}
    if max_rows:
        df = df.head(max_rows)
    cols = ([str(df.index.name or "")] if index else []) + [str(c) for c in df.columns]
    rows = []
    for idx, r in df.iterrows():
        cells = [{"v": str(idx), "head": True}] if index else []
        for c in df.columns:
            v = r[c]
            if c in formats:
                s = formats[c](v)
            elif isinstance(v, float):
                s = "—" if pd.isna(v) else f"{v:,.2f}"
            else:
                s = "—" if v is None else str(v)
            cell = {"v": s}
            if c in toned and isinstance(v, (int, float)):
                cell["tone"] = tone(v)
            if c == bar and isinstance(v, (int, float)) and not pd.isna(v):
                cell["bar"] = max(0.0, min(100.0, float(v)))
            cells.append(cell)
        rows.append(cells)
    return {"type": "table", "columns": cols, "rows": rows}


def item(title, subtitle=None, value=None, sub_value=None, color=None, tone=None):
    """One row of a list: coloured dot, title/subtitle on the left, value on the right."""
    return {"title": title, "subtitle": subtitle, "value": value, "sub_value": sub_value,
            "color": color, "tone": tone}


def items(rows):
    return {"type": "items", "rows": rows}


def _md(s):
    """Escape HTML, then turn **bold** into <strong>. That's all the markdown we need."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(str(s)))


def notes(lines):
    return {"type": "notes", "html": [_md(l) for l in lines]}


def text(s):
    return {"type": "text", "html": _md(s)}


def side(name, value, sub=None, color=None):
    """One side of a duel(): a name, a big value and a line under it."""
    return {"name": name, "value": value, "sub": sub, "color": color}


def duel(left, right, verdict=None, tone=None):
    """Two things side by side, with a one-line verdict under them (tone "pos" / "neg" colours it)."""
    return {"type": "duel", "sides": [left, right], "verdict": _md(verdict) if verdict else None, "tone": tone}


def fold(label, blocks=None, cards=None):
    """Collapsed by default; opens on tap. Holds blocks, or whole cards (other @section results)."""
    return {"type": "fold", "label": label, "blocks": blocks or [], "cards": [c for c in (cards or []) if c]}


def tabs(label, tabs, open=False):
    """A "More details" panel: a row of tab buttons, one tab shown at a time (drawn on first visit).
    tabs: [(icon, name, blurb, [cards])]. open: start expanded."""
    return {"type": "tabs", "label": label, "open": bool(open),
            "tabs": [{"icon": i, "name": n, "blurb": b, "cards": [c for c in cs if c]} for i, n, b, cs in tabs]}


def tile(icon, label, value, sub=None, level=0.0, tone=None):
    """One tile of tiles(): an emoji, a label, a value, a small line and a shade (level 0..1)."""
    return {"icon": icon, "label": label, "value": value, "sub": sub, "level": round(float(level), 3), "tone": tone}


def tiles(rows):
    return {"type": "tiles", "rows": rows}


def action(label, url, status=None):
    """A button that POSTs to `url`; the reply's "status" (or "error") is shown and the page reloads."""
    return {"type": "action", "label": label, "url": url, "status": status}


def raw(kind, **data):
    """A block drawn by a dedicated widget in app.js (e.g. the cash-flow uploader)."""
    return {"type": kind, **data}


# ---------------------------------------------------------------------------
# Controls: inputs at the top of a page. Their values come back as `params` on every reload.
# ---------------------------------------------------------------------------
def select(name, label, options, value):
    """options: [(value, label)] or [value]."""
    opts = [{"value": str(o[0]), "label": str(o[1])} if isinstance(o, tuple) else {"value": str(o), "label": str(o)}
            for o in options]
    return {"type": "select", "name": name, "label": label, "options": opts, "value": str(value)}


def number(name, label, value, min=None, max=None, step=1):
    return {"type": "number", "name": name, "label": label, "value": value, "min": min, "max": max, "step": step}


def date_input(name, label, value):
    return {"type": "date", "name": name, "label": label, "value": str(value)}


def chips(name, options, value):
    """A row of chips, one of them on. options: [(value, label)]."""
    return {"type": "chips", "name": name, "options": [{"value": str(v), "label": str(l)} for v, l in options],
            "value": str(value)}


def toggle(name, label, value):
    return {"type": "toggle", "name": name, "label": label, "value": bool(value)}


def param(params, name, default, cast=str):
    """Read a control's value from the request, falling back to `default`."""
    v = params.get(name)
    if v in (None, ""):
        return default
    if cast is bool:
        return str(v).lower() in ("1", "true", "yes", "on")
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default
