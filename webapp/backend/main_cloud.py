"""
TrackCam Viewer — cloud backend (GCS + Firestore + Cloud Run Jobs).

Environment variables:
  GCS_BUCKET          — GCS bucket name
  GCP_PROJECT         — GCP project ID
  INFERENCE_JOB_NAME  — full Cloud Run Job resource name
                        e.g. projects/trackcam-viewer/locations/us-east4/jobs/speciesnet-inference
"""
import hashlib
import json
import os
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import firebase_admin
import google.auth
import google.auth.transport.requests
from firebase_admin import auth as fb_auth
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore, storage
from google.cloud import run_v2
from pydantic import BaseModel, Field, conlist, confloat

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

# Cloud Run provides compute-engine credentials with no private key, so
# generate_signed_url can't sign locally. Pass service_account_email +
# access_token so the library uses the IAM signBlob API instead.
_auth_creds, _ = google.auth.default()


def _resolve_sa_email() -> str:
    # Compute-engine credentials report "default" as an alias — ask the
    # metadata server for the real email address.
    import urllib.request
    email = getattr(_auth_creds, "service_account_email", None)
    if email and email != "default":
        return email
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        return r.read().decode().strip()


_sa_email = _resolve_sa_email()


def _sign_kwargs() -> dict:
    _auth_creds.refresh(google.auth.transport.requests.Request())
    return {"service_account_email": _sa_email, "access_token": _auth_creds.token}

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
        # Backfill stable UUIDs on detections so the manual-edit UI can
        # address them. Idempotent — only writes back if anything was missing.
        detections = d.get("detections") or []
        mutated = False
        for det in detections:
            if "id" not in det:
                det["id"] = uuid.uuid4().hex
                mutated = True
        if mutated:
            doc.reference.update({"detections": detections})
        predictions.append(d)
    return {"predictions": predictions}


@app.delete("/api/predictions")
async def delete_prediction(
    path: str = Query(..., description="GCS object path of the image to delete"),
    uid: str = Depends(verify_token),
):
    """Delete a prediction doc, its source image, and any detection crops."""
    if not path.startswith(f"images/{uid}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    doc_id  = hashlib.md5(path.encode()).hexdigest()
    doc_ref = _db.collection("users").document(uid).collection("predictions").document(doc_id)
    snap    = doc_ref.get()

    crop_paths: list[str] = []
    if snap.exists:
        for det in (snap.to_dict().get("detections") or []):
            crop = det.get("crop_gcs_path")
            if crop and crop.startswith(f"crops/{uid}/"):
                crop_paths.append(crop)

    for blob_path in [path, *crop_paths]:
        try:
            _bucket.blob(blob_path).delete()
        except Exception:
            # Blob already missing — continue so we still clean up Firestore
            pass

    if snap.exists:
        doc_ref.delete()

    return {"deleted": True, "path": path, "crops_deleted": len(crop_paths)}


# ── Image serving (signed URL redirect) ───────────────────────────────────────

@app.get("/api/image")
async def get_image(
    path: str = Query(..., description="GCS object path, e.g. images/uid/folder/file.jpg"),
    token: Optional[str] = Query(None, description="Firebase ID token (for <img src> requests)"),
    authorization: str = Header(None),
):
    # Accept token via Authorization header OR ?token= query param (for <img>)
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ", 1)[1]
    elif token:
        raw_token = token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        uid = fb_auth.verify_id_token(raw_token)["uid"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    if not (path.startswith(f"images/{uid}/") or path.startswith(f"crops/{uid}/")):
        raise HTTPException(status_code=403, detail="Access denied")
    url = _bucket.blob(path).generate_signed_url(
        expiration=timedelta(minutes=15),
        method="GET",
        version="v4",
        **_sign_kwargs(),
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
            **_sign_kwargs(),
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

    job_ref = _db.collection("users").document(uid).collection("jobs").document(job_id)
    job_ref.set(job_doc)

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

    # Move the job off "pending / Queued" right away so the polling UI sees a
    # new message instead of sitting silent during container cold-start. The
    # inference container will overwrite this as soon as main() starts.
    job_ref.update({
        "status":  "running",
        "message": "Loading AI model (can take up to a minute)…",
        "updated_at": _now(),
    })

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


# ── Per-detection edits (Firestore-backed) ───────────────────────────────────
#
# Mirror of the local-backend endpoints in main.py. Detections live as an
# array on the prediction doc (users/{uid}/predictions/{md5(gcs_path)}); each
# mutation is a read-modify-write on that single doc. Single-user assumption
# is fine here — concurrent-edit considerations are tracked in issue #13.

VALID_CATEGORIES = {"1", "2", "3"}


class DetectionCreate(BaseModel):
    """Schema for adding a manual detection to an image."""
    category: str = Field(..., description="'1' animal, '2' human, '3' vehicle")
    label: str
    bbox: conlist(confloat(ge=0.0, le=1.0), min_length=4, max_length=4)
    conf: confloat(ge=0.0, le=1.0) = 1.0
    scientific: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")


class DetectionPatch(BaseModel):
    """Partial update — any field may be omitted to leave it unchanged."""
    category: Optional[str] = None
    label: Optional[str] = None
    conf: Optional[confloat(ge=0.0, le=1.0)] = None
    scientific: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if self.category is not None and self.category not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")


def _prediction_doc_ref(uid: str, path: str):
    """Locate the Firestore doc for a given user + GCS path."""
    doc_id = hashlib.md5(path.encode()).hexdigest()
    return _db.collection("users").document(uid).collection("predictions").document(doc_id)


def _ensure_path_owned(uid: str, path: str) -> None:
    if not path.startswith(f"images/{uid}/"):
        raise HTTPException(status_code=403, detail="Access denied")


def _load_detections(uid: str, path: str):
    """Return (doc_ref, prediction_dict, detections_list). 404 on miss."""
    doc_ref = _prediction_doc_ref(uid, path)
    snap = doc_ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="No prediction for that path")
    data = snap.to_dict()
    return doc_ref, data, (data.get("detections") or [])


@app.delete("/api/predictions/detections")
async def delete_detection(
    path: str = Query(..., description="GCS path of the image"),
    id:   str = Query(..., description="Detection id"),
    uid:  str = Depends(verify_token),
):
    _ensure_path_owned(uid, path)
    doc_ref, _data, detections = _load_detections(uid, path)
    new_dets = [d for d in detections if d.get("id") != id]
    if len(new_dets) == len(detections):
        raise HTTPException(status_code=404, detail="Detection not found")
    doc_ref.update({"detections": new_dets})
    return {"deleted": True, "id": id}


@app.patch("/api/predictions/detections")
async def patch_detection(
    patch: DetectionPatch,
    path:  str = Query(...),
    id:    str = Query(...),
    uid:   str = Depends(verify_token),
):
    """Update category / label / confidence on an existing detection. Marks
    the detection `manual: true` since a human touched it. Bbox is not
    editable here — to move a box, delete + redraw."""
    _ensure_path_owned(uid, path)
    doc_ref, _data, detections = _load_detections(uid, path)
    target = None
    for det in detections:
        if det.get("id") == id:
            target = det
            break
    if target is None:
        raise HTTPException(status_code=404, detail="Detection not found")
    if patch.category   is not None: target["category"]   = patch.category
    if patch.label      is not None: target["label"]      = patch.label
    if patch.conf       is not None: target["conf"]       = float(patch.conf)
    if patch.scientific is not None: target["scientific"] = patch.scientific
    target["manual"] = True
    doc_ref.update({"detections": detections})
    return {"updated": True, "detection": target}


@app.post("/api/predictions/detections", status_code=201)
async def add_detection(
    body: DetectionCreate,
    path: str = Query(..., description="GCS path of the image"),
    uid:  str = Depends(verify_token),
):
    _ensure_path_owned(uid, path)
    doc_ref, _data, detections = _load_detections(uid, path)
    det = {
        "id":       uuid.uuid4().hex,
        "category": body.category,
        "label":    body.label,
        "bbox":     list(body.bbox),
        "conf":     float(body.conf),
        "manual":   True,
    }
    if body.scientific:
        det["scientific"] = body.scientific
    detections.append(det)
    doc_ref.update({"detections": detections})
    return {"created": True, "detection": det}


# ── Custom species (Firestore-backed) ────────────────────────────────────────
# Stored under users/{uid}/species_custom/{lowercased common_name} so the
# document id provides natural de-duplication.

class CustomSpecies(BaseModel):
    common_name: str
    scientific:  Optional[str] = None
    parent:      Optional[str] = None  # "class;order;family" hint


@app.get("/api/species-custom")
async def get_custom_species(uid: str = Depends(verify_token)):
    docs = _db.collection("users").document(uid).collection("species_custom").stream()
    return {"species": [d.to_dict() for d in docs]}


@app.post("/api/species-custom", status_code=201)
async def add_custom_species(
    body: CustomSpecies,
    uid:  str = Depends(verify_token),
):
    cn = (body.common_name or "").strip()
    if not cn:
        raise HTTPException(status_code=400, detail="common_name is required")
    doc_id  = cn.lower()
    doc_ref = _db.collection("users").document(uid).collection("species_custom").document(doc_id)
    snap    = doc_ref.get()
    if snap.exists:
        return {"created": False, "species": snap.to_dict()}
    entry = {
        "id":          uuid.uuid4().hex,
        "common_name": cn,
        "scientific":  (body.scientific or "").strip(),
        "parent":      (body.parent or "").strip(),
    }
    doc_ref.set(entry)
    return {"created": True, "species": entry}


# ── External taxonomy lookups (GBIF + iNaturalist) ───────────────────────────
# Free, unauthenticated upstream APIs. Per-process caches keyed by lowercased
# query keep repeat lookups in one container instance instant. The proxy hides
# the upstream URL from the browser (CORS + future swap to a different source).

_HTTP_USER_AGENT = "TrailCam-Viewer/0.1 (+https://github.com/dabearic/trackcam-viewer)"
_GBIF_CACHE: dict = {}
_INAT_CACHE: dict = {}


@app.get("/api/species-lookup")
def species_lookup(
    name: str = Query(..., min_length=1, description="Scientific or common name"),
    uid:  str = Depends(verify_token),
):
    """Resolve a species name to its full taxonomy via GBIF's match endpoint."""
    key = name.strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="name is required")
    if key in _GBIF_CACHE:
        return _GBIF_CACHE[key]

    url = "https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode({
        "name":   name.strip(),
        "strict": "false",
    })
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GBIF lookup failed: {exc}")

    if raw.get("matchType") == "NONE":
        raise HTTPException(status_code=404, detail=f"No match for '{name}'")

    result = {
        "kingdom":    raw.get("kingdom", ""),
        "phylum":     raw.get("phylum", ""),
        "class":      raw.get("class", ""),
        "order":      raw.get("order", ""),
        "family":     raw.get("family", ""),
        "genus":      raw.get("genus", ""),
        "species":    raw.get("species", ""),
        "scientific": raw.get("scientificName") or raw.get("canonicalName") or "",
        "rank":       raw.get("rank", ""),
        "match_type": raw.get("matchType", ""),
        "confidence": raw.get("confidence", 0),
    }
    _GBIF_CACHE[key] = result
    return result


@app.get("/api/species-autocomplete")
def species_autocomplete(
    q:   str = Query(..., min_length=1, description="Partial common or scientific name"),
    uid: str = Depends(verify_token),
):
    """Autocomplete species names via iNaturalist."""
    key = q.strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="q is required")
    if key in _INAT_CACHE:
        return _INAT_CACHE[key]

    url = "https://api.inaturalist.org/v1/taxa/autocomplete?" + urllib.parse.urlencode({
        "q":        q.strip(),
        "rank":     "species",
        "per_page": 8,
    })
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"iNaturalist autocomplete failed: {exc}")

    out = {
        "results": [
            {
                "id":          r.get("id"),
                "name":        r.get("name", ""),
                "common_name": r.get("preferred_common_name", "") or "",
                "rank":        r.get("rank", ""),
                "iconic":      r.get("iconic_taxon_name", ""),
                "extinct":     bool(r.get("extinct")),
            }
            for r in raw.get("results", [])
            if r.get("rank") == "species" and r.get("name")
        ],
    }
    _INAT_CACHE[key] = out
    return out


# ── Serve Vue SPA (must be last) ──────────────────────────────────────────────

_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_cloud:app", host="0.0.0.0", port=8080, reload=False)
