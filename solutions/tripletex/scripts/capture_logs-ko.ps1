# Capture logs from Cloud Run after a scoring run.
# Usage: .\scripts\capture_logs-ko.ps1 [minutes_back]
#
# Saves to logs/run_TIMESTAMP.log and prints the path.

$ErrorActionPreference = "Stop"

$PROJECT = "nmiai-490717"
$REGION = "europe-north1"
$SERVICE = "captains-tripletex"
$MINUTES_BACK = if ($args.Count -gt 0) { $args[0] } else { 30 }

# Use local gcloud config
$configDir = Join-Path $PSScriptRoot "..\.gcloud-config"
if (Test-Path $configDir) { $env:CLOUDSDK_CONFIG = (Resolve-Path $configDir).Path }

$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$LOG_DIR = Join-Path $PSScriptRoot "..\logs"
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR | Out-Null }
$LOG_FILE = Join-Path $LOG_DIR "run_${TIMESTAMP}.log"

Write-Host "=== Fetching last $MINUTES_BACK min of Cloud Run logs ==="

$filter = "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE AND timestamp>=""-${MINUTES_BACK}m"""
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE" --project=$PROJECT --limit=500 --format="value(timestamp,textPayload,jsonPayload)" --freshness="${MINUTES_BACK}m" | Out-File -Encoding utf8 $LOG_FILE

$LINES = (Get-Content $LOG_FILE -ErrorAction SilentlyContinue | Where-Object { $_.Trim() -ne "" } | Measure-Object).Count
Write-Host "Saved $LINES log lines to $LOG_FILE"

$resolvedLog = (Resolve-Path $LOG_FILE).Path
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  LOG FILE:" -ForegroundColor Green
Write-Host "  $resolvedLog" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
