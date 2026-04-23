resource "google_artifact_registry_repository" "main" {
  project       = var.project_id
  location      = var.region
  repository_id = "trackcam"
  format        = "DOCKER"
  description   = "TrackCam Viewer Docker images"

  depends_on = [google_project_service.apis]
}
