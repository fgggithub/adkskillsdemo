output "service_url" {
  description = "URL of the deployed Travel Concierge Root Orchestrator Cloud Run service"
  value       = google_cloud_run_v2_service.travel_concierge.uri
}

output "agent_gateway_url" {
  description = "URL of the Agent Gateway Policy Enforcement Point (PEP)"
  value       = google_cloud_run_v2_service.agent_gateway.uri
}

output "hotel_agent_url" {
  description = "URL of the Hotel Booking Specialist subagent service"
  value       = google_cloud_run_v2_service.hotel_agent.uri
}

output "restaurant_agent_url" {
  description = "URL of the Restaurant Booking Specialist subagent service"
  value       = google_cloud_run_v2_service.restaurant_agent.uri
}

output "verification_agent_url" {
  description = "URL of the Final Verification subagent service"
  value       = google_cloud_run_v2_service.verification_agent.uri
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
  description = "A2A Agent Card Discovery URL for Root Orchestrator"
  value       = "${google_cloud_run_v2_service.travel_concierge.uri}/.well-known/agent-card.json"
}

output "gateway_card_url" {
  description = "A2A Agent Card Discovery URL for Agent Gateway"
  value       = "${google_cloud_run_v2_service.agent_gateway.uri}/.well-known/agent-card.json"
}
