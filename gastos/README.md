# Gastos

Expenses and income, as a web app for the phone and the computer. Replaces logging them straight into the Gastos Google Sheet.
It is the default page of My Money: the same server shows Gastos at `/` and the portfolio at `/portfolio`,
with a switcher at the top of both.

## Run it

Online: see [../DEPLOY.md](../DEPLOY.md), then open the link on your computer.
On your computer: `.venv/bin/python app.py` from My_Money/, then http://127.0.0.1:8050.

Every movement is one row in the **Movements** tab of your Google Sheet (columns in `db.py`). You can edit or
sort rows there; the app sees it within half a minute.

## Where things are

| File | What it does |
|---|---|
| `db.py` | The Movements tab: reading, adding, editing and deleting rows, and the daily savings for Portfolio |
| `routes.py` | Serves `web/` and the `/api` routes (a blueprint that `../app.py` registers at `/`) |
| `web/store.js` | The only file that talks to the server (and sends you to sign in when needed) |
| `web/app.js` | The screens: Home, Movements, Stats, the add/edit sheet and Tidy names (settings are the shared ⚙ sheet, `../static/settings.js`) |
| `web/style.css` | Same look as My Money, with dark mode |
| `web/sw.js`, `manifest.webmanifest` | Installable app, works offline with the last data seen |

## Rules carried over from the sheet

- **Paid by others** (the old `Supply` column): shown, but left out of every total, like TOTAL did.
- **Income amount** is what reached the account (the sheet's "Import (brut)" column); the optional
  **gross** is the before-tax figure (the sheet's "Import (net)").
- Amounts accept sums: `12,5 + 3`.
- Typing a name you've used before picks its category automatically.
