# ==============================================================================
# Gemini Enterprise Web App & Data Store Provisioning
# Deploys official Gemini Enterprise Search & Assistant App (APP_TYPE_INTRANET)
# ==============================================================================

locals {
  solution_type = "SOLUTION_TYPE_SEARCH"
  app_type      = "APP_TYPE_INTRANET"
  name_prefix   = "gemini-enterprise"
  company_name  = "Travel Concierge"
}

resource "random_id" "gemini_suffix" {
  byte_length = 4
}

resource "google_discovery_engine_data_store" "gemini_search_store" {
  provider                    = google-beta
  location                    = var.location
  data_store_id               = "${local.name_prefix}-data-store-${random_id.gemini_suffix.hex}"
  display_name                = "Gemini Search Data Store ${random_id.gemini_suffix.hex}"
  industry_vertical           = "GENERIC"
  content_config              = "NO_CONTENT"
  solution_types              = [local.solution_type]
  create_advanced_site_search = false

  depends_on = [
    google_project_service.enabled_apis
  ]
}

resource "google_discovery_engine_search_engine" "gemini_search_engine" {
  provider          = google-beta
  engine_id         = "${local.name_prefix}-engine-${random_id.gemini_suffix.hex}"
  collection_id     = "default_collection"
  location          = google_discovery_engine_data_store.gemini_search_store.location
  display_name      = "Gemini Enterprise App"
  industry_vertical = "GENERIC"
  data_store_ids    = [google_discovery_engine_data_store.gemini_search_store.data_store_id]
  app_type          = local.app_type

  common_config {
    company_name = local.company_name
  }

  features = {
    "agent-sharing-without-admin-approval" = "FEATURE_STATE_ON"
    "disable-agent-sharing"                = "FEATURE_STATE_OFF"
    "agent-gallery"                        = "FEATURE_STATE_ON"
    "bi-directional-audio"                 = "FEATURE_STATE_OFF"
    "disable-google-drive-upload"          = "FEATURE_STATE_OFF"
    "disable-image-generation"             = "FEATURE_STATE_OFF"
    "disable-onedrive-upload"              = "FEATURE_STATE_OFF"
    "disable-talk-to-content"              = "FEATURE_STATE_OFF"
    "disable-video-generation"             = "FEATURE_STATE_OFF"
    "disable-welcome-emails"               = "FEATURE_STATE_OFF"
    "model-selector"                       = "FEATURE_STATE_ON"
    "no-code-agent-builder"                = "FEATURE_STATE_ON"
    "notebook-lm"                          = "FEATURE_STATE_ON"
    "people-search-org-chart"              = "FEATURE_STATE_ON"
    "personalization-memory"               = "FEATURE_STATE_ON"
    "personalization-suggested-highlights" = "FEATURE_STATE_ON"
    "prompt-gallery"                       = "FEATURE_STATE_ON"
    "session-sharing"                      = "FEATURE_STATE_ON"
  }

  search_engine_config {
    search_tier                = "SEARCH_TIER_ENTERPRISE"
    search_add_ons             = ["SEARCH_ADD_ON_LLM"]
    required_subscription_tier = "SUBSCRIPTION_TIER_SEARCH_AND_ASSISTANT"
  }

  knowledge_graph_config {}

  depends_on = [
    google_project_service.enabled_apis
  ]
}
