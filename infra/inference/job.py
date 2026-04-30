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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import firestore, storage
from PIL import Image, ImageOps

CROP_CONF_THRESHOLD = 0.2
CROP_MAX_DIM        = 512
CROP_JPEG_QUALITY   = 85

# GCS round-trip latency (~50-200ms per blob) dominates large-batch wall
# time — sequential I/O made a 513-image run take ~14 minutes on top of
# inference. 16 workers cuts that to single-digit minutes without
# pressuring the per-instance memory budget.
DOWNLOAD_WORKERS = 16
UPLOAD_WORKERS   = 16

# Crop generation = (Image.open + exif_transpose + crop + JPEG encode)
# per source image. PIL's libjpeg / libpng C calls release the GIL, so
# threads do give real parallelism here. A single-threaded loop on a
# 200-image / 200-crop batch was running ~30s; pooling matches the
# download/upload pattern above. The same pool also handles the per-
# prediction crop+upload+firestore work in streaming mode (see below).
CROP_WORKERS = 16

# Streaming mode: the inference image patches speciesnet's hardcoded
# 600s "save partial results" interval down to 5s (see Dockerfile.inference).
# That means predictions.json gets atomically rewritten ~every 5s during
# inference. We poll it on a slightly faster cadence so a save we missed
# at 5.1s lands within ~2s, and dispatch newly-arrived predictions to a
# worker pool for crop+upload+firestore — so the upload dialog can show
# thumbnails as classifications complete instead of waiting for the
# whole inference run.
PREDICTIONS_POLL_S = 2

# The web backend fires run_job at upload-prepare time, so the container
# often starts cold-starting BEFORE the browser has finished PUT-ing all
# files to GCS. Each download worker polls for its assigned blob, then
# downloads as soon as it appears — pipelining the wait and the download
# so by the time the last upload arrives, earlier files are already on
# disk. The timeout below is per-file, not per-job: a single file that
# never arrives fails the job after this much wall time.
UPLOAD_WAIT_TIMEOUT_S = 900   # 15 min — well above any realistic upload
UPLOAD_WAIT_POLL_S    = 3

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

    # First thing: confirm the worker is alive so the UI stops showing
    # the cold-start placeholder set by the web backend.
    set_status("running", "AI model ready — reading job config…")

    # ── Read job document ─────────────────────────────────────────────────────
    job_doc = job_ref.get().to_dict()
    files   = job_doc["files"]           # list of GCS object paths
    params  = job_doc.get("params", {})
    country       = params.get("country")
    admin1_region = params.get("admin1_region")
    latitude      = params.get("latitude")
    longitude     = params.get("longitude")

    set_status("running", f"Fetching {len(files)} image(s) from storage…")

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── Wait + download in a single pipelined phase ───────────────────
        # The backend often fires run_job before the browser has finished
        # PUT-ing every file. Previously we waited for every blob to exist
        # and only then started parallel downloads — that left ~10s of
        # serialized download work running AFTER the last upload landed.
        # Now each worker polls for its assigned blob and downloads as
        # soon as it appears, so by the time the last upload arrives the
        # earlier files are already on disk. For already-uploaded jobs
        # each worker probes once and proceeds straight to download
        # (one HEAD per file vs the old N-HEADs-per-poll-cycle approach).
        local_paths: list[str] = []
        path_map: dict[str, str] = {}  # local_path -> gcs_path

        def _wait_and_download_one(gcs_path: str) -> tuple[str, str]:
            blob = bucket.blob(gcs_path)
            start = time.time()
            while not blob.exists():
                if time.time() - start > UPLOAD_WAIT_TIMEOUT_S:
                    raise TimeoutError(
                        f"Upload never arrived after {UPLOAD_WAIT_TIMEOUT_S}s: {gcs_path}"
                    )
                time.sleep(UPLOAD_WAIT_POLL_S)
            local_path = os.path.join(tmpdir, Path(gcs_path).name)
            blob.download_to_filename(local_path)
            return gcs_path, local_path

        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as ex:
            futures = [ex.submit(_wait_and_download_one, f) for f in files]
            done = 0
            try:
                for fut in as_completed(futures):
                    gcs_path, local_path = fut.result()
                    local_paths.append(local_path)
                    path_map[local_path] = gcs_path
                    done += 1
                    if done % 20 == 0 or done == len(files):
                        set_status("running", f"Fetched {done}/{len(files)} images…")
            except TimeoutError as exc:
                set_status("error", str(exc))
                raise SystemExit(1)

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

        folder = job_doc.get("folder", "")
        log: list[str] = []
        progress: dict = {}

        # ── Streaming-prediction state ────────────────────────────────────
        # Workers running in `worker_pool` consume new predictions as
        # speciesnet writes them and produce: (a) crop file + GCS upload,
        # (b) a per-prediction Firestore doc with crop_gcs_path filled in,
        # and (c) summary aggregates. The watcher thread polls
        # predictions.json every PREDICTIONS_POLL_S seconds and dispatches
        # any prediction whose filepath we haven't seen yet.
        processed_filepaths: set[str] = set()
        processed_lock = threading.Lock()
        summary_lock   = threading.Lock()
        by_species:     dict[str, int] = {}
        by_category:    dict[str, int] = {}
        summary_images: list[dict] = []
        count_lock = threading.Lock()
        count = 0

        def _generate_crops_for_pred(pred: dict) -> list[tuple[str, str, dict]]:
            """Open the source image once, emit one crop file per qualifying
            detection. Avoids re-decoding the same JPEG per detection."""
            local_fp = pred["filepath"]
            gcs_path = path_map.get(local_fp, local_fp)
            filename = Path(gcs_path).name
            valid = [
                (idx, det) for idx, det in enumerate(pred.get("detections", []))
                if det.get("conf", 0) >= CROP_CONF_THRESHOLD and det.get("bbox")
            ]
            if not valid:
                return []
            try:
                # Apply EXIF orientation so portrait-mode photos crop
                # in the orientation the browser displays them in.
                with Image.open(local_fp) as raw:
                    source_image = ImageOps.exif_transpose(raw)
            except Exception as exc:
                log.append(f"crop: could not open {local_fp}: {exc}")
                return []
            results: list[tuple[str, str, dict]] = []
            try:
                stem = Path(filename).stem
                for idx, det in valid:
                    crop_filename = f"{stem}_detection_{idx + 1}.jpg"
                    crop_local = os.path.join(tmpdir, crop_filename)
                    try:
                        _save_crop(source_image, det["bbox"], crop_local)
                    except Exception as exc:
                        log.append(f"crop: failed for {filename} det {idx}: {exc}")
                        continue
                    crop_gcs_path = f"crops/{uid}/{folder}/{crop_filename}"
                    results.append((crop_local, crop_gcs_path, det))
            finally:
                source_image.close()
            return results

        def _process_one_prediction(pred: dict) -> None:
            """End-to-end work for a single prediction: crops, uploads,
            Firestore doc, summary. Called from worker_pool."""
            nonlocal count
            local_fp = pred["filepath"]
            gcs_path = path_map.get(local_fp, local_fp)
            filename = Path(gcs_path).name

            # Crops + uploads. Each crop is independent; failures log and
            # continue rather than failing the whole prediction.
            for local, remote, det in _generate_crops_for_pred(pred):
                try:
                    bucket.blob(remote).upload_from_filename(
                        local, content_type="image/jpeg"
                    )
                    det["crop_gcs_path"] = remote
                except Exception as exc:
                    log.append(f"upload: failed for {remote}: {exc}")

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

            now_iso = _now()
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
                "detections":        pred.get("detections", []),
                "model_version":     pred.get("model_version"),
                "failures":          pred.get("failures", []),
                "country":           pred.get("country"),
                "latitude":          pred.get("latitude"),
                "longitude":         pred.get("longitude"),
                "job_id":            job_id,
                "created_at":        now_iso,
                "updated_at":        now_iso,
            }
            doc_id = hashlib.md5(gcs_path.encode()).hexdigest()
            # Per-doc set instead of batched commit: each one needs to land
            # in Firestore as soon as it's ready so the upload-dialog UI
            # can render the thumbnail. ~3 writes/sec is well under the
            # per-collection write-rate guideline.
            pred_col.document(doc_id).set(doc, merge=True)

            common = prediction_label["common_name"] if prediction_label else None
            category = None
            if common:
                low = common.lower()
                category = low if low in {"blank", "human", "vehicle"} else "animal"

            with summary_lock:
                if common:
                    by_species[common] = by_species.get(common, 0) + 1
                    by_category[category] = by_category.get(category, 0) + 1
                summary_images.append({
                    "filename":    filename,
                    "common_name": common,
                    "score":       round(pred.get("prediction_score") or 0, 3),
                    "category":    category,
                })

            # Surface a "latest qualifying crop" pointer on the job doc so
            # the upload-dialog UI can render a live thumbnail of the most-
            # recently-classified animal without subscribing to Firestore
            # or running a separate query (the doc is already polled every
            # 2s for status). Concurrent updates from multiple workers are
            # last-writer-wins, which is exactly the desired semantics:
            # whichever prediction completed most recently wins the slot.
            score = pred.get("prediction_score") or 0
            if category == "animal" and score >= 0.5:
                best_crop = max(
                    (d for d in pred.get("detections", []) if d.get("crop_gcs_path")),
                    key=lambda d: d.get("conf", 0),
                    default=None,
                )
                if best_crop:
                    job_ref.update({
                        "latest_animal_crop": {
                            "filename":      filename,
                            "common_name":   common,
                            "score":         round(score, 3),
                            "crop_gcs_path": best_crop["crop_gcs_path"],
                            "classified_at": now_iso,
                        },
                        "updated_at": now_iso,
                    })

            with count_lock:
                count += 1
                my_count = count

            if my_count % 20 == 0 or my_count == len(files):
                set_status(
                    "running",
                    f"Streamed predictions: {my_count}/{len(files)} processed…",
                )

        def _scan_predictions_file(
            pool: ThreadPoolExecutor, accept_failures: bool = False
        ) -> None:
            """Read predictions.json, dispatch new entries to workers.
            Idempotent — tracks `processed_filepaths` so each prediction
            runs exactly once even though we re-read the whole file each
            cycle. Speciesnet's atomic temp-file-then-rename means we
            never see partial writes; a JSONDecodeError just retries on
            the next cycle.

            CRITICAL: speciesnet's `_merge_results` writes a stub
            `{filepath, failures: [...]}` entry for *every* input filepath
            whose pipeline hasn't completed yet — see
            github.com/google/cameratrapai/blob/main/speciesnet/multiprocessing.py:458.
            So a periodic save at t=5s with only 10 of 119 predictions
            done contains 10 real entries plus 109 failure stubs. If we
            naively process those stubs we mark all 119 filepaths as
            done and miss the real predictions when they arrive in later
            saves — which is what produced the "lots of animals labelled
            blank" regression in execution g7jrp.

            Skip failure entries during in-progress scans so a stub
            doesn't claim a filepath; pick them up in the final scan
            after speciesnet exits, where any remaining failures are
            real (e.g. an unloadable JPEG)."""
            if not os.path.exists(predictions_file):
                return
            try:
                with open(predictions_file, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                return
            new_preds = []
            with processed_lock:
                for pred in data.get("predictions", []):
                    fp = pred.get("filepath")
                    if not fp or fp in processed_filepaths:
                        continue
                    if pred.get("failures") and not accept_failures:
                        continue
                    processed_filepaths.add(fp)
                    new_preds.append(pred)
            for pred in new_preds:
                pool.submit(_process_one_prediction, pred)

        # SpeciesNet's classifier batch size and parallelism mode are tunable
        # at the run_model.py CLI; expose them via env so deploys can sweep
        # (gcloud run jobs update --update-env-vars) without rebuilding the
        # image.
        speciesnet_batch_size = os.environ.get("SPECIESNET_BATCH_SIZE", "8")
        speciesnet_run_mode   = os.environ.get("SPECIESNET_RUN_MODE", "multi_thread")
        set_status(
            "running",
            f"Running SpeciesNet inference (batch_size={speciesnet_batch_size}, "
            f"run_mode={speciesnet_run_mode})…",
        )

        # ── Run SpeciesNet ────────────────────────────────────────────────────
        cmd = [
            "python", "-u", "-m", "speciesnet.scripts.run_model",
            "--instances_json", instances_file,
            "--predictions_json", predictions_file,
            "--batch_size", speciesnet_batch_size,
            "--run_mode", speciesnet_run_mode,
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

        # Start the predictions-file watcher and the per-prediction worker
        # pool BEFORE consuming the speciesnet stdout — speciesnet emits
        # its first periodic save ~5s after starting, and we want the
        # watcher live by then.
        worker_pool = ThreadPoolExecutor(max_workers=CROP_WORKERS)
        stop_event = threading.Event()

        def _watcher() -> None:
            while not stop_event.wait(timeout=PREDICTIONS_POLL_S):
                _scan_predictions_file(worker_pool, accept_failures=False)
            # Final scan once speciesnet exits — accept failure entries
            # at this point because they're now genuine (load_rgb_image
            # gave up on a corrupt file etc.) rather than "not yet
            # processed" stubs from an in-flight pipeline.
            _scan_predictions_file(worker_pool, accept_failures=True)

        watcher_thread = threading.Thread(target=_watcher, daemon=True)
        watcher_thread.start()

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
                # Mirror to stdout so Cloud Logging captures speciesnet's
                # output (including stack traces and CUDA OOM messages).
                # Tqdm progress lines are intentionally skipped — they would
                # add hundreds of lines per run with no diagnostic value.
                print(f"[speciesnet] {line}", flush=True)
                log.append(line)
                job_ref.update({"message": line, "log": log[-50:], "updated_at": _now()})

        process.wait()

        if process.returncode != 0:
            set_status("error", f"SpeciesNet exited with code {process.returncode}")
            stop_event.set()
            worker_pool.shutdown(wait=False, cancel_futures=True)
            raise SystemExit(1)

        # Speciesnet is done. Tell the watcher to do its final scan and
        # exit, then wait for any in-flight per-prediction workers to
        # land their crops + Firestore docs.
        stop_event.set()
        watcher_thread.join()
        worker_pool.shutdown(wait=True)

        summary = {
            "total":        count,
            "by_species":   by_species,
            "by_category":  by_category,
            "images":       summary_images,
        }

        set_status("done", f"Done — {count} prediction(s) saved",
                   {"completed_at": _now(), "summary": summary})
        print(f"[done] Saved {count} predictions for user {uid}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
