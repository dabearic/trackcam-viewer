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

Write-Host "==> Updating job image and re-applying GPU + volume config..."
# Mirrors the gcloud command in terraform_data.inference_gpu so a deploy
# never leaves the job in a state where the provisioner-managed fields
# (GPU, zonal redundancy, model-cache volume, KAGGLEHUB_CACHE) are stale.
gcloud beta run jobs update speciesnet-inference `
  --image $IMAGE `
  --gpu=1 --gpu-type=nvidia-l4 `
  --execution-environment=gen2 `
  --gpu-zonal-redundancy `
  --update-env-vars=KAGGLEHUB_CACHE=/mnt/model-cache `
  --clear-volumes `
  --clear-volume-mounts `
  --add-volume=name=model-cache,type=cloud-storage,bucket=trackcam-viewer-model-cache `
  --add-volume-mount=volume=model-cache,mount-path=/mnt/model-cache `
  --region us-east4 `
  --project trackcam-viewer
if ($LASTEXITCODE -ne 0) { throw "gcloud job update failed" }

Write-Host "==> Done."
