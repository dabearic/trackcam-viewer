# Enable Identity Platform (Firebase Auth)
resource "google_identity_platform_config" "main" {
  project = var.project_id

  sign_in {
    allow_duplicate_emails = false

    google {
      enabled   = true
      client_id = var.oauth_client_id
    }
  }

  depends_on = [google_project_service.apis]
}

# Store OAuth client secret in Secret Manager
resource "google_secret_manager_secret" "oauth_client_secret" {
  project   = var.project_id
  secret_id = "oauth-client-secret"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "oauth_client_secret" {
  secret      = google_secret_manager_secret.oauth_client_secret.id
  secret_data = var.oauth_client_secret
}
