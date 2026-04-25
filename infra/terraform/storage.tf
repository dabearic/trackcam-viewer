resource "google_storage_bucket" "main" {
  name          = "${var.project_id}-data"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET", "PUT", "HEAD"]
    response_header = ["Content-Type", "Authorization", "Content-Length"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.apis]
}

# Allow the API service account to manage objects
resource "google_storage_bucket_iam_member" "api_object_admin" {
  bucket = google_storage_bucket.main.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

# Allow the inference service account to manage objects
resource "google_storage_bucket_iam_member" "inference_object_admin" {
  bucket = google_storage_bucket.main.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.inference.email}"
}

# ── Model cache bucket ────────────────────────────────────────────────────────
# Mounted into the inference job at /mnt/model-cache so the SpeciesNet weights
# (~700 MB-1 GB from Kaggle Hub) are downloaded once and reused across runs
# instead of re-fetched on every cold start.
resource "google_storage_bucket" "model_cache" {
  name          = "${var.project_id}-model-cache"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "inference_model_cache" {
  bucket = google_storage_bucket.model_cache.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.inference.email}"
}
