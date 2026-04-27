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


# ── Upload + inference kickoff ────────────────────────────────────────────────

class UploadPrepareRequest(BaseModel):
    folder: str
    filenames: list[str]
    country: Optional[str] = None
    admin1_region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@app.post("/api/upload/prepare")
async def prepare_upload(
    req: UploadPrepareRequest,
    uid: str = Depends(verify_token),
):
    """Single-shot kickoff for uploads.

    This used to just return signed PUT URLs; the client then separately
    called /api/process once uploads finished. That put the Cloud Run Job
    cold-start (30–60s) entirely after the upload phase, where the user
    could see it.

    Now we do everything here: dedupe against existing predictions, create
    the job doc, fire run_job, and return the signed URLs alongside the
    job_id. The container cold-starts while the browser is still uploading,
    and the inference job.py waits for any missing files in GCS (up to a
    generous timeout) before proceeding — so the 30–60s cold-start overlaps
    with the upload time instead of following it.
    """
    if not req.filenames:
        raise HTTPException(status_code=400, detail="No filenames provided")

    folder = _safe_folder(req.folder)
    uploads = []
    for raw_name in req.filenames:
        filename = Path(raw_name).name  # strip any path component
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

    if not uploads:
        return {
            "uploads": [], "folder": folder,
            "job_id": None, "skipped": 0,
            "message": "No supported image files found",
        }

    # Dedupe — skip GCS paths that already have a prediction doc
    existing   = _existing_gcs_paths(uid)
    new_paths  = [u["gcs_path"] for u in uploads if u["gcs_path"] not in existing]
    skipped    = len(uploads) - len(new_paths)
    new_upload_set = set(new_paths)

    # Still need to return signed URLs for new files only — the browser
    # shouldn't bother re-uploading files we'll skip anyway.
    uploads = [u for u in uploads if u["gcs_path"] in new_upload_set]

    if not uploads:
        return {
            "uploads": [], "folder": folder,
            "job_id": None, "skipped": skipped,
            "message": f"All {skipped} image(s) already processed — nothing to do",
        }

    # ── Create job doc and fire run_job NOW, in parallel with uploads ────
    job_id = uuid.uuid4().hex[:8]
    now    = _now()
    job_doc = {
        "job_id":  job_id,
        "uid":     uid,
        "folder":  folder,
        "status":  "pending",
        "message": f"Queued — {len(new_paths)} new image(s)"
                   + (f", {skipped} skipped" if skipped else ""),
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

    jobs_client = run_v2.JobsClient()
    op = jobs_client.run_job(
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

    # Capture the Execution resource name so the watchdog (see
    # _reconcile_failed_execution) can ask Cloud Run whether a stale
    # "running" doc actually corresponds to a crashed container — covers
    # crashes that happen before job.py reaches its first set_status call.
    execution_name = ""
    try:
        if op.metadata is not None:
            execution_name = op.metadata.name or ""
    except Exception:
        pass

    # Move the job off "pending / Queued" right away so the polling UI sees a
    # new message instead of sitting silent during container cold-start. The
    # inference container will overwrite this as soon as main() starts.
    job_ref.update({
        "status":  "running",
        "message": "Loading AI model (can take up to a minute)…",
        "updated_at": _now(),
        "execution_name": execution_name,
    })

    return {
        "uploads":  uploads,
        "folder":   folder,
        "job_id":   job_id,
        "skipped":  skipped,
    }


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, uid: str = Depends(verify_token)):
    doc_ref = (
        _db.collection("users").document(uid)
        .collection("jobs").document(job_id)
    )
    snap = doc_ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Job not found")
    data = snap.to_dict()
    reconciled = _reconcile_failed_execution(doc_ref, data)
    return reconciled or data


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


# ── Execution watchdog ───────────────────────────────────────────────────────
#
# If the inference container crashes before reaching its first set_status()
# call (syntax error at import time, image pull failure, OOM during torch
# import, missing env var…), Cloud Run marks the execution Failed but the
# Firestore job doc stays on the "Loading AI model…" placeholder forever.
# On every poll of GET /api/jobs/{id} we ask Cloud Run whether the execution
# has finished, and flip status to "error" if it failed. Issue #25.

# Only consult Cloud Run if the doc hasn't been touched for this long. Cold
# start is 30–60s, so going below ~60s would just spend API calls during
# normal cold-starts. Setting it well under any realistic phase duration
# means a crash mid-cold-start is detected within ~30s of the container exit.
_WATCHDOG_STALENESS_S = 60

_executions_client: Optional[run_v2.ExecutionsClient] = None


def _get_executions_client() -> run_v2.ExecutionsClient:
    global _executions_client
    if _executions_client is None:
        _executions_client = run_v2.ExecutionsClient()
    return _executions_client


def _reconcile_failed_execution(doc_ref, data: dict) -> Optional[dict]:
    """If the doc claims `running` but Cloud Run reports the execution
    finished and failed, flip the doc to `error` and return the updated dict.
    Returns None when no change is needed."""
    if data.get("status") != "running":
        return None
    execution_name = data.get("execution_name")
    if not execution_name:
        return None

    raw = data.get("updated_at")
    try:
        updated_at = datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        updated_at = None
    if updated_at is None:
        return None
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - updated_at).total_seconds() < _WATCHDOG_STALENESS_S:
        return None

    try:
        execution = _get_executions_client().get_execution(name=execution_name)
    except Exception:
        return None

    # completion_time is a google.protobuf.Timestamp; unset → falsy seconds.
    if not execution.completion_time or not execution.completion_time.seconds:
        return None

    # Cloud Run sets succeeded_count > 0 only on a clean exit. Treat anything
    # else as a failure — the container exited without flipping the doc itself.
    if execution.succeeded_count and not execution.failed_count:
        return None

    update = {
        "status":       "error",
        "message":      "Inference container exited without reporting status — check Cloud Run logs.",
        "updated_at":   _now(),
        "completed_at": _now(),
    }
    doc_ref.update(update)
    return {**data, **update}


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


class DetectionBulkPatch(BaseModel):
    """Same partial update applied to every detection that matches
    category_filter (or every detection if the filter is None)."""
    category_filter: Optional[str] = None
    category:        Optional[str] = None
    label:           Optional[str] = None
    conf:            Optional[confloat(ge=0.0, le=1.0)] = None
    scientific:      Optional[str] = None

    def model_post_init(self, __context) -> None:
        for fld, val in (("category", self.category), ("category_filter", self.category_filter)):
            if val is not None and val not in VALID_CATEGORIES:
                raise ValueError(f"{fld} must be one of {sorted(VALID_CATEGORIES)}")


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


@app.patch("/api/predictions/detections/bulk")
async def patch_detections_bulk(
    body: DetectionBulkPatch,
    path: str = Query(..., description="GCS path of the image"),
    uid:  str = Depends(verify_token),
):
    """Apply the same partial update to many detections at once. Useful for
    re-labelling a flock of birds without clicking through each box.

    When the user gives the bulk a new species label, ALSO rewrites the
    image-level prediction so the gallery filter and SpeciesView (which
    both key off prediction.common_name) reflect the manual species too."""
    _ensure_path_owned(uid, path)
    doc_ref, _data, detections = _load_detections(uid, path)
    updated: list[dict] = []
    for det in detections:
        if body.category_filter and det.get("category") != body.category_filter:
            continue
        if body.category   is not None: det["category"]   = body.category
        if body.label      is not None: det["label"]      = body.label
        if body.conf       is not None: det["conf"]       = float(body.conf)
        if body.scientific is not None: det["scientific"] = body.scientific
        det["manual"] = True
        updated.append(det)

    new_prediction: Optional[dict] = None
    update_doc: dict = {}
    if updated:
        update_doc["detections"] = detections
        if body.label:
            new_prediction = _build_synthetic_prediction(body.label, body.scientific or "")
            update_doc["prediction"]        = new_prediction
            update_doc["prediction_source"] = "manual"
        doc_ref.update(update_doc)

    response: dict = {"updated": len(updated), "detections": updated}
    if new_prediction is not None:
        response["prediction"] = new_prediction
    return response


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


def _lookup_taxonomy_silent(name: str) -> Optional[dict]:
    """Like species_lookup but returns None on any failure. Shared with
    the bulk endpoint where a missing taxonomy shouldn't fail the whole edit."""
    if not name or not name.strip():
        return None
    key = name.strip().lower()
    if key in _GBIF_CACHE:
        return _GBIF_CACHE[key]
    try:
        url = "https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode({
            "name": name.strip(), "strict": "false",
        })
        req = urllib.request.Request(url, headers={"User-Agent": _HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = json.loads(resp.read())
    except Exception:
        return None
    if raw.get("matchType") == "NONE":
        return None
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


def _build_synthetic_prediction(common_name: str, scientific: str = "") -> dict:
    """Synthesise a parsed-prediction dict for a manual species edit.
    Matches the shape inference writes to Firestore — id/common_name/
    scientific/raw — so the frontend doesn't need to special-case manual
    vs. inferred predictions."""
    tax = _lookup_taxonomy_silent(scientific or common_name) or {}
    species_full = tax.get("species") or ""
    genus = tax.get("genus") or ""
    if species_full and genus and species_full.lower().startswith(genus.lower()):
        epithet = species_full[len(genus):].strip()
    elif species_full:
        epithet = species_full.split()[-1]
    else:
        epithet = ""
    raw = ";".join([
        "",
        (tax.get("class")  or "").lower(),
        (tax.get("order")  or "").lower(),
        (tax.get("family") or "").lower(),
        (tax.get("genus")  or "").lower(),
        epithet.lower(),
        common_name,
    ])
    return {
        "id":          "",
        "common_name": common_name,
        "scientific":  tax.get("scientific") or scientific or "",
        "raw":         raw,
    }


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
