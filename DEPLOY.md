# Put My Money online (Google Cloud)

What you end up with: one private link (Gastos first, Portfolio behind the switch) for your phone and computer
(save it to your phone's home screen to open Gastos like an app). Only the Google accounts you list can sign in.

```
 phone / laptop ──(Sign in with Google)──► Cloud Run: app.py ──► Google Sheet  "Movements" + "Snapshots" tabs
                                                 ▲              └► bucket        receipts, downloads
                         every night, 05:00 ─────┘ Cloud Scheduler (pre-downloads ETF data so pages open fast)
```

- **Your data is a Google Sheet you own.** You can read, sort and fix it in Sheets; the app sees edits within
  half a minute. Keep the first row (the column names) as it is.
- **Cost for one person: €0–1 a month** (inside Google's free allowances; the bucket costs cents).
- **Someone else wants it?** They follow this same page with their own Google account, project and sheet.
  Nobody's data ever passes through yours.

Everything below is done once. Afterwards, changing the app is just `./deploy.sh`.

---

## 1. A Google Cloud project with billing
1. Create a project at [console.cloud.google.com](https://console.cloud.google.com) (or with
   `gcloud projects create`). Note its **ID**, e.g. `my-money-153626`.
2. **Billing › Link a billing account** to it. Google asks for this even when you stay inside the free usage.
3. **Billing › Budgets & alerts › Create budget**: €5 a month, email at 50% and 100%. That's your safety net.

## 2. A new, empty Google Sheet
Create it in your Google Drive (e.g. "My Money data"). Its ID is the long part of the link:
`docs.google.com/spreadsheets/d/`**`<ID>`**`/edit`. Leave it empty: the tabs are made for you.

## 3. deploy.env
```bash
cp deploy.env.example deploy.env
```
Fill in `PROJECT`, `SHEET_ID` and `ALLOWED_EMAILS` (your Gmail). `GOOGLE_CLIENT_ID` comes in the next step.

## 4. The "Sign in with Google" client
In the console, with your project selected, open **Google Auth Platform**:
1. **Branding**: app name "My Money", your email as support and developer contact. Save.
2. **Audience**: User type **External**, leave it in **Testing**, and under **Test users** add your Gmail
   (and anyone in `ALLOWED_EMAILS`). Testing mode is fine forever for a private app.
3. **Clients › Create client** › Web application, name "My Money". Under **Authorized redirect URIs** add
   ```
   https://my-money-<PROJECT NUMBER>.europe-west1.run.app/auth/callback
   ```
   (the project number is on the console's home page; `./deploy.sh setup` also prints the exact address).
4. Copy the **Client ID** into `deploy.env`. Keep the **Client secret** at hand for the next step: it goes
   into Google's Secret Manager, never into a file.

## 5. Set up the project
```bash
./deploy.sh setup
```
Turns on the services, creates the private bucket, the app's service account, the nightly job's account and
the secrets (it asks for the client secret). It ends by printing an address like
`my-money-app@<project>.iam.gserviceaccount.com`: **share the sheet with it as Editor** (Share button in
Sheets, untick "Notify").

## 6. Move your current data in (once)
On your computer the app uses the same sheet and bucket, through your gcloud login. Add to `config_local.py`:
```python
SHEET_ID = "<the sheet ID>"
PROJECT = "<the project ID>"
BUCKET = "<the project ID>-files"
```
and let your gcloud login act as the app's account (once; it opens the browser):
```bash
gcloud auth application-default login --impersonate-service-account my-money-app@<project>.iam.gserviceaccount.com
```
Then:
```bash
.venv/bin/python migrate.py          # shows what it would copy
.venv/bin/python migrate.py --go     # copies gastos.db, the snapshots, receipts and look-through history
```
It stops if the tabs already have rows, so it can't duplicate anything. Your local files are left alone.

## 7. Deploy
```bash
./deploy.sh            # about 3 minutes; prints the link
./deploy.sh schedule   # the nightly refresh (once)
```
Open the link on your computer and sign in.

---

## Afterwards
| To… | Do |
|---|---|
| change the app | edit, try it with `.venv/bin/python app.py`, then `./deploy.sh` |
| add a fund or change settings | edit `config_local.py`, then `./deploy.sh` (it travels inside the app, privately) |
| fix a movement by hand | edit the Movements tab |
| back up | the sheet keeps its own history (File › Version history); `./deploy.sh backup` copies the bucket |
| let someone else in | add their email to `ALLOWED_EMAILS` and to the test users (step 4.2), then `./deploy.sh` |
| see what happened | console › Cloud Run › my-money › Logs |

## How it's kept private
- The GitHub repo has code only. Your data is in your sheet and bucket; your holdings (`config_local.py`)
  go up only inside the app's container, in your own project (`.gcloudignore` lists what never leaves).
- Every page and API call checks the sign-in cookie; the app refuses to start on Cloud Run without
  `ALLOWED_EMAILS`. The sheet is shared with one service account only, and the bucket is private.
- The nightly job proves who it is with a token Google signs; there is no password anywhere.
