#!/bin/bash
# Build, deploy, and capture logs for the Tripletex agent.
# Usage: ./scripts/deploy.sh
#
# Reads env vars from .env file at the root of the tripletex folder.
# After deploy, run a scoring batch on app.ainm.no, then:
#   ./scripts/capture_logs.sh

set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env file if it exists
if [ -f .env ]; then
  echo "=== Loading .env ==="
  set -a
  source .env
  set +a
else
  echo "WARNING: No .env file found. Create one from .env.example"
  echo "Expected at: $(pwd)/.env"
  exit 1
fi

PROJECT="${GCP_PROJECT:-nmiai-490717}"
REGION="${GCP_REGION:-europe-north1}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/tripletex/tripletex-agent:latest"
SERVICE="${CLOUD_RUN_SERVICE:-tripletex-agent}"

# Build comma-separated env vars for Cloud Run from .env
# Include all vars except GCP/deployment-specific ones
ENV_VARS=""
while IFS='=' read -r key value; do
  # Skip comments, empty lines, and deployment-specific vars
  [[ -z "$key" || "$key" =~ ^# ]] && continue
  [[ "$key" =~ ^(GCP_PROJECT|GCP_REGION|CLOUD_RUN_SERVICE)$ ]] && continue
  # Strip quotes from value
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  if [ -n "$ENV_VARS" ]; then
    ENV_VARS="$ENV_VARS,$key=$value"
  else
    ENV_VARS="$key=$value"
  fi
done < .env

echo "=== Building image ==="
gcloud builds submit --tag "$IMAGE" --region="$REGION" .

echo ""
echo "=== Deploying to Cloud Run ==="
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --set-env-vars "$ENV_VARS"

echo ""
echo "=== Clearing old logs ==="
SERVICE_URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)")
curl -s -X DELETE "$SERVICE_URL/logs"

echo ""
echo "=== Deploy complete ==="
echo "Service URL: $SERVICE_URL"
echo ""
echo "Now run a scoring batch on app.ainm.no, then:"
echo "  ./scripts/capture_logs.sh"
