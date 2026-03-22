# Run this AFTER you submit on app.ainm.no and the scoring run finishes.
# It captures Cloud Run logs, pulls latest git changes, and prints what to paste to Claude.
# Usage: .\scripts\post-score.ps1 [minutes_back]

$ErrorActionPreference = "Stop"

$PROJECT = "nmiai-490717"
$REGION = "europe-north1"
$SERVICE = "captains-tripletex"
$MINUTES_BACK = if ($args.Count -gt 0) { $args[0] } else { 30 }

# Use local gcloud config
$configDir = Join-Path $PSScriptRoot "..\.gcloud-config"
if (Test-Path $configDir) { $env:CLOUDSDK_CONFIG = (Resolve-Path $configDir).Path }

# Capture logs from Cloud Run logging
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$LOG_DIR = Join-Path $PSScriptRoot "..\logs"
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR | Out-Null }
$LOG_FILE = Join-Path $LOG_DIR "run_${TIMESTAMP}.log"

Write-Host "=== Fetching last $MINUTES_BACK min of Cloud Run logs ===" -ForegroundColor Cyan
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE" --project=$PROJECT --limit=500 --format="value(timestamp,textPayload,jsonPayload)" --freshness="${MINUTES_BACK}m" | Out-File -Encoding utf8 $LOG_FILE

$LINES = (Get-Content $LOG_FILE -ErrorAction SilentlyContinue | Where-Object { $_.Trim() -ne "" } | Measure-Object).Count
Write-Host "Saved $LINES log lines to $LOG_FILE"

# Git pull
Write-Host ""
Write-Host "=== Pulling latest changes ===" -ForegroundColor Cyan
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $repoRoot
git pull
Pop-Location

# Print what to paste to Claude
$resolvedLog = (Resolve-Path $LOG_FILE).Path
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  PASTE THIS TO CLAUDE:" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Score: [YOUR SCORE HERE]"
Write-Host "Logs: $resolvedLog"
Write-Host ""
