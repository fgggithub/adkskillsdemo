terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Enable Required GCP APIs
resource "google_project_service" "enabled_apis" {
  for_each = toset([
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudtrace.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
  ])

  service            = each.key
  disable_on_destroy = false
}

# 2. Artifact Registry for Container Images
resource "google_artifact_registry_repository" "app_repo" {
  depends_on    = [google_project_service.enabled_apis]
  location      = var.region
  repository_id = "travel-concierge-repo"
  description   = "Docker repository for Travel Concierge Multi-Agent Orchestrator"
  format        = "DOCKER"
}

# 3. Secret Manager Secret for Zomato / A2A Credentials
resource "google_secret_manager_secret" "api_credentials" {
  depends_on = [google_project_service.enabled_apis]
  secret_id  = "travel-concierge-api-credentials"

  replication {
    auto {}
  }
}

# 4. Cloud Run Service Deployment (v2)
resource "google_cloud_run_v2_service" "travel_concierge" {
  depends_on = [
    google_project_service.enabled_apis,
    google_service_account.concierge_sa,
    google_project_iam_member.vertex_ai_user,
  ]

  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.concierge_sa.email

    scaling {
      min_instance_count = var.min_instance_count
      max_instance_count = var.max_instance_count
    }

    containers {
      image = coalesce(
        var.container_image,
        "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app_repo.repository_id}/travel-concierge:latest"
      )

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
      }

      ports {
        container_port = 8080
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "LOCATION"
        value = var.region
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "MODEL_NAME"
        value = "gemini-2.5-flash"
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 15
        timeout_seconds       = 3
      }
    }
  }
}
