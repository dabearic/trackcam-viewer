"""
Pre-download SpeciesNet model artifacts at image-build time so the inference
job doesn't pay the ~1 GB Kaggle Hub + GitHub fetch on every cold start.

Pulls:
  - The Kaggle bundle (classifier weights, taxonomy, geofence, info.json)
  - The MegaDetector .pt that speciesnet's info.json references via a GitHub
    URL — speciesnet would otherwise lazy-fetch this on first run_model call

KAGGLEHUB_CACHE must be set before invoking; the resolved files end up under
$KAGGLEHUB_CACHE/models/google/speciesnet/pyTorch/<version>/<rev>/
"""
import json
import os
import urllib.request

import kagglehub

MODEL = "google/speciesnet/pyTorch/v4.0.2a/1"

base = kagglehub.model_download(MODEL)
info = json.load(open(os.path.join(base, "info.json")))

detector_url = info.get("detector")
if detector_url:
    fname = detector_url.replace(":", "_").replace("/", "_")
    target = os.path.join(base, fname)
    if not os.path.exists(target):
        print(f"prefetch: fetching detector from {detector_url}")
        urllib.request.urlretrieve(detector_url, target)

print(f"prefetch: model ready under {base}")
