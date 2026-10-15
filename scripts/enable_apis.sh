#!/usr/bin/env bash
# ==============================================================================
# Script: enable_apis.sh
# Purpose: Enable all required GCP APIs for Travel Concierge Multi-Agent Solution.
# Solution Tag: FDEDEMO
# ==============================================================================

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: Google Cloud PROJECT_ID could not be determined."
  echo "    Please run 'gcloud config set project <PROJECT_ID>' or export PROJECT_ID=<PROJECT_ID>."
  exit 1
fi

echo "[+] Target Google Cloud Project: ${PROJECT_ID}"
echo "[+] Enabling required APIs for Travel Concierge Multi-Agent Solution (Tag: FDEDEMO)..."

REQUIRED_SERVICES=(
  "run.googleapis.com"
  "aiplatform.googleapis.com"
  "cloudtrace.googleapis.com"
  "artifactregistry.googleapis.com"
  "secretmanager.googleapis.com"
  "iam.googleapis.com"
  "cloudbuild.googleapis.com"
  "iap.googleapis.com"
  "agentidentity.googleapis.com"
  "agentidentitycredentials.googleapis.com"
  "discoveryengine.googleapis.com"
  "dialogflow.googleapis.com"
)

for svc in "${REQUIRED_SERVICES[@]}"; do
  echo "  --> Enabling ${svc}..."
  gcloud services enable "${svc}" --project="${PROJECT_ID}"
done

# Ensure Terraform is installed
if ! command -v terraform >/dev/null 2>&1 || [[ "$(terraform version 2>&1 || true)" == *"Follow the instructions"* ]]; then
  echo "[+] Installing Terraform..."
  wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg 2>/dev/null || true
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
  sudo apt-get update -qq && sudo apt-get install -y -qq terraform
fi

echo "[✓] All required APIs and tools verified for project: ${PROJECT_ID}."
