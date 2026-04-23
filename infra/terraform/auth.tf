# Enable Identity Platform and configure Google Sign-In
resource "google_identity_platform_config" "main" {
  project = var.project_id

  sign_in {
    allow_duplicate_emails = false
  }

  depends_on = [google_project_service.apis]
}

# Configure Google as an OAuth sign-in provider
resource "google_identity_platform_default_supported_idp_config" "google" {
  project       = var.project_id
  idp_id        = "google.com"
  client_id     = var.oauth_client_id
  client_secret = var.oauth_client_secret
  enabled       = true

  depends_on = [google_identity_platform_config.main]
}

# Store OAuth client secret in Secret Manager for reference
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
