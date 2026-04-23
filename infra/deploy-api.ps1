#!/usr/bin/env pwsh
# Build, push, and deploy the trackcam-api Cloud Run service.
# Run from anywhere — the script cd's to its own directory.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$IMAGE = "us-east4-docker.pkg.dev/trackcam-viewer/trackcam/api:latest"

Write-Host "==> Building image..."
docker build -f Dockerfile -t $IMAGE ../
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

Write-Host "==> Pushing image..."
docker push $IMAGE
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }

Write-Host "==> Updating Cloud Run service..."
gcloud run services update trackcam-api --image $IMAGE --region us-east4
if ($LASTEXITCODE -ne 0) { throw "gcloud update failed" }

Write-Host "==> Done."
