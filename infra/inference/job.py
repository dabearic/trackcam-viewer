"""
TrackCam SpeciesNet inference — Cloud Run Job entrypoint.

Required env vars:
  JOB_ID      — Firestore job document ID
  USER_ID     — Firebase UID of the requesting user
  GCS_BUCKET  — GCS bucket name
  GCP_PROJECT — GCP project ID
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import firestore, storage
from PIL import Image

CROP_CONF_THRESHOLD = 0.2
CROP_MAX_DIM        = 512
CROP_JPEG_QUALITY   = 85

_EXIF_EXIF_IFD           = 0x8769
_EXIF_DATETIME_ORIGINAL  = 0x9003
_EXIF_DATETIME_DIGITIZED = 0x9004
_EXIF_DATETIME           = 0x0132


def _parse_exif_datetime(raw) -> str | None:
    """Parse EXIF datetime string ('YYYY:MM:DD HH:MM:SS') to naive ISO."""
    if not raw:
        return None
    try:
        s = raw.strip() if isinstance(raw, str) else str(raw).strip()
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        return None


def _extract_taken_at(path: str) -> str | None:
    """Return naive-ISO datetime from EXIF DateTimeOriginal, or None."""
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

# ── ANSI / tqdm helpers (same as local backend) ───────────────────────────────
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\r')
_TQDM_RE = re.compile(r'^(.+?)\s*:\s*(\d+)%\|[^|]*\|\s*(\d+)/(\d+)')


def _save_crop(image: Image.Image, bbox: list, dest_path: str) -> None:
    """Crop `bbox` (normalised [x, y, w, h]) from `image` and save JPEG to `dest_path`."""
    w, h = image.size
    bx, by, bw, bh = bbox
    x0 = max(0, int(bx * w))
    y0 = max(0, int(by * h))
    x1 = min(w, int((bx + bw) * w))
    y1 = min(h, int((by + bh) * h))
    if x1 <= x0 or y1 <= y0:
        return
    crop = image.crop((x0, y0, x1, y1))
    cw, ch = crop.size
    scale = min(1.0, CROP_MAX_DIM / max(cw, ch))
    if scale < 1.0:
        crop = crop.resize((int(cw * scale), int(ch * scale)), Image.LANCZOS)
    if crop.mode != "RGB":
        crop = crop.convert("RGB")
    crop.save(dest_path, "JPEG", quality=CROP_JPEG_QUALITY, optimize=True)


def _parse_label(label_str: str) -> dict:
    parts = label_str.split(";")
    common_name = parts[-1] if parts else label_str
    scientific = ""
    if len(parts) >= 6 and parts[4] and parts[5]:
        scientific = f"{parts[4].capitalize()} {parts[5]}"
    elif len(parts) >= 2 and parts[1]:
        scientific = parts[1].capitalize()
    return {"id": parts[0], "common_name": common_name, "scientific": scientific, "raw": label_str}


def main():
    job_id   = os.environ["JOB_ID"]
    uid      = os.environ["USER_ID"]
    bucket_name = os.environ["GCS_BUCKET"]
    project  = os.environ["GCP_PROJECT"]

    db  = firestore.Client(project=project)
    gcs = storage.Client(project=project)
    bucket = gcs.bucket(bucket_name)

    job_ref  = db.collection("users").document(uid).collection("jobs").document(job_id)
    pred_col = db.collection("users").document(uid).collection("predictions")

    def set_status(status: str, message: str, extra: dict | None = None):
        update = {"status": status, "message": message, "updated_at": _now()}
        if extra:
            update.update(extra)
        job_ref.update(update)
        print(f"[{status}] {message}")

    # First thing: confirm the container is alive so the UI stops showing
    # the cold-start placeholder set by the web backend.
    set_status("running", "Container started — reading job config…")

    # ── Read job document ─────────────────────────────────────────────────────
    job_doc = job_ref.get().to_dict()
    files   = job_doc["files"]           # list of GCS object paths
    params  = job_doc.get("params", {})
    country       = params.get("country")
    admin1_region = params.get("admin1_region")
    latitude      = params.get("latitude")
    longitude     = params.get("longitude")

    set_status("running", f"Downloading {len(files)} image(s) from storage…")

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── Download images from GCS ──────────────────────────────────────────
        local_paths = []
        path_map: dict[str, str] = {}  # local_path -> gcs_path

        for i, gcs_path in enumerate(files):
            filename   = Path(gcs_path).name
            local_path = os.path.join(tmpdir, filename)
            bucket.blob(gcs_path).download_to_filename(local_path)
            local_paths.append(local_path)
            path_map[local_path] = gcs_path
            if (i + 1) % 20 == 0 or (i + 1) == len(files):
                set_status("running", f"Downloaded {i+1}/{len(files)} images…")

        # ── Build instances JSON ──────────────────────────────────────────────
        instances = []
        for local_path in local_paths:
            inst: dict = {"filepath": local_path}
            if country:
                inst["country"] = country
            if admin1_region:
                inst["admin1_region"] = admin1_region
            if latitude is not None:
                inst["latitude"] = latitude
            if longitude is not None:
                inst["longitude"] = longitude
            instances.append(inst)

        instances_file  = os.path.join(tmpdir, "instances.json")
        predictions_file = os.path.join(tmpdir, "predictions.json")

        with open(instances_file, "w") as f:
            json.dump({"instances": instances}, f)

        set_status("running", "Running SpeciesNet inference…")

        # ── Run SpeciesNet ────────────────────────────────────────────────────
        cmd = [
            "python", "-u", "-m", "speciesnet.scripts.run_model",
            "--instances_json", instances_file,
            "--predictions_json", predictions_file,
            "--bypass_prompts",
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        log: list[str] = []
        progress: dict = {}

        for line in process.stdout:
            line = _ANSI_ESCAPE.sub("", line).rstrip()
            if not line:
                continue
            m = _TQDM_RE.match(line)
            if m:
                label = m.group(1).strip()
                progress[label] = {
                    "percent": int(m.group(2)),
                    "current": int(m.group(3)),
                    "total":   int(m.group(4)),
                }
                job_ref.update({"progress": progress, "updated_at": _now()})
            else:
                log.append(line)
                job_ref.update({"message": line, "log": log[-50:], "updated_at": _now()})

        process.wait()

        if process.returncode != 0:
            set_status("error", f"SpeciesNet exited with code {process.returncode}")
            raise SystemExit(1)

        # ── Write predictions to Firestore ────────────────────────────────────
        set_status("running", "Saving predictions to database…")

        with open(predictions_file, encoding="utf-8") as f:
            output = json.load(f)

        batch = db.batch()
        batch_count = 0
        count = 0
        now = _now()
        folder = job_doc.get("folder", "")

        for pred in output.get("predictions", []):
            local_fp = pred["filepath"]
            gcs_path = path_map.get(local_fp, local_fp)
            filename = Path(gcs_path).name

            doc_id = hashlib.md5(gcs_path.encode()).hexdigest()

            prediction_label = None
            if "prediction" in pred:
                prediction_label = _parse_label(pred["prediction"])

            top5 = []
            if "classifications" in pred:
                for cls, score in zip(
                    pred["classifications"]["classes"],
                    pred["classifications"]["scores"],
                ):
                    top5.append({**_parse_label(cls), "score": round(score, 4)})

            detections = pred.get("detections", [])
            source_image = None
            for idx, det in enumerate(detections):
                if det.get("conf", 0) < CROP_CONF_THRESHOLD or not det.get("bbox"):
                    continue
                if source_image is None:
                    try:
                        source_image = Image.open(local_fp)
                    except Exception as exc:
                        log.append(f"crop: could not open {local_fp}: {exc}")
                        break
                stem = Path(filename).stem
                crop_filename = f"{stem}_detection_{idx + 1}.jpg"
                crop_local = os.path.join(tmpdir, crop_filename)
                try:
                    _save_crop(source_image, det["bbox"], crop_local)
                except Exception as exc:
                    log.append(f"crop: failed for {filename} det {idx}: {exc}")
                    continue
                crop_gcs_path = f"crops/{uid}/{folder}/{crop_filename}"
                bucket.blob(crop_gcs_path).upload_from_filename(
                    crop_local, content_type="image/jpeg"
                )
                det["crop_gcs_path"] = crop_gcs_path
            if source_image is not None:
                source_image.close()

            doc = {
                "gcs_path":          gcs_path,
                "filename":          filename,
                "folder":            folder,
                "uid":               uid,
                "taken_at":          _extract_taken_at(local_fp),
                "prediction":        prediction_label,
                "prediction_score":  pred.get("prediction_score"),
                "prediction_source": pred.get("prediction_source"),
                "top5":              top5,
                "detections":        detections,
                "model_version":     pred.get("model_version"),
                "failures":          pred.get("failures", []),
                "country":           pred.get("country"),
                "latitude":          pred.get("latitude"),
                "longitude":         pred.get("longitude"),
                "job_id":            job_id,
                "created_at":        now,
                "updated_at":        now,
            }

            batch.set(pred_col.document(doc_id), doc, merge=True)
            batch_count += 1
            count += 1

            if batch_count >= 400:   # Firestore batch limit is 500
                batch.commit()
                batch = db.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()

        set_status("done", f"Done — {count} prediction(s) saved",
                   {"completed_at": now})
        print(f"[done] Saved {count} predictions for user {uid}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
