# ── Service accounts ──────────────────────────────────────────────────────────

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "trackcam-api"
  display_name = "TrackCam API"
  description  = "Runs the Cloud Run web service"
}

resource "google_service_account" "inference" {
  project      = var.project_id
  account_id   = "trackcam-inference"
  display_name = "TrackCam Inference"
  description  = "Runs the SpeciesNet Cloud Run Job"
}

# ── API service account permissions ──────────────────────────────────────────

# Read/write Firestore
resource "google_project_iam_member" "api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Generate signed GCS URLs (requires service account token creator on itself)
resource "google_service_account_iam_member" "api_token_creator" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# Trigger Cloud Run Jobs
resource "google_project_iam_member" "api_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# ── Inference service account permissions ────────────────────────────────────

# Read/write Firestore (update job status + write predictions)
resource "google_project_iam_member" "inference_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.inference.email}"
}

# ── Admin owner ──────────────────────────────────────────────────────────────

resource "google_project_iam_member" "admin_owner" {
  project = var.project_id
  role    = "roles/owner"
  member  = "user:${var.admin_email}"
}
