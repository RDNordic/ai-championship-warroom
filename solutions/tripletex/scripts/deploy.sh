#!/bin/bash
# Build, deploy, and capture logs for the Tripletex agent.
# Usage: ./scripts/deploy.sh
#
# After deploy, run a scoring batch on app.ainm.no, then:
#   ./scripts/capture_logs.sh

set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=nmiai-490717
REGION=europe-north1
IMAGE=europe-north1-docker.pkg.dev/$PROJECT/tripletex/tripletex-agent:latest
SERVICE=tripletex-agent
ANTHROPIC_KEY="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"

echo "=== Building image ==="
gcloud builds submit --tag "$IMAGE" --region="$REGION" .

echo ""
echo "=== Deploying to Cloud Run ==="
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --set-env-vars "ANTHROPIC_API_KEY=$ANTHROPIC_KEY,SOLVE_EVENT_LOG_PATH=/tmp/solve-events.jsonl"

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
