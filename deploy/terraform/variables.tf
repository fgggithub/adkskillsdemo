variable "project_id" {
  type        = string
  description = "Google Cloud Project ID"
}

variable "region" {
  type        = string
  description = "GCP Region for Cloud Run, Artifact Registry, and Vertex AI"
  default     = "us-central1"
}

variable "location" {
  type        = string
  description = "Location of Gemini Enterprise deployment. Can be us, eu, or global."
  default     = "global"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g. prod, staging, dev)"
  default     = "prod"
}

variable "service_name" {
  type        = string
  description = "Name of the Cloud Run service"
  default     = "travel-concierge-orchestrator"
}

variable "container_image" {
  type        = string
  description = "Container image URI in Artifact Registry or GCR"
  default     = ""
}

variable "min_instance_count" {
  type        = number
  description = "Minimum number of Cloud Run instances (0 for scale-to-zero)"
  default     = 0
}

variable "max_instance_count" {
  type        = number
  description = "Maximum number of Cloud Run instances"
  default     = 4
}

variable "cpu_limit" {
  type        = string
  description = "CPU allocated per Cloud Run instance"
  default     = "1"
}

variable "memory_limit" {
  type        = string
  description = "Memory allocated per Cloud Run instance"
  default     = "1Gi"
}
