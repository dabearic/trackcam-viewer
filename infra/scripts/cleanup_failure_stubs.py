"""
One-shot recovery for the failure-stub bug introduced (and fixed) in PR #34.

PR #34 added streaming-prediction processing — a watcher thread that reads
the predictions.json speciesnet writes periodically and dispatches new
entries to per-prediction workers. Speciesnet's _merge_results function
writes a `{filepath, failures: [name]}` placeholder for every input
filepath whose pipeline stage hasn't completed yet, so a periodic save
fired before all images had been classified contained 10 real entries +
N failure stubs. The original streaming code processed those stubs as if
they were finished predictions, claiming the filepath in
`processed_filepaths` and ignoring the real prediction when it arrived
later. Result: many animals incorrectly written as blank-with-failures
to Firestore.

The streaming code has since been fixed to skip failure stubs in-progress
and only accept them in the final scan after speciesnet exits. This
script cleans up any docs that landed in Firestore from the buggy window.

Identification: a stub doc has `prediction is None` AND `failures` is
non-empty AND comes from the affected `job_id`. Real predictions —
even ones with partial component failures (e.g. GEOLOCATION failed but
classifier worked) — keep `prediction` set, so they're untouched.

Environment:
  GCP_PROJECT.
  Google ADC with Firestore read/write.

Dependencies:
  pip install google-cloud-firestore

Usage (bash / Linux / macOS):
  GCP_PROJECT=trackcam-viewer python infra/scripts/cleanup_failure_stubs.py \
      --uid UID --job-id JOBID --dry-run

Usage (PowerShell on Windows):
  $env:GCP_PROJECT="trackcam-viewer"
  py infra/scripts/cleanup_failure_stubs.py --uid UID --job-id JOBID --dry-run

  On Windows the bare `python` command is intercepted by the Microsoft
  Store app-execution alias; use `py` (the Python launcher) instead.
  If `from google.cloud import firestore` fails, run
  `py -m pip install google-cloud-firestore` — the user-site install
  path is not always on Python's import search list depending on how
  your shell is configured.

The job_id is the firestore job-doc ID (8-char hex) — NOT the Cloud Run
execution suffix. Find it on any of the bad prediction docs in the
Firestore console (the `job_id` field), or on the job's own doc under
users/<uid>/jobs/<job_id>.
"""
import argparse
import os

from google.cloud import firestore


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uid",     required=True, help="Firebase UID whose predictions to clean")
    ap.add_argument("--job-id",  required=True, help="Firestore job_id (NOT the Cloud Run execution suffix)")
    ap.add_argument("--dry-run", action="store_true", help="List doomed docs without deleting")
    args = ap.parse_args()

    project = os.environ["GCP_PROJECT"]
    db = firestore.Client(project=project)
    pred_col = (
        db.collection("users").document(args.uid)
        .collection("predictions")
    )

    # Materialise the query before doing per-doc work so the gRPC stream
    # can close cleanly (mirrors backfill_taken_at.py:99).
    docs = list(pred_col.where("job_id", "==", args.job_id).stream())
    print(f"Scanned {len(docs)} prediction(s) for job {args.job_id}")

    doomed = []
    for snap in docs:
        d = snap.to_dict()
        # Conservative filter: only docs that have NO ensembled prediction
        # AND non-empty failures. Predictions where some pipeline stage
        # failed but ensemble still produced a label keep `prediction`
        # set, so they're left alone.
        if d.get("prediction") is None and d.get("failures"):
            doomed.append((snap.reference, d.get("filename"), d.get("failures")))

    if not doomed:
        print("No failure-stub docs found. Nothing to delete.")
        return

    print(f"Found {len(doomed)} failure-stub doc(s):")
    preview = doomed[:20]
    for _, name, failures in preview:
        print(f"  {name}  failures={failures}")
    if len(doomed) > len(preview):
        print(f"  ... and {len(doomed) - len(preview)} more")

    if args.dry_run:
        print(f"\n(dry-run — no deletes performed)")
        return

    for ref, name, _ in doomed:
        ref.delete()
    print(f"\nDeleted {len(doomed)} doc(s).")


if __name__ == "__main__":
    main()
