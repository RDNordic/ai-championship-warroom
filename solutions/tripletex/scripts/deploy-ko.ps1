# Build, deploy, and clear logs for captains-tripletex (KO's instance).
# Usage: .\scripts\deploy-ko.ps1
#
# After deploy, run a scoring batch on app.ainm.no, then:
#   .\scripts\capture_logs-ko.ps1

$ErrorActionPreference = "Stop"

$PROJECT = "nmiai-490717"
$REGION = "europe-north1"
$SERVICE = "captains-tripletex"

# Use local gcloud config to avoid NTUSER.DAT issues
$configDir = Join-Path $PSScriptRoot "..\.gcloud-config"
if (Test-Path $configDir) { $env:CLOUDSDK_CONFIG = (Resolve-Path $configDir).Path }

Write-Host "=== Deploying to Cloud Run (source build) ==="
gcloud run deploy $SERVICE --source (Resolve-Path (Join-Path $PSScriptRoot "..")).Path --region=$REGION --project=$PROJECT --allow-unauthenticated --timeout=300 --memory=1Gi
if ($LASTEXITCODE -ne 0) { throw "Deploy failed" }

$SERVICE_URL = gcloud run services describe $SERVICE --region $REGION --project $PROJECT --format="value(status.url)"
Write-Host ""
Write-Host "=== Clearing old logs ==="
Invoke-WebRequest -Uri "$SERVICE_URL/logs" -Method DELETE -UseBasicParsing

Write-Host ""
Write-Host "=== Deploy complete ==="
Write-Host "Service URL: $SERVICE_URL"
Write-Host ""
Write-Host "Now run a scoring batch on app.ainm.no, then:"
Write-Host "  .\scripts\capture_logs-ko.ps1"
