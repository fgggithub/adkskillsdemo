#!/usr/bin/env bash
# ==============================================================================
# Script: teardown.sh
# Purpose: Complete teardown of Travel Concierge resources and zero-cost verification.
# Solution Tag: FDEDEMO
# ==============================================================================

set -euo pipefail

START_TIME=$(date +%s)
echo "=========================================================================="
echo "    STARTING TEARDOWN: TRAVEL CONCIERGE (FDEDEMO)                         "
echo "=========================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="${HOME}/.local/bin:${PATH}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"
REGION="${REGION:-us-central1}"
REPO_NAME="travel-concierge-repo"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: Google Cloud PROJECT_ID could not be determined."
  exit 1
fi

export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"

echo "[1/3] Destroying Terraform resources..."
chmod -R +x deploy/terraform/.terraform/providers 2>/dev/null || true
terraform -chdir=deploy/terraform destroy \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -auto-approve || true

echo "[2/3] Deleting Artifact Registry repository if retained..."
gcloud artifacts repositories delete "${REPO_NAME}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --quiet 2>/dev/null || true

echo "[+] Deregistering Agent and Skill Registry resources..."
gcloud alpha agent-registry services delete "travel-concierge-orchestrator" --location=global --project="${PROJECT_ID}" --quiet 2>/dev/null || true
gcloud alpha agent-registry services delete "travel-concierge-orchestrator" --location="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true
gcloud alpha agent-registry skills delete "private-dietary-advisor" --location=global --project="${PROJECT_ID}" --quiet 2>/dev/null || true
gcloud alpha agent-identity auth-providers delete "travel-concierge-auth" --location="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true
python3 scripts/create_gemini_enterprise_app.py --teardown --project-id="${PROJECT_ID}" --region="${REGION}" --app-id="fdedemoapp" 2>/dev/null || true

echo "[3/3] Running residual cost audit to verify 100% clean teardown..."
python3 scripts/cost_report.py --verify-teardown

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
echo "=========================================================================="
echo " [✓] TEARDOWN COMPLETED SUCCESSFULLY"
echo "     Status:         Zero Residual Cost Verified"
echo "     Elapsed Time:   ${ELAPSED} seconds (~$((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "=========================================================================="
