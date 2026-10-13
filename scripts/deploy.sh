#!/usr/bin/env bash
# ==============================================================================
# Script: deploy.sh
# Purpose: Reproducible end-to-end deployment of Travel Concierge Multi-Agent Solution.
# Solution Tag: FDEDEMO
# ==============================================================================

set -euo pipefail

START_TIME=$(date +%s)
echo "=========================================================================="
echo "    STARTING REPRODUCIBLE DEPLOYMENT: TRAVEL CONCIERGE (FDEDEMO)         "
echo "=========================================================================="

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="travel-concierge-orchestrator"
REPO_NAME="travel-concierge-repo"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: Google Cloud PROJECT_ID could not be determined."
  exit 1
fi

export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"

echo "[1/6] Target GCP Project: ${PROJECT_ID} in ${REGION}"

# Step 1: Enable APIs
echo "[2/6] Enabling APIs..."
bash scripts/enable_apis.sh

# Step 2: Register Skills in GCP Agent Runtime Skills Registry
echo "[3/6] Registering ADK dietary_advisor Skill in Agent Runtime..."
python3 scripts/register_skills.py

# Step 3: Initialize and Apply Terraform for Core Infrastructure
echo "[4/6] Initializing Terraform infrastructure..."
terraform -chdir=deploy/terraform init -input=false
chmod -R +x deploy/terraform/.terraform/providers 2>/dev/null || true

echo "      Applying Artifact Registry and Service Account..."
terraform -chdir=deploy/terraform apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="service_name=${SERVICE_NAME}" \
  -target=google_artifact_registry_repository.app_repo \
  -target=google_service_account.concierge_sa \
  -target=google_project_iam_member.vertex_ai_user \
  -target=google_project_iam_member.cloud_trace_agent \
  -target=google_secret_manager_secret.api_credentials \
  -auto-approve

# Step 4: Build and Push Container Image
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/travel-concierge:latest"
echo "[5/6] Building container image: ${IMAGE_URI}..."
docker build -t "${IMAGE_URI}" -f deploy/Dockerfile .

echo "      Configuring docker authentication..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "      Pushing container to Artifact Registry..."
docker push "${IMAGE_URI}"

# Step 5: Deploy Cloud Run Service via Terraform
echo "[6/6] Deploying Cloud Run Service with container image..."
terraform -chdir=deploy/terraform apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="service_name=${SERVICE_NAME}" \
  -var="container_image=${IMAGE_URI}" \
  -auto-approve

# Ensure newest container revision is running
gcloud run services update "${SERVICE_NAME}" \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --quiet

# Verification
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)' 2>/dev/null || terraform -chdir=deploy/terraform output -raw service_url)
echo "[+] Service deployed at: ${SERVICE_URL}"

echo "      Checking /health endpoint..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health" || echo "failed")
echo "      Health Check (/health) Response: ${HTTP_STATUS}"

echo "      Checking A2A Agent Card endpoint..."
CARD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/.well-known/agent-card.json" || echo "failed")
echo "      Agent Card (/.well-known/agent-card.json) Response: ${CARD_STATUS}"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
echo "=========================================================================="
echo " [✓] DEPLOYMENT COMPLETED SUCCESSFULLY"
echo "     Target URL:     ${SERVICE_URL}"
echo "     Resource Tag:   FDEDEMO"
echo "     Elapsed Time:   ${ELAPSED} seconds (~$((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "=========================================================================="

python3 scripts/cost_report.py
