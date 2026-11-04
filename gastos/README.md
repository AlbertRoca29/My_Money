# Gastos

Expenses and income, as a phone-first web app. Replaces logging them straight into the Gastos Google Sheet.
It is the default page of My Money: the same server shows Gastos at `/` and the portfolio at `/portfolio`,
with a switcher at the top of both.

## Run it

```bash
.venv/bin/python app.py        # from My_Money/, then open http://127.0.0.1:8050
```

On your phone (same Wi-Fi): start it with `MY_MONEY_HOST=0.0.0.0`, open `http://<this computer's IP>:8050`,
then **Add to Home Screen**.

First time: put the sheet's link in `GASTOS_SHEET_URL` (environment, `config_local.py` or `gastos/config_local.py`), then **Settings › Import from Google Sheet** (or `.venv/bin/python -m gastos.db`). It reads the GASTOS and
INGRESOS tabs; running it again updates rows by ID and never touches entries made in the app.

## Where things are

| File | What it does |
|---|---|
| `db.py` | The SQLite table (`gastos.db`, git-ignored) and the Google Sheet import |
| `routes.py` | Serves `web/` and the `/api` routes (a blueprint that `../app.py` registers at `/`) |
| `web/store.js` | **The only file that talks to the server.** Swap it to move to GitHub Pages + a hosted DB |
| `web/app.js` | The screens: Home, Movements, Stats, Settings and the add/edit sheet |
| `web/style.css` | Same look as My Money, with dark mode |
| `web/sw.js`, `manifest.webmanifest` | Installable app, works offline with the last data seen |

## Rules carried over from the sheet

- **Paid by others** (the old `Supply` column): shown, but left out of every total, like TOTAL did.
- **Income amount** is what reached the account (the sheet's "Import (brut)" column); the optional
  **gross** is the before-tax figure (the sheet's "Import (net)").
- Amounts accept sums: `12,5 + 3`.
- Typing a name you've used before picks its category automatically.

## Moving to GitHub Pages later

`web/` is plain static files, so it can be published as-is. Rewrite `web/store.js` against the hosted
database (e.g. Supabase: one `entries` table with the columns in `db.py`, plus a storage bucket for receipts)
and add login, since the data would no longer be on your own machine.
