# ── Web API + Frontend service ────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "api" {
  project  = var.project_id
  name     = "trackcam-api"
  location = var.region

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.api_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.main.name
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "INFERENCE_JOB_NAME"
        value = "projects/${var.project_id}/locations/${var.region}/jobs/speciesnet-inference"
      }
      env {
        name  = "REGION"
        value = var.region
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.main,
  ]
}

# Allow unauthenticated access — the app handles auth itself
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── SpeciesNet inference Cloud Run Job ────────────────────────────────────────

resource "google_cloud_run_v2_job" "inference" {
  provider = google-beta
  project  = var.project_id
  name     = "speciesnet-inference"
  location = var.region

  template {
    template {
      service_account = google_service_account.inference.email
      max_retries     = 0
      timeout         = "3600s"

      containers {
        image = var.inference_image

        resources {
          limits = {
            cpu    = "8"
            memory = "32Gi"
          }
        }

        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.main.name
        }
        env {
          name  = "GCP_PROJECT"
          value = var.project_id
        }
        # KAGGLEHUB_CACHE env, the model-cache volume, and the volume mount
        # are applied via the inference_gpu provisioner below — declaring
        # them here would race with the gcloud update that re-asserts GPU
        # config and wipe v2-only fields.
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.main,
  ]
}

# GPU config and v2-only fields (GCS volume, mount, KAGGLEHUB_CACHE env) are
# applied via gcloud after every job create or update. The Terraform google
# provider's in-place updates use the v1 (Knative) API view, which silently
# drops v2-only fields like GCS volumes — so we treat this provisioner as
# the source of truth for everything Cloud Run-Job-specific that doesn't
# round-trip cleanly through the provider.
resource "terraform_data" "inference_gpu" {
  triggers_replace = [
    google_cloud_run_v2_job.inference.id,
    var.inference_image,
    google_storage_bucket.model_cache.name,
  ]

  provisioner "local-exec" {
    command = "gcloud beta run jobs update ${google_cloud_run_v2_job.inference.name} --gpu=1 --gpu-type=nvidia-l4 --execution-environment=gen2 --gpu-zonal-redundancy --update-env-vars=KAGGLEHUB_CACHE=/mnt/model-cache --clear-volumes --clear-volume-mounts --add-volume=name=model-cache,type=cloud-storage,bucket=${google_storage_bucket.model_cache.name} --add-volume-mount=volume=model-cache,mount-path=/mnt/model-cache --region=${var.region} --project=${var.project_id}"
  }

  depends_on = [google_cloud_run_v2_job.inference]
}
