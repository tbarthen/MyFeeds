#!/usr/bin/env bash
set -euo pipefail

PROJECT="glossy-reserve-153120"
REGION="us-central1"
BUCKET="myfeeds-market-close"
FUNCTION="market-close-feed"
SCHEDULER_JOB="market-close-daily"

echo "==> Creating GCS bucket (if needed)..."
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT}" \
  --location="${REGION}" \
  --uniform-bucket-level-access 2>/dev/null || echo "Bucket already exists"

echo "==> Setting bucket public read..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member=allUsers \
  --role=roles/storage.objectViewer \
  --project="${PROJECT}" 2>/dev/null || echo "Policy already set"

echo "==> Deploying Cloud Function..."
gcloud functions deploy "${FUNCTION}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --runtime=python312 \
  --trigger-http \
  --allow-unauthenticated \
  --entry-point=market_close_feed \
  --source="$(dirname "$0")" \
  --timeout=540 \
  --memory=256MiB \
  --gen2

FUNCTION_URL=$(gcloud functions describe "${FUNCTION}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --gen2 \
  --format="value(serviceConfig.uri)")

echo "==> Function URL: ${FUNCTION_URL}"

echo "==> Creating Cloud Scheduler job..."
gcloud scheduler jobs delete "${SCHEDULER_JOB}" \
  --project="${PROJECT}" \
  --location="${REGION}" \
  --quiet 2>/dev/null || true

gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
  --project="${PROJECT}" \
  --location="${REGION}" \
  --schedule="0 17 * * 1-5" \
  --time-zone="America/New_York" \
  --uri="${FUNCTION_URL}" \
  --http-method=GET \
  --attempt-deadline=1800s

echo "==> Done. Trigger manually with:"
echo "    curl ${FUNCTION_URL}"
