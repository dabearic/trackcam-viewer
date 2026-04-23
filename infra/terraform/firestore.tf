resource "google_firestore_database" "main" {
  project     = var.project_id
  name        = "(default)"
  location_id = "nam5"  # US multi-region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# Composite indexes for efficient gallery queries
resource "google_firestore_index" "predictions_folder_filename" {
  project    = var.project_id
  database   = google_firestore_database.main.name
  collection = "predictions"

  fields {
    field_path = "uid"
    order      = "ASCENDING"
  }
  fields {
    field_path = "folder"
    order      = "ASCENDING"
  }
  fields {
    field_path = "filename"
    order      = "ASCENDING"
  }
}
