#!/usr/bin/env bash
# ==============================================================================
# Script: register_adk_agent.sh
# Purpose: Registers the ADK Agent in Gemini Enterprise App 'fdedemoapp'.
# Documentation: https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"
APP_ID="fdedemoapp"
LOCATION="global"
DISPLAY_NAME="Travel Concierge"
DESCRIPTION="Travel Concierge Agent for flight, hotel, and restaurant booking"
REASONING_ENGINE=""
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --project-id=*)
      PROJECT_ID="${1#*=}"
      shift
      ;;
    --app-id=*)
      APP_ID="${1#*=}"
      shift
      ;;
    --location=*)
      LOCATION="${1#*=}"
      shift
      ;;
    --display-name=*)
      DISPLAY_NAME="${1#*=}"
      shift
      ;;
    --description=*)
      DESCRIPTION="${1#*=}"
      shift
      ;;
    --reasoning-engine=*)
      REASONING_ENGINE="${1#*=}"
      shift
      ;;
    --list)
      LIST_ONLY=true
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: Google Cloud PROJECT_ID must be specified."
  exit 1
fi

export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"

echo "=========================================================================="
echo "    REGISTERING ADK AGENT IN GEMINI ENTERPRISE (FDEDEMOAPP)               "
echo "=========================================================================="
echo " Project ID:     ${PROJECT_ID}"
echo " App ID:         ${APP_ID}"
echo " Location:       ${LOCATION}"
echo " Agent Name:     ${DISPLAY_NAME}"
echo "=========================================================================="

ARGS=(
  "--project-id=${PROJECT_ID}"
  "--app-id=${APP_ID}"
  "--location=${LOCATION}"
  "--display-name=${DISPLAY_NAME}"
  "--description=${DESCRIPTION}"
)

if [[ -n "${REASONING_ENGINE}" ]]; then
  ARGS+=("--reasoning-engine=${REASONING_ENGINE}")
fi

if [[ "${LIST_ONLY}" == "true" ]]; then
  ARGS+=("--list-only")
fi

python3 scripts/register_adk_agent.py "${ARGS[@]}"
