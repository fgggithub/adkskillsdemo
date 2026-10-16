#!/usr/bin/env bash
# ==============================================================================
# Script: create_gemini_enterprise_app.sh
# Purpose: Creates the Gemini Enterprise App 'fdedemoapp' and registers the
#          Travel Concierge Root Agent with Agent Identity & Registry.
# Solution Tag: FDEDEMO
#
# References:
# - https://docs.cloud.google.com/gemini/enterprise/docs/get-answers-from-streamassist
# - https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity
# - https://docs.cloud.google.com/agent-registry/overview
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Default parameters
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"
REGION="${REGION:-us-central1}"
LOCATION="${LOCATION:-global}"
APP_ID="${APP_ID:-fdedemoapp}"
DISPLAY_NAME="${DISPLAY_NAME:-fdedemoapp}"
SOLUTION_TYPE="${SOLUTION_TYPE:-SOLUTION_TYPE_SEARCH}"
AUTH_PROVIDER_ID="${AUTH_PROVIDER_ID:-travel-concierge-auth}"
SERVICE_NAME="travel-concierge-orchestrator"
SERVICE_URL=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id=*)
      PROJECT_ID="${1#*=}"
      shift
      ;;
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --region=*)
      REGION="${1#*=}"
      shift
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --location=*)
      LOCATION="${1#*=}"
      shift
      ;;
    --location)
      LOCATION="$2"
      shift 2
      ;;
    --app-id=*)
      APP_ID="${1#*=}"
      shift
      ;;
    --app-id)
      APP_ID="$2"
      shift 2
      ;;
    --display-name=*)
      DISPLAY_NAME="${1#*=}"
      shift
      ;;
    --display-name)
      DISPLAY_NAME="$2"
      shift 2
      ;;
    --solution-type=*)
      SOLUTION_TYPE="${1#*=}"
      shift
      ;;
    --solution-type)
      SOLUTION_TYPE="$2"
      shift 2
      ;;
    --service-url=*)
      SERVICE_URL="${1#*=}"
      shift
      ;;
    --service-url)
      SERVICE_URL="$2"
      shift 2
      ;;
    --auth-provider-id=*)
      AUTH_PROVIDER_ID="${1#*=}"
      shift
      ;;
    --auth-provider-id)
      AUTH_PROVIDER_ID="$2"
      shift 2
      ;;
    --teardown)
      EXTRA_ARGS+=("--teardown")
      shift
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: GCP Project ID could not be determined."
  echo "    Please specify --project-id=<ID> or export PROJECT_ID=<ID>."
  exit 1
fi

# Resolve service URL if not explicitly provided
if [[ -z "${SERVICE_URL}" ]]; then
  echo "      Resolving live Cloud Run service URL for ${SERVICE_NAME}..."
  SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --format="value(status.url)" 2>/dev/null || echo "")
  
  if [[ -z "${SERVICE_URL}" ]]; then
    SERVICE_URL="https://${SERVICE_NAME}-301388663977.${REGION}.run.app"
    echo "      Using fallback Cloud Run service URL: ${SERVICE_URL}"
  else
    echo "      Found live Cloud Run service URL: ${SERVICE_URL}"
  fi
fi

echo "=========================================================================="
echo "    GEMINI ENTERPRISE APP '${APP_ID}' PROVISIONING & AGENT REGISTRATION   "
echo "=========================================================================="
echo " Target Project:     ${PROJECT_ID}"
echo " Discovery Location: ${LOCATION}"
echo " Region:             ${REGION}"
echo " App ID:             ${APP_ID}"
echo " Service URL:        ${SERVICE_URL}"
echo " Auth Provider:      ${AUTH_PROVIDER_ID}"
echo "=========================================================================="

# Execute Python implementation
python3 "${SCRIPT_DIR}/create_gemini_enterprise_app.py" \
  --project-id="${PROJECT_ID}" \
  --location="${LOCATION}" \
  --region="${REGION}" \
  --app-id="${APP_ID}" \
  --display-name="${DISPLAY_NAME}" \
  --solution-type="${SOLUTION_TYPE}" \
  --service-url="${SERVICE_URL}" \
  --service-name="${SERVICE_NAME}" \
  --auth-provider-id="${AUTH_PROVIDER_ID}" \
  "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
