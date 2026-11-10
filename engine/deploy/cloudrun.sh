#!/bin/sh
# Deploy the engine to Cloud Run (Mumbai) with a Litestream-replicated SQLite
# database and a 15-minute scheduler tick.
#
# Required env: PROJECT, BUCKET, JOB_TOKEN, VENICE_API_KEY
# Optional env: OPENAQ_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, KHIDKI_CORS
set -eu
REGION=${REGION:-asia-south1}
SERVICE=${SERVICE:-khidki-engine}

gcloud services enable run.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com storage.googleapis.com --project "$PROJECT"
gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$REGION" --uniform-bucket-level-access

ENVS="LITESTREAM_BUCKET=$BUCKET,KHIDKI_JOB_TOKEN=$JOB_TOKEN,VENICE_API_KEY=$VENICE_API_KEY,KHIDKI_CORS=${KHIDKI_CORS:-*}"
[ -n "${OPENAQ_API_KEY:-}" ] && ENVS="$ENVS,OPENAQ_API_KEY=$OPENAQ_API_KEY"
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] && ENVS="$ENVS,TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"
[ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ] && ENVS="$ENVS,TELEGRAM_WEBHOOK_SECRET=$TELEGRAM_WEBHOOK_SECRET"

# One instance: SQLite has a single writer.
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source . \
  --allow-unauthenticated --max-instances 1 --min-instances 0 --memory 1Gi --cpu 1 \
  --timeout 900 --concurrency 40 --set-env-vars "$ENVS"

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')
SA=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(spec.template.spec.serviceAccountName)')
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" --role roles/storage.objectAdmin >/dev/null

gcloud scheduler jobs describe khidki-tick --project "$PROJECT" --location "$REGION" >/dev/null 2>&1 && \
  gcloud scheduler jobs delete khidki-tick --project "$PROJECT" --location "$REGION" --quiet
gcloud scheduler jobs create http khidki-tick --project "$PROJECT" --location "$REGION" \
  --schedule "*/15 * * * *" --time-zone "Asia/Kolkata" --http-method POST \
  --uri "$URL/jobs/tick" --headers "Authorization=Bearer $JOB_TOKEN" --attempt-deadline 900s

echo "deployed: $URL"
