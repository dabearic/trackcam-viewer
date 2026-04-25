"""
Backfill `taken_at` on prediction docs from EXIF DateTimeOriginal.

Reads each prediction's image from GCS, extracts the EXIF capture time
(falling back to DigitizedTime, then the IFD0 DateTime), and writes it
onto the Firestore doc as ISO 8601 naive-local.

Environment:
  GCP_PROJECT, GCS_BUCKET.
  Google ADC with Firestore + GCS read/write.

Usage:
  python infra/scripts/backfill_taken_at.py [--uid UID] [--dry-run] [--overwrite]
"""
import argparse
import io
import os
from datetime import datetime

from google.cloud import firestore, storage
from PIL import Image

_EXIF_EXIF_IFD           = 0x8769
_EXIF_DATETIME_ORIGINAL  = 0x9003
_EXIF_DATETIME_DIGITIZED = 0x9004
_EXIF_DATETIME           = 0x0132


def _parse_exif_datetime(raw) -> str | None:
    if not raw:
        return None
    try:
        s = raw.strip() if isinstance(raw, str) else str(raw).strip()
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        return None


def _extract_taken_at_from_bytes(data: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(data)) as img:
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


# EXIF in a JPEG lives in the APP1 marker right after SOI, almost always
# within the first few tens of KB. Range-download a prefix instead of
# pulling the whole image — typically 100x faster on multi-MB photos.
_PREFIX_BYTES = 256 * 1024


def _download_for_exif(blob) -> bytes | None:
    try:
        return blob.download_as_bytes(start=0, end=_PREFIX_BYTES - 1)
    except Exception:
        try:
            return blob.download_as_bytes()
        except Exception:
            return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uid", help="Only backfill this user's predictions")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="Re-extract even when taken_at is already set")
    args = ap.parse_args()

    project     = os.environ["GCP_PROJECT"]
    bucket_name = os.environ["GCS_BUCKET"]

    db     = firestore.Client(project=project)
    gcs    = storage.Client(project=project)
    bucket = gcs.bucket(bucket_name)

    if args.uid:
        user_refs = [db.collection("users").document(args.uid)]
    else:
        user_refs = list(db.collection("users").list_documents())

    total = updated = skipped = no_exif = errors = 0

    for user_ref in user_refs:
        uid = user_ref.id
        # Materialise the snapshot list so the streaming gRPC closes before
        # we do per-doc GCS work (otherwise the cursor hits DEADLINE_EXCEEDED).
        docs = list(user_ref.collection("predictions").stream())
        print(f"[user] {uid}: {len(docs)} prediction(s)", flush=True)
        for doc in docs:
            total += 1
            data = doc.to_dict()
            if data.get("taken_at") and not args.overwrite:
                skipped += 1
                continue
            gcs_path = data.get("gcs_path") or data.get("filepath")
            if not gcs_path:
                print(f"[err]  {uid}/{doc.id}: no gcs_path", flush=True)
                errors += 1
                continue
            blob_bytes = _download_for_exif(bucket.blob(gcs_path))
            if blob_bytes is None:
                print(f"[err]  {uid}/{gcs_path}: download failed", flush=True)
                errors += 1
                continue
            taken_at = _extract_taken_at_from_bytes(blob_bytes)
            # If the prefix wasn't enough (unusual), retry with full file.
            if not taken_at and len(blob_bytes) >= _PREFIX_BYTES:
                try:
                    blob_bytes = bucket.blob(gcs_path).download_as_bytes()
                    taken_at = _extract_taken_at_from_bytes(blob_bytes)
                except Exception:
                    pass
            if not taken_at:
                no_exif += 1
                print(f"[skip] {uid}/{gcs_path}: no EXIF date", flush=True)
                continue
            print(f"[ok]   {uid}/{gcs_path}: {taken_at}", flush=True)
            if not args.dry_run:
                doc.reference.update({"taken_at": taken_at})
            updated += 1

    suffix = " (dry-run)" if args.dry_run else ""
    print(f"\nDone: total={total} updated={updated} already_set={skipped} "
          f"no_exif={no_exif} errors={errors}{suffix}")


if __name__ == "__main__":
    main()
