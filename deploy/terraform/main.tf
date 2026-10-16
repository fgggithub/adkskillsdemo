terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.20"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 7.20"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
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
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "iap.googleapis.com",
    "agentregistry.googleapis.com",
    "agentidentity.googleapis.com",
    "agentidentitycredentials.googleapis.com",
    "discoveryengine.googleapis.com",
    "dialogflow.googleapis.com",
    "storage.googleapis.com",
  ])

  service            = each.key
  disable_on_destroy = false
}

# 2. Artifact Registry for Container Images
resource "google_artifact_registry_repository" "app_repo" {
  depends_on    = [google_project_service.enabled_apis]
  location      = var.region
  repository_id = "travel-concierge-repo"
  description   = "Docker repository for Travel Concierge Multi-Agent Orchestrator (FDEDEMO)"
  format        = "DOCKER"

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
  }
}

# 3. Secret Manager Secret for Zomato / A2A Credentials
resource "google_secret_manager_secret" "api_credentials" {
  depends_on = [google_project_service.enabled_apis]
  secret_id  = "travel-concierge-api-credentials"

  replication {
    auto {}
  }

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
  }
}

# Local helper for default image
locals {
  app_image = coalesce(
    var.container_image,
    "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app_repo.repository_id}/travel-concierge:latest"
  )
}

# ==============================================================================
# 4. Decoupled Subagent Microservices (Scale to Zero for $0.00 Idle Cost)
# ==============================================================================

# 4a. Hotel Booking Specialist Service
resource "google_cloud_run_v2_service" "hotel_agent" {
  depends_on = [
    google_project_service.enabled_apis,
    google_service_account.concierge_sa,
  ]

  name     = "hotel-booking-specialist"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
    component   = "subagent-hotel"
  }

  template {
    labels = {
      tag         = "fdedemo"
      project     = "fdedemo"
      environment = "fdedemo"
    }

    service_account = google_service_account.concierge_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instance_count
    }

    containers {
      image   = local.app_image
      command = ["uvicorn"]
      args    = ["travel_concierge.services.hotel_service:app", "--host", "0.0.0.0", "--port", "8080"]

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
        name  = "RESOURCE_TAG"
        value = "FDEDEMO"
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "OTEL_EXPORTER_TYPE"
        value = "gcp"
      }
    }
  }
}

# 4b. Restaurant Booking Specialist Service
resource "google_cloud_run_v2_service" "restaurant_agent" {
  depends_on = [
    google_project_service.enabled_apis,
    google_service_account.concierge_sa,
  ]

  name     = "restaurant-booking-specialist"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
    component   = "subagent-restaurant"
  }

  template {
    labels = {
      tag         = "fdedemo"
      project     = "fdedemo"
      environment = "fdedemo"
    }

    service_account = google_service_account.concierge_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instance_count
    }

    containers {
      image   = local.app_image
      command = ["uvicorn"]
      args    = ["travel_concierge.services.restaurant_service:app", "--host", "0.0.0.0", "--port", "8080"]

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
        name  = "RESOURCE_TAG"
        value = "FDEDEMO"
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "OTEL_EXPORTER_TYPE"
        value = "gcp"
      }
    }
  }
}

# 4c. Final Verification & HITL Service
resource "google_cloud_run_v2_service" "verification_agent" {
  depends_on = [
    google_project_service.enabled_apis,
    google_service_account.concierge_sa,
  ]

  name     = "final-verification-agent"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
    component   = "subagent-verification"
  }

  template {
    labels = {
      tag         = "fdedemo"
      project     = "fdedemo"
      environment = "fdedemo"
    }

    service_account = google_service_account.concierge_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instance_count
    }

    containers {
      image   = local.app_image
      command = ["uvicorn"]
      args    = ["travel_concierge.services.verification_service:app", "--host", "0.0.0.0", "--port", "8080"]

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
        name  = "RESOURCE_TAG"
        value = "FDEDEMO"
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "OTEL_EXPORTER_TYPE"
        value = "gcp"
      }
    }
  }
}

# ==============================================================================
# 5. Agent Gateway Policy Enforcement Point (PEP) Service
# ==============================================================================

resource "google_cloud_run_v2_service" "agent_gateway" {
  depends_on = [
    google_project_service.enabled_apis,
    google_service_account.concierge_sa,
    google_cloud_run_v2_service.hotel_agent,
    google_cloud_run_v2_service.restaurant_agent,
    google_cloud_run_v2_service.verification_agent,
  ]

  name     = "agent-gateway-pep"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
    component   = "agent-gateway-pep"
  }

  template {
    labels = {
      tag         = "fdedemo"
      project     = "fdedemo"
      environment = "fdedemo"
    }

    service_account = google_service_account.concierge_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instance_count
    }

    containers {
      image   = local.app_image
      command = ["uvicorn"]
      args    = ["travel_concierge.gateway.server:app", "--host", "0.0.0.0", "--port", "8080"]

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
        name  = "HOTEL_SERVICE_URL"
        value = google_cloud_run_v2_service.hotel_agent.uri
      }
      env {
        name  = "RESTAURANT_SERVICE_URL"
        value = google_cloud_run_v2_service.restaurant_agent.uri
      }
      env {
        name  = "VERIFICATION_SERVICE_URL"
        value = google_cloud_run_v2_service.verification_agent.uri
      }
      env {
        name  = "RESOURCE_TAG"
        value = "FDEDEMO"
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "OTEL_EXPORTER_TYPE"
        value = "gcp"
      }
    }
  }
}

# ==============================================================================
# 6. Travel Concierge Root Orchestrator Service
# ==============================================================================

resource "google_cloud_run_v2_service" "travel_concierge" {
  depends_on = [
    google_project_service.enabled_apis,
    google_service_account.concierge_sa,
    google_project_iam_member.vertex_ai_user,
    google_cloud_run_v2_service.agent_gateway,
  ]

  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  labels = {
    tag         = "fdedemo"
    project     = "fdedemo"
    environment = "fdedemo"
    component   = "root-orchestrator"
  }

  template {
    labels = {
      tag         = "fdedemo"
      project     = "fdedemo"
      environment = "fdedemo"
    }

    service_account = google_service_account.concierge_sa.email

    scaling {
      min_instance_count = var.min_instance_count
      max_instance_count = var.max_instance_count
    }

    containers {
      image   = local.app_image
      command = ["uvicorn"]
      args    = ["travel_concierge.server:app", "--host", "0.0.0.0", "--port", "8080"]

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
        value = "gemini-3.5-flash"
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "OTEL_EXPORTER_TYPE"
        value = "gcp"
      }
      env {
        name  = "RESOURCE_TAG"
        value = "FDEDEMO"
      }
      env {
        name  = "AGENT_GATEWAY_URL"
        value = google_cloud_run_v2_service.agent_gateway.uri
      }
      env {
        name  = "USE_AGENT_GATEWAY"
        value = "true"
      }
      env {
        name  = "HOTEL_SERVICE_URL"
        value = google_cloud_run_v2_service.hotel_agent.uri
      }
      env {
        name  = "RESTAURANT_SERVICE_URL"
        value = google_cloud_run_v2_service.restaurant_agent.uri
      }
      env {
        name  = "VERIFICATION_SERVICE_URL"
        value = google_cloud_run_v2_service.verification_agent.uri
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 30
        timeout_seconds       = 5
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 15
        period_seconds        = 15
        timeout_seconds       = 3
      }
    }
  }
}
