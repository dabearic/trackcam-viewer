variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "trackcam-viewer"
}

variable "region" {
  description = "GCP region (must support Cloud Run GPU)"
  type        = string
  default     = "us-east4"
}

variable "admin_email" {
  description = "Google account email to grant owner access"
  type        = string
  default     = "dabearic@gmail.com"
}

variable "oauth_client_id" {
  description = "Google OAuth 2.0 Web Client ID (from Cloud Console)"
  type        = string
}

variable "oauth_client_secret" {
  description = "Google OAuth 2.0 Web Client Secret (from Cloud Console)"
  type        = string
  sensitive   = true
}

variable "api_image" {
  description = "Docker image for the web API service"
  type        = string
  # Placeholder allows `terraform apply` to succeed before real images are built.
  # After pushing your images, re-run `terraform apply` to update Cloud Run.
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "inference_image" {
  description = "Docker image for the inference Cloud Run Job"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
