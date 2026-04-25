terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.28, < 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.28, < 6.0"
    }
  }
}

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

# Enable all required GCP APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "identitytoolkit.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
