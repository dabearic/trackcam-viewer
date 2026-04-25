import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

_EXIF_EXIF_IFD           = 0x8769
_EXIF_DATETIME_ORIGINAL  = 0x9003
_EXIF_DATETIME_DIGITIZED = 0x9004
_EXIF_DATETIME           = 0x0132


def _parse_exif_datetime(raw) -> Optional[str]:
    if not raw:
        return None
    try:
        s = raw.strip() if isinstance(raw, str) else str(raw).strip()
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        return None


def _extract_taken_at(path: str) -> Optional[str]:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            try:
                sub = exif.get_ifd(_EXIF_EXIF_IFD)
            except Exception:
                sub = {}
            for tag in (_EXIF_DATETIME_ORIGINAL, _EXIF_DATETIME_DIGITIZED):
                parsed = _parse_exif_datetime(sub.get(tag))
                if parsed:
                    return parsed
            return _parse_exif_datetime(exif.get(_EXIF_DATETIME))
    except Exception:
        return None

# Regex that matches ANSI escape sequences (colors, cursor moves, etc.)
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\r')

# Matches tqdm progress lines e.g. "Detector preprocess   :  45%|████| 11/24 [00:03<00:04]"
_TQDM_RE = re.compile(r'^(.+?)\s*:\s*(\d+)%\|[^|]*\|\s*(\d+)/(\d+)')

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, conlist, confloat
import uvicorn

app = FastAPI(title="TrailCam Viewer API")

PREDICTIONS_FILE = os.environ.get(
    "PREDICTIONS_FILE",
    r"C:\Users\dabea\Downloads\Photos-3-001\predictions.json",
)

# Sibling file holding user-added species (taxonomy entries that don't appear
# in any inference output yet). Loaded by /api/species-custom and merged into
# the frontend species tree.
SPECIES_CUSTOM_FILE = os.environ.get(
    "SPECIES_CUSTOM_FILE",
    str(Path(PREDICTIONS_FILE).parent / "species_custom.json"),
)

# Python interpreter used to invoke SpeciesNet.
# Override with PYTHON_EXECUTABLE env var, otherwise auto-detect by finding
# an interpreter that can import speciesnet, then fall back to sys.executable.
def _find_python() -> str:
    if "PYTHON_EXECUTABLE" in os.environ:
        return os.environ["PYTHON_EXECUTABLE"]

    # Common conda/venv locations to probe, in priority order
    home = Path.home()
    candidates = [
        # conda envs named 'speciesnet'
        home / "miniforge3"  / "envs" / "speciesnet" / "python.exe",
        home / "miniconda3"  / "envs" / "speciesnet" / "python.exe",
        home / "anaconda3"   / "envs" / "speciesnet" / "python.exe",
        home / "miniforge3"  / "envs" / "speciesnet" / "bin" / "python",
        home / "miniconda3"  / "envs" / "speciesnet" / "bin" / "python",
        home / "anaconda3"   / "envs" / "speciesnet" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    # Last resort: current interpreter (works if backend is launched from the
    # speciesnet env)
    return sys.executable

PYTHON_EXECUTABLE = _find_python()
print(f"[TrailCam] Using Python for SpeciesNet: {PYTHON_EXECUTABLE}")

# In-memory job store (sufficient for a single-user local tool)
_jobs: dict = {}


# ---------------------------------------------------------------------------
# Label parsing
# ---------------------------------------------------------------------------

def parse_label(label_str: str) -> dict:
    """Parse 'uuid;class;order;family;genus;species;common_name' into a dict."""
    parts = label_str.split(";")
    common_name = parts[-1] if parts else label_str
    scientific = ""
    if len(parts) >= 6 and parts[4] and parts[5]:
        scientific = f"{parts[4].capitalize()} {parts[5]}"
    elif len(parts) >= 2 and parts[1]:
        scientific = parts[1].capitalize()
    return {
        "id": parts[0],
        "common_name": common_name,
        "scientific": scientific,
        "raw": label_str,
    }


# ---------------------------------------------------------------------------
# Detection schema + raw predictions.json helpers
# ---------------------------------------------------------------------------

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


def _load_raw_predictions() -> dict:
    """Read predictions.json and backfill missing detection IDs in place.

    If any IDs were added, the file is rewritten so IDs are stable across
    sessions. Returns the parsed dict (with `predictions` key).
    """
    if not os.path.isfile(PREDICTIONS_FILE):
        return {"predictions": []}
    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    mutated = False
    for pred in data.get("predictions", []):
        for det in pred.get("detections", []) or []:
            if "id" not in det:
                det["id"] = uuid.uuid4().hex
                mutated = True

    if mutated:
        _save_raw_predictions(data)
    return data


def _save_raw_predictions(data: dict) -> None:
    """Atomic write to PREDICTIONS_FILE via temp file + os.replace."""
    target_dir = os.path.dirname(PREDICTIONS_FILE) or "."
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, PREDICTIONS_FILE)
    except Exception:
        if os.path.isfile(tmp):
            try: os.unlink(tmp)
            except OSError: pass
        raise


def _find_prediction(data: dict, path: str) -> Optional[dict]:
    """Locate a prediction entry by filepath (normalised compare)."""
    target = _norm_path(path)
    for p in data.get("predictions", []):
        if _norm_path(p.get("filepath", "")) == target:
            return p
    return None


def load_predictions() -> list:
    data = _load_raw_predictions()

    result = []
    for pred in data["predictions"]:
        filepath = pred["filepath"]
        filename = Path(filepath).name

        prediction_label = None
        if "prediction" in pred:
            prediction_label = parse_label(pred["prediction"])

        top5 = []
        if "classifications" in pred:
            for cls, score in zip(
                pred["classifications"]["classes"],
                pred["classifications"]["scores"],
            ):
                top5.append({**parse_label(cls), "score": round(score, 4)})

        result.append({
            "filepath": filepath,
            "filename": filename,
            "taken_at": _extract_taken_at(filepath),
            "prediction": prediction_label,
            "prediction_score": pred.get("prediction_score"),
            "prediction_source": pred.get("prediction_source"),
            "top5": top5,
            "detections": pred.get("detections", []),
            "model_version": pred.get("model_version"),
            "failures": pred.get("failures", []),
            "country": pred.get("country"),
            "latitude": pred.get("latitude"),
            "longitude": pred.get("longitude"),
        })

    return result


# ---------------------------------------------------------------------------
# Predictions merge
# ---------------------------------------------------------------------------

def _merge_predictions(main_file: str, new_file: str) -> int:
    """Merge new_file into main_file. Returns count of new/updated predictions."""
    main_data: dict = {"predictions": []}
    if os.path.isfile(main_file):
        with open(main_file, encoding="utf-8") as f:
            main_data = json.load(f)

    with open(new_file, encoding="utf-8") as f:
        new_data = json.load(f)

    idx = {p["filepath"]: i for i, p in enumerate(main_data["predictions"])}
    count = 0
    for pred in new_data["predictions"]:
        fp = pred["filepath"]
        if fp in idx:
            main_data["predictions"][idx[fp]] = pred
        else:
            main_data["predictions"].append(pred)
        count += 1

    with open(main_file, "w", encoding="utf-8") as f:
        json.dump(main_data, f, indent=1)

    return count


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}


def _norm_path(path: str) -> str:
    """Normalise a filepath for dedup comparison (forward slashes, lowercase)."""
    return path.replace("\\", "/").lower()


def _existing_filepaths() -> set:
    """Return the set of normalised filepaths already in PREDICTIONS_FILE."""
    if not os.path.isfile(PREDICTIONS_FILE):
        return set()
    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {_norm_path(p["filepath"]) for p in data.get("predictions", [])}


def _set_job(job_id: str, status: str, message: str):
    _jobs[job_id]["status"] = status
    _jobs[job_id]["message"] = message


def _run_job(job_id: str, folder: str, country: Optional[str],
             admin1_region: Optional[str],
             latitude: Optional[float], longitude: Optional[float]):
    tmp_path = None
    instances_json_path = None
    try:
        # --- Deduplication: skip images already in PREDICTIONS_FILE ----------
        _set_job(job_id, "running", "Checking for already-processed images…")
        all_files = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.suffix.lower() in IMAGE_EXTS
        )
        existing = _existing_filepaths()
        new_files = [f for f in all_files if _norm_path(f) not in existing]
        skipped = len(all_files) - len(new_files)

        if not new_files:
            _set_job(job_id, "done",
                     f"Done — all {len(all_files)} image(s) already processed, nothing to do")
            return

        if skipped:
            _set_job(job_id, "running",
                     f"Found {len(new_files)} new image(s), skipping {skipped} already processed…")

        # --- Build instances JSON (always; handles location + dedup cleanly) --
        instances = []
        for fp in new_files:
            inst: dict = {"filepath": fp.replace("\\", "/")}
            if country:
                inst["country"] = country
            if admin1_region:
                inst["admin1_region"] = admin1_region
            if latitude is not None:
                inst["latitude"] = latitude
            if longitude is not None:
                inst["longitude"] = longitude
            instances.append(inst)

        fd2, instances_json_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd2, "w") as f:
            json.dump({"instances": instances}, f)

        # Write SpeciesNet output to a temp file so the main predictions.json
        # is only touched once, atomically, after a successful run.
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(tmp_path)  # SpeciesNet must create this itself; an empty file causes a JSON parse error

        cmd = [
            PYTHON_EXECUTABLE, "-u", "-m", "speciesnet.scripts.run_model",
            "--instances_json", instances_json_path,
            "--predictions_json", tmp_path,
            "--bypass_prompts",
        ]

        _set_job(job_id, "running", "Running SpeciesNet inference…")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
        )

        log: list[str] = []
        for line in process.stdout:
            line = _ANSI_ESCAPE.sub('', line).rstrip()
            if not line:
                continue
            m = _TQDM_RE.match(line)
            if m:
                # Progress bar line — update structured progress, skip the log
                label = m.group(1).strip()
                _jobs[job_id]["progress"][label] = {
                    "percent": int(m.group(2)),
                    "current": int(m.group(3)),
                    "total":   int(m.group(4)),
                }
            else:
                log.append(line)
                _jobs[job_id]["log"] = log[-50:]
                _jobs[job_id]["message"] = line

        process.wait()

        if process.returncode != 0:
            _set_job(job_id, "error",
                     f"SpeciesNet exited with code {process.returncode}")
            return

        _set_job(job_id, "running", "Merging predictions into dataset…")
        count = _merge_predictions(PREDICTIONS_FILE, tmp_path)
        _set_job(job_id, "done", f"Done — {count} prediction(s) added/updated")

    except Exception as exc:
        _set_job(job_id, "error", str(exc))

    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)
        if instances_json_path and os.path.isfile(instances_json_path):
            os.unlink(instances_json_path)


# ---------------------------------------------------------------------------
# API routes — predictions & images
# ---------------------------------------------------------------------------

@app.get("/api/predictions")
def get_predictions():
    return {"predictions": load_predictions()}


@app.get("/api/image")
def get_image(path: str = Query(...)):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg")


def _preview_path_for(path: str) -> str:
    """Path where SpeciesNet's visualiser writes the annotated copy of `path`."""
    preview_dir = str(Path(path).parent / "previews")
    encoded = path.replace(":", "~").replace("/", "~").replace("\\", "~")
    return os.path.join(preview_dir, f"anno_{encoded}")


@app.delete("/api/predictions")
def delete_prediction(path: str = Query(..., description="Filepath of the image to delete")):
    """Remove an image from predictions.json and delete its file + preview from disk."""
    if not os.path.isfile(PREDICTIONS_FILE):
        raise HTTPException(status_code=404, detail="Predictions file not found")

    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    target = _norm_path(path)
    kept, removed = [], []
    for p in data.get("predictions", []):
        if _norm_path(p.get("filepath", "")) == target:
            removed.append(p)
        else:
            kept.append(p)

    if not removed:
        raise HTTPException(status_code=404, detail="No prediction found for that path")

    data["predictions"] = kept
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)

    # Only delete disk files that were actually listed in predictions.json
    for fp in (removed[0]["filepath"], _preview_path_for(removed[0]["filepath"])):
        try:
            if os.path.isfile(fp):
                os.unlink(fp)
        except OSError:
            pass

    return {"deleted": True, "path": path, "removed_entries": len(removed)}


# ---------------------------------------------------------------------------
# API routes — per-detection edits
# ---------------------------------------------------------------------------
#
# Detections are addressed by the parent image's filepath plus the detection's
# stable UUID `id` (backfilled by _load_raw_predictions on first read). Every
# mutation reads the raw file, edits one detection, and atomically rewrites the
# whole file via _save_raw_predictions. Single-user assumption — see issue #13
# for concurrent-edit considerations.

def _require_detection(path: str, det_id: str) -> tuple[dict, dict, dict]:
    """Load raw data + locate prediction + locate detection. 404 on miss."""
    data = _load_raw_predictions()
    pred = _find_prediction(data, path)
    if pred is None:
        raise HTTPException(status_code=404, detail="No prediction for that path")
    for det in pred.get("detections", []) or []:
        if det.get("id") == det_id:
            return data, pred, det
    raise HTTPException(status_code=404, detail="Detection not found")


@app.delete("/api/predictions/detections")
def delete_detection(
    path: str = Query(..., description="Image filepath"),
    id:   str = Query(..., description="Detection id"),
):
    data, pred, _ = _require_detection(path, id)
    pred["detections"] = [d for d in pred["detections"] if d.get("id") != id]
    _save_raw_predictions(data)
    return {"deleted": True, "id": id}


@app.patch("/api/predictions/detections")
def patch_detection(
    patch: DetectionPatch,
    path:  str = Query(...),
    id:    str = Query(...),
):
    """Update category, label/species, and/or confidence on an existing
    detection. Marks the detection as `manual: true` since a human touched it.
    Bbox is intentionally not editable here — to move a box, delete + redraw."""
    data, _pred, det = _require_detection(path, id)
    if patch.category is not None: det["category"]   = patch.category
    if patch.label    is not None: det["label"]      = patch.label
    if patch.conf     is not None: det["conf"]       = float(patch.conf)
    if patch.scientific is not None: det["scientific"] = patch.scientific
    det["manual"] = True
    _save_raw_predictions(data)
    return {"updated": True, "detection": det}


@app.post("/api/predictions/detections", status_code=201)
def add_detection(
    body: DetectionCreate,
    path: str = Query(..., description="Image filepath"),
):
    """Create a new manual detection on an image. Server assigns the id and
    sets `manual: true`."""
    data = _load_raw_predictions()
    pred = _find_prediction(data, path)
    if pred is None:
        raise HTTPException(status_code=404, detail="No prediction for that path")
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
    pred.setdefault("detections", []).append(det)
    _save_raw_predictions(data)
    return {"created": True, "detection": det}


# ---------------------------------------------------------------------------
# API routes — custom (user-added) species
# ---------------------------------------------------------------------------

class CustomSpecies(BaseModel):
    common_name: str
    scientific:  Optional[str] = None
    parent:      Optional[str] = None  # optional taxonomy hint, e.g. "mammalia;carnivora;felidae"


def _load_custom_species() -> list:
    if not os.path.isfile(SPECIES_CUSTOM_FILE):
        return []
    try:
        with open(SPECIES_CUSTOM_FILE, encoding="utf-8") as f:
            return json.load(f).get("species", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_custom_species(species: list) -> None:
    target_dir = os.path.dirname(SPECIES_CUSTOM_FILE) or "."
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"species": species}, f, indent=1)
        os.replace(tmp, SPECIES_CUSTOM_FILE)
    except Exception:
        if os.path.isfile(tmp):
            try: os.unlink(tmp)
            except OSError: pass
        raise


@app.get("/api/species-custom")
def get_custom_species():
    return {"species": _load_custom_species()}


@app.post("/api/species-custom", status_code=201)
def add_custom_species(body: CustomSpecies):
    species = _load_custom_species()
    # De-dup by common_name (case-insensitive). If it already exists, return it.
    key = body.common_name.strip().lower()
    for s in species:
        if s.get("common_name", "").strip().lower() == key:
            return {"created": False, "species": s}
    entry = {
        "id":          uuid.uuid4().hex,
        "common_name": body.common_name.strip(),
        "scientific":  (body.scientific or "").strip(),
        "parent":      (body.parent or "").strip(),
    }
    species.append(entry)
    _save_custom_species(species)
    return {"created": True, "species": entry}


# ---------------------------------------------------------------------------
# API routes — processing jobs
# ---------------------------------------------------------------------------

class ProcessRequest(BaseModel):
    folder: str
    country: Optional[str] = None
    admin1_region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@app.get("/api/browse-folder")
def browse_folder():
    """Open a native folder-picker dialog and return the selected path."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select image folder")
    root.destroy()
    return {"folder": folder or None}


@app.post("/api/process", status_code=202)
def start_process(req: ProcessRequest):
    if not os.path.isdir(req.folder):
        raise HTTPException(status_code=400,
                            detail=f"Folder not found: {req.folder}")

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {"status": "running", "message": "Queued", "log": [], "progress": {}}

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, req.folder, req.country, req.admin1_region,
              req.latitude, req.longitude),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/api/jobs")
def list_jobs():
    # Return all jobs, truncating the log to last 3 lines for brevity
    return {
        jid: {**info, "log": info.get("log", [])[-3:]}
        for jid, info in _jobs.items()
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
