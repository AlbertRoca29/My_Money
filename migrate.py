"""One-time move of the data on this computer into your Google Sheet and bucket.

    gastos/gastos.db            -> Movements tab
    portfolios/YYYYMMDD.json    -> Snapshots tab
    gastos/receipts/*           -> bucket receipts/
    portfolios/lookthrough/*    -> bucket lookthrough/

Needs SHEET_ID, PROJECT and BUCKET in config_local.py (see DEPLOY.md). It creates the two tabs, and stops if
either already has rows, so running it twice can't duplicate anything. The files here are left as they are.

    .venv/bin/python migrate.py            show what would be copied
    .venv/bin/python migrate.py --go       copy it
"""
import json
import sqlite3
import sys
from pathlib import Path

import config
import gsheet
import storage
from gastos import db
from web import data

HERE = Path(__file__).parent
GO = "--go" in sys.argv


def movements():
    con = sqlite3.connect(HERE / "gastos" / "gastos.db")
    con.row_factory = sqlite3.Row
    rows = con.execute(f"SELECT {', '.join(db.FIELDS)} FROM entries ORDER BY date, updated_at").fetchall()
    return [db._row(dict(r) | {"paid_by_other": bool(r["paid_by_other"])}) for r in rows]


def snapshots():
    rows = []
    for p in sorted((HERE / "portfolios").glob("[0-9]" * 8 + ".json")):
        day = f"{p.stem[:4]}-{p.stem[4:6]}-{p.stem[6:]}"
        for category, assets in json.loads(p.read_text()).items():
            if not isinstance(assets, dict):  # very old files: one number per category
                assets = {category: assets}
            rows += [[day, category, name, amount] for name, amount in assets.items()]
    return sorted(rows, key=lambda r: (r[0], data._category_order(r[1])))


def files(folder, prefix):
    return [(f"{prefix}/{p.name}", p) for p in sorted((HERE / folder).glob("*")) if p.is_file()]


def main():
    if not (config.SHEET_ID and config.BUCKET):
        sys.exit("Set SHEET_ID, PROJECT and BUCKET in config_local.py first (DEPLOY.md, step 6).")
    moves, snaps = movements(), snapshots()
    uploads = files("gastos/receipts", "receipts") + files("portfolios/lookthrough", "lookthrough")
    print(f"{len(moves)} movements, {len(snaps)} snapshot rows "
          f"({len({r[0] for r in snaps})} snapshots), {len(uploads)} files for gs://{config.BUCKET}")
    if not GO:
        return print("Nothing copied yet: run again with --go.")

    db.setup(), data.setup()
    for tab in (config.MOVEMENTS_TAB, config.SNAPSHOTS_TAB):
        if any(not gsheet.blank(r) for r in gsheet.read(tab)[1:]):
            sys.exit(f"The {tab} tab already has rows: stopping so nothing is duplicated.")
    for i in range(0, len(moves), 500):  # a few big writes rather than one per row
        gsheet.append(config.MOVEMENTS_TAB, moves[i:i + 500])
    gsheet.update(config.SNAPSHOTS_TAB, "A2", snaps)
    for key, path in uploads:
        storage.write(key, path.read_bytes())

    # Read everything back, the way the app will
    back = db.all_entries()
    assert len(back) == len(moves), f"{len(back)} movements read back, {len(moves)} written"
    assert len(data.portfolios()) == len({r[0] for r in snaps})
    print(f"Done: {len(back)} movements and {len(data.portfolios())} snapshots read back from the sheet.")


if __name__ == "__main__":
    main()
