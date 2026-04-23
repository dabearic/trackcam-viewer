"""
TrackCam Viewer — cloud backend (GCS + Firestore + Cloud Run Jobs).

Environment variables:
  GCS_BUCKET          — GCS bucket name
  GCP_PROJECT         — GCP project ID
  INFERENCE_JOB_NAME  — full Cloud Run Job resource name
                        e.g. projects/trackcam-viewer/locations/us-east4/jobs/speciesnet-inference
"""
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import auth as fb_auth
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore, storage
from google.cloud import run_v2
from pydantic import BaseModel

# ── App + GCP clients ─────────────────────────────────────────────────────────
app = FastAPI(title="TrackCam Viewer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

firebase_admin.initialize_app()   # uses Application Default Credentials

GCS_BUCKET         = os.environ["GCS_BUCKET"]
GCP_PROJECT        = os.environ["GCP_PROJECT"]
INFERENCE_JOB_NAME = os.environ["INFERENCE_JOB_NAME"]

_db      = firestore.Client(project=GCP_PROJECT)
_storage = storage.Client(project=GCP_PROJECT)
_bucket  = _storage.bucket(GCS_BUCKET)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}


# ── Auth ──────────────────────────────────────────────────────────────────────

async def verify_token(authorization: str = Header(None)) -> str:
    """Verify Firebase ID token and return the uid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        decoded = fb_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


# ── Predictions ───────────────────────────────────────────────────────────────

@app.get("/api/predictions")
async def get_predictions(uid: str = Depends(verify_token)):
    docs = (
        _db.collection("users").document(uid)
        .collection("predictions")
        .stream()
    )
    predictions = []
    for doc in docs:
        d = doc.to_dict()
        # Normalise: frontend uses 'filepath' as the image path key
        d.setdefault("filepath", d.get("gcs_path", ""))
        predictions.append(d)
    return {"predictions": predictions}


# ── Image serving (signed URL redirect) ───────────────────────────────────────

@app.get("/api/image")
async def get_image(
    path: str = Query(..., description="GCS object path, e.g. images/uid/folder/file.jpg"),
    uid: str = Depends(verify_token),
):
    if not path.startswith(f"images/{uid}/"):
        raise HTTPException(status_code=403, detail="Access denied")
    url = _bucket.blob(path).generate_signed_url(
        expiration=timedelta(minutes=15),
        method="GET",
        version="v4",
    )
    return RedirectResponse(url, status_code=307)


# ── Upload ────────────────────────────────────────────────────────────────────

class UploadPrepareRequest(BaseModel):
    folder: str
    filenames: list[str]


@app.post("/api/upload/prepare")
async def prepare_upload(
    req: UploadPrepareRequest,
    uid: str = Depends(verify_token),
):
    """Return a signed PUT URL for each filename so the browser can upload directly to GCS."""
    if not req.filenames:
        raise HTTPException(status_code=400, detail="No filenames provided")

    folder = _safe_folder(req.folder)
    uploads = []

    for raw_name in req.filenames:
        filename  = Path(raw_name).name  # strip any path component
        if Path(filename).suffix.lower() not in IMAGE_EXTS:
            continue
        gcs_path = f"images/{uid}/{folder}/{filename}"
        url = _bucket.blob(gcs_path).generate_signed_url(
            expiration=timedelta(minutes=30),
            method="PUT",
            content_type="image/jpeg",
            version="v4",
        )
        uploads.append({"filename": filename, "gcs_path": gcs_path, "url": url})

    return {"uploads": uploads, "folder": folder}


# ── Processing jobs ───────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    folder: str
    gcs_paths: list[str]              # already-uploaded GCS object paths
    country: Optional[str] = None
    admin1_region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@app.post("/api/process", status_code=202)
async def start_process(
    req: ProcessRequest,
    uid: str = Depends(verify_token),
):
    if not req.gcs_paths:
        raise HTTPException(status_code=400, detail="No files to process")

    # Deduplicate — skip GCS paths that already have a prediction doc
    existing = _existing_gcs_paths(uid)
    new_paths = [p for p in req.gcs_paths if p not in existing]
    skipped   = len(req.gcs_paths) - len(new_paths)

    if not new_paths:
        return {
            "job_id": None,
            "message": f"All {len(req.gcs_paths)} image(s) already processed — nothing to do",
            "skipped": skipped,
        }

    job_id = uuid.uuid4().hex[:8]
    now    = _now()

    job_doc = {
        "job_id":  job_id,
        "uid":     uid,
        "folder":  req.folder,
        "status":  "pending",
        "message": f"Queued — {len(new_paths)} new image(s)" + (f", {skipped} skipped" if skipped else ""),
        "progress": {},
        "log":     [],
        "files":   new_paths,
        "file_count": len(new_paths),
        "params": {
            "country":       req.country,
            "admin1_region": req.admin1_region,
            "latitude":      req.latitude,
            "longitude":     req.longitude,
        },
        "created_at":   now,
        "updated_at":   now,
        "completed_at": None,
    }

    _db.collection("users").document(uid).collection("jobs").document(job_id).set(job_doc)

    # Trigger Cloud Run Job
    jobs_client = run_v2.JobsClient()
    jobs_client.run_job(
        run_v2.RunJobRequest(
            name=INFERENCE_JOB_NAME,
            overrides=run_v2.RunJobRequest.Overrides(
                container_overrides=[
                    run_v2.RunJobRequest.Overrides.ContainerOverride(
                        env=[
                            run_v2.EnvVar(name="JOB_ID",  value=job_id),
                            run_v2.EnvVar(name="USER_ID", value=uid),
                        ]
                    )
                ]
            ),
        )
    )

    return {"job_id": job_id, "skipped": skipped}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, uid: str = Depends(verify_token)):
    doc = (
        _db.collection("users").document(uid)
        .collection("jobs").document(job_id)
        .get()
    )
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc.to_dict()


@app.get("/api/jobs")
async def list_jobs(uid: str = Depends(verify_token)):
    docs = (
        _db.collection("users").document(uid)
        .collection("jobs")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(20)
        .stream()
    )
    return [doc.to_dict() for doc in docs]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _existing_gcs_paths(uid: str) -> set[str]:
    docs = _db.collection("users").document(uid).collection("predictions").stream()
    return {d.to_dict().get("gcs_path", "") for d in docs}


def _safe_folder(name: str) -> str:
    """Strip path separators so folder names are safe GCS prefixes."""
    return Path(name).name or "default"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Serve Vue SPA (must be last) ──────────────────────────────────────────────

_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_cloud:app", host="0.0.0.0", port=8080, reload=False)
