# ==============================================================================
# Google Cloud Agent Platform - Managed Agent Gateway
# Docs: https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview
# Module: https://github.com/GoogleCloudPlatform/terraform-google-agent-gateway
# ==============================================================================

# Enable required Network Services and Security APIs
resource "google_project_service" "agent_gateway_apis" {
  for_each = toset([
    "networkservices.googleapis.com",
    "networksecurity.googleapis.com",
    "serviceextensions.googleapis.com",
    "modelarmor.googleapis.com"
  ])

  service            = each.key
  disable_on_destroy = false
}

# Declarative Agent Platform Gateway provisioning via local-exec / gcloud
# (Provides compatibility across google-provider versions for the new agent-gateway resource)
resource "terraform_data" "agent_platform_gateway" {
  depends_on = [
    google_project_service.agent_gateway_apis
  ]

  input = {
    gateway_name = "travel-concierge-gateway"
    region       = var.region
    project_id   = var.project_id
  }

  provisioner "local-exec" {
    command = <<-EOT
      gcloud network-services agent-gateways import travel-concierge-gateway \
        --source="${path.module}/../agent_gateway/agent_gateway.yaml" \
        --location="${var.region}" \
        --project="${var.project_id}" || true
    EOT
  }
}
