# TrackCam Viewer

A web app for processing and browsing trail/trap camera photos.
Uses [SpeciesNet](https://github.com/google/cameratrapai) to identify animals
and draw bounding boxes, and runs on Google Cloud with GPU-accelerated inference.

## What it does

- Upload folders of trail-cam images directly from the browser
- Run SpeciesNet (detection + classification) on the batch in a GPU Cloud Run Job
- Browse results grouped by timestamp with a gallery view
- Filter by species, confidence, date, or category (animal / vehicle / human / blank)
- Click any image for a full-screen view with bounding-box overlays
- See a detection-crop carousel for every photo (pre-cropped for fast loading)
- Day summary charts showing species counts over time
- Automatic deduplication — reuploading the same folder skips already-processed images
- Google sign-in, per-user data isolation

## Architecture

```
Browser (Vue 3 SPA)
      │
      │  Firebase ID token
      ▼
Cloud Run service (FastAPI)   ─── Firestore (predictions + jobs)
      │                       ─── GCS (images + crops, signed URLs)
      │  RunJob
      ▼
Cloud Run Job (NVIDIA L4 GPU)
  └── SpeciesNet inference → writes predictions + crops back
```

- **Frontend** — Vue 3 + Vite, built into static assets and served by the same Cloud Run service as the API.
- **Backend** — FastAPI. Verifies Firebase ID tokens, issues signed GCS URLs, triggers inference jobs.
- **Inference** — Cloud Run Job built on `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`. Downloads images from GCS, runs `speciesnet.scripts.run_model`, generates per-detection crops with PIL, writes everything to Firestore.
- **Storage** — GCS for source images (`images/{uid}/...`) and detection crops (`crops/{uid}/...`). Firestore for predictions and job state.
- **Auth** — Identity Platform with Google Sign-In. No user data is shared across accounts.
- **Infra** — Terraform manages the GCP project (Cloud Run, Firestore, GCS, IAM, Identity Platform, Artifact Registry).

## Layout

```
webapp/
  backend/
    main.py         — local dev backend (predictions.json + subprocess)
    main_cloud.py   — cloud backend (Firestore + GCS + Cloud Run Jobs)
  frontend/         — Vue 3 SPA
infra/
  Dockerfile              — API + frontend container
  Dockerfile.inference    — GPU inference container
  inference/job.py        — Cloud Run Job entrypoint
  terraform/              — infra-as-code
  deploy-api.ps1          — build + push + deploy API
  deploy-inference.ps1    — build + push inference image
SETUP.md                  — full first-time setup walkthrough
```

## Local development

The local backend uses the same Vue frontend but stores predictions in a
`predictions.json` file and runs SpeciesNet via subprocess — no GCP required.

```
cd webapp/backend
pip install -r requirements.txt
python main.py                      # localhost:8000

cd webapp/frontend
npm install
npm run dev                         # localhost:5173
```

The frontend's `AUTH_ENABLED` flag in `firebase.js` is tied to Vite's
build mode: `npm run dev` skips sign-in, production builds require it.

## Cloud deployment

See [SETUP.md](SETUP.md) for the full first-time walkthrough (gcloud /
Terraform install, OAuth consent, Identity Platform, GPU quota request,
Docker builds, Firebase config).

Once everything is deployed, iterating on code is just:

```
# after editing backend / frontend
infra/deploy-api.ps1

# after editing the inference job
infra/deploy-inference.ps1
```

## Requirements

- GCP project with billing enabled
- NVIDIA L4 GPU quota in `us-east4` (`terraform apply` will prompt; quota
  request is usually approved within a few hours)
- gcloud CLI, Terraform >= 1.5, Docker Desktop, Node.js 20+
