#!/usr/bin/env pwsh
# Build and push the speciesnet-inference container image.
# The Cloud Run Job pulls :latest at execution time, so no job update is needed.
# Run from anywhere — the script cd's to its own directory.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$IMAGE = "us-east4-docker.pkg.dev/trackcam-viewer/trackcam/inference:latest"

Write-Host "==> Building inference image (this can take 15-30 minutes)..."
docker build -f Dockerfile.inference -t $IMAGE ./inference
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

Write-Host "==> Pushing inference image..."
docker push $IMAGE
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }

Write-Host "==> Done. Next job execution will use the new image."
