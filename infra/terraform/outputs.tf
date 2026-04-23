output "api_url" {
  description = "Cloud Run service URL — open this in your browser"
  value       = google_cloud_run_v2_service.api.uri
}

output "bucket_name" {
  description = "GCS bucket for images"
  value       = google_storage_bucket.main.name
}

output "artifact_registry" {
  description = "Docker registry URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/trackcam"
}

output "inference_job" {
  description = "Full Cloud Run Job resource name"
  value       = "projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.inference.name}"
}
