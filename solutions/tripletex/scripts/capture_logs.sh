#!/bin/bash
# Capture JSONL logs from Cloud Run after a scoring run.
# Usage: ./scripts/capture_logs.sh [tail_count]
#
# Saves to logs/run_TIMESTAMP.jsonl and prints a summary.

set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=nmiai-490717
REGION=europe-north1
SERVICE=tripletex-agent
TAIL="${1:-0}"

SERVICE_URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)")

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_${TIMESTAMP}.jsonl"

echo "=== Fetching logs from $SERVICE_URL ==="
if [ "$TAIL" -gt 0 ]; then
  curl -s "$SERVICE_URL/logs?tail=$TAIL" > "$LOG_FILE"
else
  curl -s "$SERVICE_URL/logs" > "$LOG_FILE"
fi

LINES=$(wc -l < "$LOG_FILE")
echo "Saved $LINES events to $LOG_FILE"

echo ""
echo "=== Summary ==="
python3 -c "
import json, sys
from collections import Counter

events = []
for line in open('$LOG_FILE'):
    line = line.strip()
    if line:
        events.append(json.loads(line))

by_type = Counter(e.get('event', '?') for e in events)
print(f'Total events: {len(events)}')
for evt_type, count in by_type.most_common():
    print(f'  {evt_type}: {count}')

# Count traces
traces = set(e.get('trace_id', '') for e in events)
print(f'Unique traces (requests): {len(traces)}')

# Count API call outcomes
calls = [e for e in events if e.get('event') == 'tripletex_call']
statuses = Counter(e.get('call', {}).get('status_code', '?') for e in calls)
print(f'Tripletex API calls: {len(calls)}')
for status, count in statuses.most_common():
    print(f'  HTTP {status}: {count}')

# Completed vs failed
completed = sum(1 for e in events if e.get('event') == 'completed')
failed = sum(1 for e in events if e.get('event') == 'failed')
print(f'Completed: {completed}, Failed: {failed}')
" 2>/dev/null || echo "(install python3 for summary)"

echo ""
echo "To feed these logs to Claude Code:"
echo "  cat $LOG_FILE"
