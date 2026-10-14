# Service Account for Travel Concierge Cloud Run
resource "google_service_account" "concierge_sa" {
  account_id   = "travel-concierge-sa"
  display_name = "Travel Concierge Orchestrator Service Account"
  description  = "Least-privilege service account for Travel Concierge Agent operations."
}

# 1. Vertex AI / Gemini Access (roles/aiplatform.user)
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.concierge_sa.email}"
}

# 2. Cloud Trace Exporter Access (roles/cloudtrace.agent)
resource "google_project_iam_member" "cloud_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.concierge_sa.email}"
}

# 3. Cloud Run Invokers (all services secured with Zero-Trust JWTs at application layer)
resource "google_cloud_run_v2_service_iam_member" "public_orchestrator_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.travel_concierge.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "agent_gateway_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent_gateway.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "hotel_agent_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hotel_agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "restaurant_agent_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.restaurant_agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "verification_agent_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.verification_agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
