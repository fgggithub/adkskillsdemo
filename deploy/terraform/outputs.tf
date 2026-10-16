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

output "agent_platform_gateway_name" {
  description = "Fully-qualified resource name of the Google Cloud Agent Platform Agent Gateway"
  value       = "projects/${var.project_id}/locations/${var.region}/agentGateways/travel-concierge-gateway"
}

output "gemini_enterprise_app_id" {
  description = "Engine ID of the Gemini Enterprise Web App"
  value       = google_discovery_engine_search_engine.gemini_search_engine.engine_id
}

output "gemini_enterprise_app_name" {
  description = "Full resource name of the Gemini Enterprise Web App"
  value       = google_discovery_engine_search_engine.gemini_search_engine.name
}

output "gemini_enterprise_data_store_id" {
  description = "Data Store ID attached to Gemini Enterprise"
  value       = google_discovery_engine_data_store.gemini_search_store.data_store_id
}

output "gemini_enterprise_console_url" {
  description = "Direct URL to view and preview the Gemini Enterprise Web App in the Google Cloud Console"
  value       = "https://console.cloud.google.com/gemini-enterprise?project=${var.project_id}"
}
