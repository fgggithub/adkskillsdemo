output "service_url" {
  description = "URL of the deployed Travel Concierge Cloud Run service"
  value       = google_cloud_run_v2_service.travel_concierge.uri
}

output "artifact_registry_repository" {
  description = "Artifact Registry Docker repository URI"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app_repo.repository_id}"
}

output "service_account_email" {
  description = "Service Account email used by Travel Concierge"
  value       = google_service_account.concierge_sa.email
}

output "agent_card_url" {
  description = "A2A Agent Card Discovery URL"
  value       = "${google_cloud_run_v2_service.travel_concierge.uri}/.well-known/agent-card.json"
}
