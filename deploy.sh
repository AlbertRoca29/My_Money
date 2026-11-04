#!/usr/bin/env bash
# Put My Money on Google Cloud Run. DEPLOY.md walks through the one-time steps around this.
#
#   ./deploy.sh setup      once: turn on the services, make the bucket, the service accounts and the secrets
#   ./deploy.sh            send the current code (about 3 minutes); run it again after every change
#   ./deploy.sh schedule   once, after the first deploy: the nightly refresh at 05:00 Madrid time
#   ./deploy.sh backup     copy the bucket (receipts, look-through history) into backup/
#
# Settings come from deploy.env (copy deploy.env.example). Every command names the project, so whatever
# project gcloud has as its default is never used.
set -euo pipefail
cd "$(dirname "$0")"
[ -f deploy.env ] || { echo "Copy deploy.env.example to deploy.env and fill it in first (see DEPLOY.md)."; exit 1; }
source deploy.env
: "${PROJECT:?set PROJECT in deploy.env}"
REGION=${REGION:-europe-west1}
SERVICE=my-money
BUCKET=$PROJECT-files
RUN_SA=my-money-app@$PROJECT.iam.gserviceaccount.com
CRON_SA=my-money-scheduler@$PROJECT.iam.gserviceaccount.com

g() { gcloud --project "$PROJECT" --billing-project "$PROJECT" --quiet "$@"; }
project_number() { g projects describe "$PROJECT" --format='value(projectNumber)' 2>/dev/null; }
if ! NUMBER=$(project_number); then
  # A brand-new project has this API off; turn it on, then give Google a minute to notice
  g services enable cloudresourcemanager.googleapis.com
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do NUMBER=$(project_number) && break; sleep 10; done
  [ -n "$NUMBER" ] || { echo "Could not read $PROJECT's number: try again in a few minutes."; exit 1; }
fi
URL=https://$SERVICE-$NUMBER.$REGION.run.app   # Cloud Run's address for this service, known in advance

setup() {
  echo "== Services"
  g services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    secretmanager.googleapis.com cloudscheduler.googleapis.com sheets.googleapis.com storage.googleapis.com \
    iamcredentials.googleapis.com

  echo "== Service accounts (the app, and the nightly job)"
  g iam service-accounts describe "$RUN_SA" >/dev/null 2>&1 ||
    g iam service-accounts create my-money-app --display-name "My Money app"
  g iam service-accounts describe "$CRON_SA" >/dev/null 2>&1 ||
    g iam service-accounts create my-money-scheduler --display-name "My Money nightly refresh"
  # Lets you run the app on your computer as the app's account (so the sheet is shared with one address only)
  g iam service-accounts add-iam-policy-binding "$RUN_SA" --member "user:$(gcloud config get-value account)" \
    --role roles/iam.serviceAccountTokenCreator >/dev/null
  # The app tags its API calls with this project (so nothing is ever billed elsewhere): that needs this role
  g projects add-iam-policy-binding "$PROJECT" --condition=None \
    --member "serviceAccount:$RUN_SA" --role roles/serviceusage.serviceUsageConsumer >/dev/null
  # The builder that turns the code into a container
  g projects add-iam-policy-binding "$PROJECT" --condition=None \
    --member "serviceAccount:$NUMBER-compute@developer.gserviceaccount.com" --role roles/run.builder >/dev/null

  echo "== Bucket gs://$BUCKET (private)"
  g storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
    g storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access \
      --public-access-prevention
  g storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$RUN_SA" \
    --role roles/storage.objectAdmin >/dev/null
  g storage buckets add-iam-policy-binding "gs://$BUCKET" --member "user:$(gcloud config get-value account)" \
    --role roles/storage.objectAdmin >/dev/null

  echo "== Secrets"
  if ! g secrets describe my-money-session-key >/dev/null 2>&1; then
    openssl rand -base64 48 | tr -d '\n' | g secrets create my-money-session-key --data-file=- --replication-policy automatic
  fi
  if ! g secrets describe my-money-oauth-secret >/dev/null 2>&1; then
    read -rsp "Paste the OAuth client secret (DEPLOY.md, step 4), then Enter: " SECRET; echo
    printf %s "$SECRET" | g secrets create my-money-oauth-secret --data-file=- --replication-policy automatic
  fi
  for s in my-money-session-key my-money-oauth-secret; do
    g secrets add-iam-policy-binding "$s" --member "serviceAccount:$RUN_SA" \
      --role roles/secretmanager.secretAccessor >/dev/null
  done

  echo
  echo "Done. Share your sheet (Editor) with:   $RUN_SA"
  echo "The app will live at:                   $URL"
  echo "Then run:  ./deploy.sh"
}

deploy() {
  : "${SHEET_ID:?set SHEET_ID in deploy.env}" "${ALLOWED_EMAILS:?set ALLOWED_EMAILS in deploy.env}"
  : "${GOOGLE_CLIENT_ID:?set GOOGLE_CLIENT_ID in deploy.env}"
  # ^|^ makes "|" the separator, so ALLOWED_EMAILS may contain commas
  g run deploy "$SERVICE" --source . --region "$REGION" --service-account "$RUN_SA" \
    --allow-unauthenticated --max-instances 1 --memory 1Gi --cpu 1 --cpu-boost --timeout 900 \
    --set-env-vars "^|^MY_MONEY_PROJECT=$PROJECT|MY_MONEY_SHEET=$SHEET_ID|MY_MONEY_BUCKET=$BUCKET|ALLOWED_EMAILS=$ALLOWED_EMAILS|GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID|TASKS_AUDIENCE=$URL|SCHEDULER_EMAIL=$CRON_SA" \
    --set-secrets SECRET_KEY=my-money-session-key:latest,GOOGLE_CLIENT_SECRET=my-money-oauth-secret:latest
  echo "Open $URL"
}

schedule() {
  local verb=create
  g scheduler jobs describe my-money-refresh --location "$REGION" >/dev/null 2>&1 && verb=update
  g scheduler jobs "$verb" http my-money-refresh --location "$REGION" --schedule "0 5 * * *" \
    --time-zone Europe/Madrid --uri "$URL/tasks/refresh" --http-method POST --attempt-deadline 900s \
    --oidc-service-account-email "$CRON_SA" --oidc-token-audience "$URL"
  echo "Nightly refresh set. Run it now with:  gcloud --project $PROJECT scheduler jobs run my-money-refresh --location $REGION"
}

backup() {
  mkdir -p backup
  g storage cp -r "gs://$BUCKET/receipts" "gs://$BUCKET/lookthrough" backup/
  echo "Bucket copied to backup/. The sheet keeps its own history (File › Version history)."
}

case "${1:-deploy}" in
  setup) setup ;; deploy) deploy ;; schedule) schedule ;; backup) backup ;;
  *) echo "usage: ./deploy.sh [setup|deploy|schedule|backup]"; exit 1 ;;
esac
