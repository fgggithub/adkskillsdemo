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

# 3. Secret Manager Access (roles/secretmanager.secretAccessor)
resource "google_secret_manager_secret_iam_member" "secret_accessor" {
  secret_id = google_secret_manager_secret.api_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.concierge_sa.email}"
}

# 4. Cloud Run Invoker (Public or Gateway Invocation)
resource "google_cloud_run_v2_service_iam_member" "public_or_gateway_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.travel_concierge.name
  role     = "roles/run.invoker"
  member   = "allUsers" # Or specific caller SA for internal Gateway ingress
}
