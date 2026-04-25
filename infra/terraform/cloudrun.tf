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

# GPU config isn't yet exposed through the Terraform provider schema, so we
# re-assert it via gcloud after every job create or update.
#
# --no-gpu-zonal-redundancy is the only valid setting for GPU jobs today:
# "Currently Cloud Run jobs are unable to offer GPU enabled instances with
# zonal redundancy due to capacity limitations."
# https://cloud.google.com/run/docs/configuring/jobs/gpu#zonal-redundancy
resource "terraform_data" "inference_gpu" {
  triggers_replace = [
    google_cloud_run_v2_job.inference.id,
    var.inference_image,
  ]

  provisioner "local-exec" {
    command = "gcloud beta run jobs update ${google_cloud_run_v2_job.inference.name} --gpu=1 --gpu-type=nvidia-l4 --execution-environment=gen2 --no-gpu-zonal-redundancy --clear-volumes --clear-volume-mounts --region=${var.region} --project=${var.project_id}"
  }

  depends_on = [google_cloud_run_v2_job.inference]
}
