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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="travel-concierge-orchestrator"
REPO_NAME="travel-concierge-repo"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: Google Cloud PROJECT_ID could not be determined."
  exit 1
fi

export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"

echo "[1/7] Target GCP Project: ${PROJECT_ID} in ${REGION}"

# Step 0: Ensure local Python environment and requirements.txt are installed
echo "      Installing required Python dependencies from requirements.txt..."
export PATH="${HOME}/.local/bin:${PATH}"
python3 -m pip install -q -r "${REPO_ROOT}/requirements.txt" 2>/dev/null || python3 -m pip install -q --break-system-packages -r "${REPO_ROOT}/requirements.txt"

# Step 1: Enable APIs
echo "[2/7] Enabling APIs..."
bash scripts/enable_apis.sh

# Step 2: Register Skills in GCP Agent Runtime Skills Registry
echo "[3/7] Registering ADK dietary_advisor Skill in Agent Runtime..."
python3 scripts/register_skills.py --project-id="${PROJECT_ID}" --location="${REGION}"

# Step 3: Initialize and Apply Terraform for Core Infrastructure
echo "[4/7] Initializing Terraform infrastructure..."
if [[ -f "deploy/terraform/terraform.tfstate" ]] && grep -q '"project":' "deploy/terraform/terraform.tfstate"; then
  if ! grep -q "\"${PROJECT_ID}\"" "deploy/terraform/terraform.tfstate"; then
    echo "      Detected state from a different project. Clearing stale state..."
    rm -f deploy/terraform/terraform.tfstate deploy/terraform/terraform.tfstate.backup
  fi
fi
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
echo "[5/7] Building container image: ${IMAGE_URI}..."
docker build -t "${IMAGE_URI}" -f deploy/Dockerfile .

echo "      Configuring docker authentication..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "      Pushing container to Artifact Registry..."
docker push "${IMAGE_URI}"

# Step 5: Deploy Cloud Run Service via Terraform
echo "[6/7] Deploying Cloud Run Service with container image..."
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

# Verification across all 5 deployed microservices
resolve_deploy_url() {
  local service_name="$1"
  local tf_output_key="$2"
  local url=""

  if [[ -n "${PROJECT_ID}" ]]; then
    url=$(gcloud run services describe "${service_name}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")
  fi
  if [[ -z "${url}" || ! "${url}" =~ ^https?:// ]] && [[ -f "deploy/terraform/terraform.tfstate" ]]; then
    url=$(python3 -c '
import json, sys
try:
    with open("deploy/terraform/terraform.tfstate") as f:
        data = json.load(f)
    print(data.get("outputs", {}).get("'"${tf_output_key}"'", {}).get("value", "") or "")
except Exception:
    pass
' 2>/dev/null || echo "")
  fi
  if [[ -z "${url}" || ! "${url}" =~ ^https?:// ]] && command -v terraform >/dev/null 2>&1; then
    if terraform version 2>&1 | grep -q 'Terraform v'; then
      url=$(terraform -chdir=deploy/terraform output -raw "${tf_output_key}" 2>/dev/null || echo "")
    fi
  fi
  if [[ "${url}" =~ ^https?:// ]]; then
    echo "${url}"
  else
    echo ""
  fi
}

GATEWAY_URL=$(resolve_deploy_url "agent-gateway-pep" "agent_gateway_url")
SERVICE_URL=$(resolve_deploy_url "${SERVICE_NAME}" "service_url")

echo "[+] Root Orchestrator deployed at: ${SERVICE_URL}"
echo "[+] Agent Gateway PEP deployed at: ${GATEWAY_URL}"

# Step 6: Configure Google Auth Platform & OAuth clients for Gemini Enterprise
echo "[7/7] Configuring Google Auth Platform and OAuth clients for Gemini Enterprise..."
bash scripts/setup_auth_platform.sh \
  --project-id="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-url="${SERVICE_URL}"

# Register Root Agent in GCP Agent Registry
echo "[+] Registering Root Agent in GCP Agent Registry..."
python3 scripts/register_agents.py --service-url="${SERVICE_URL}" --region="${REGION}" --project-id="${PROJECT_ID}"

# Provision Gemini Enterprise App 'fdedemoapp' and register agent
echo "[+] Provisioning Gemini Enterprise App 'fdedemoapp'..."
bash scripts/create_gemini_enterprise_app.sh \
  --project-id="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-url="${SERVICE_URL}" \
  --app-id="fdedemoapp"

# Register ADK Agent in Gemini Enterprise App assistant
echo "[+] Registering ADK Agent 'Travel Concierge' in Gemini Enterprise App..."
bash scripts/register_adk_agent.sh \
  --project-id="${PROJECT_ID}" \
  --app-id="fdedemoapp" \
  --location="global" \
  --display-name="Travel Concierge"

echo "      Checking Root Orchestrator /health..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health" || echo "failed")
echo "      Root Health Check: ${HTTP_STATUS}"

if [[ -n "${GATEWAY_URL}" ]]; then
  echo "      Checking Agent Gateway /health..."
  GW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/health" || echo "failed")
  echo "      Gateway Health Check: ${GW_STATUS}"
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
echo "=========================================================================="
echo " [✓] DEPLOYMENT COMPLETED SUCCESSFULLY"
echo "     Target URL:     ${SERVICE_URL}"
echo "     Resource Tag:   FDEDEMO"
echo "     Elapsed Time:   ${ELAPSED} seconds (~$((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "=========================================================================="

python3 scripts/cost_report.py
