import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional

# Regex that matches ANSI escape sequences (colors, cursor moves, etc.)
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\r')

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="TrailCam Viewer API")

PREDICTIONS_FILE = os.environ.get(
    "PREDICTIONS_FILE",
    r"C:\Users\dabea\Downloads\Photos-3-001\predictions.json",
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


def load_predictions() -> list:
    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)

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

def _set_job(job_id: str, status: str, message: str):
    _jobs[job_id]["status"] = status
    _jobs[job_id]["message"] = message


def _run_job(job_id: str, folder: str, country: Optional[str],
             admin1_region: Optional[str],
             latitude: Optional[float], longitude: Optional[float]):
    tmp_path = None
    instances_json_path = None
    try:
        # Write SpeciesNet output to a temp file so the main predictions.json
        # is only touched once, atomically, after a successful run.
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(tmp_path)  # SpeciesNet must create this itself; an empty file causes a JSON parse error

        if latitude is not None or longitude is not None:
            # SpeciesNet has no --latitude/--longitude CLI flags.
            # Per-image location must be supplied via --instances_json.
            IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
            filepaths = sorted(
                str(p) for p in Path(folder).iterdir()
                if p.suffix.lower() in IMAGE_EXTS
            )
            instances = []
            for fp in filepaths:
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
            cmd = [
                PYTHON_EXECUTABLE, "-u", "-m", "speciesnet.scripts.run_model",
                "--instances_json", instances_json_path,
                "--predictions_json", tmp_path,
                "--bypass_prompts",
            ]
        else:
            cmd = [
                PYTHON_EXECUTABLE, "-u", "-m", "speciesnet.scripts.run_model",
                "--folders", folder,
                "--predictions_json", tmp_path,
                "--bypass_prompts",
            ]
            if country:
                cmd += ["--country", country]
            if admin1_region:
                cmd += ["--admin1_region", admin1_region]

        _set_job(job_id, "running", "Running SpeciesNet inference…")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        log: list[str] = []
        for line in process.stdout:
            line = _ANSI_ESCAPE.sub('', line).rstrip()
            if line:
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


@app.get("/api/preview")
def get_preview(path: str = Query(...)):
    preview_dir = str(Path(path).parent / "previews")
    encoded = path.replace(":", "~").replace("/", "~").replace("\\", "~")
    preview_path = os.path.join(preview_dir, f"anno_{encoded}")
    if not os.path.isfile(preview_path):
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path, media_type="image/jpeg")


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
    _jobs[job_id] = {"status": "running", "message": "Queued", "log": []}

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
