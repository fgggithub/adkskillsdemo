#!/usr/bin/env bash
# ==============================================================================
# Script: setup_auth_platform.sh
# Purpose: Configure Google Auth Platform and OAuth clients for Gemini Enterprise.
# Documentation:
#   - https://docs.cloud.google.com/docs/authentication
#   - https://support.google.com/cloud/answer/15549257
# Solution Tag: FDEDEMO
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo '')}"
REGION="${REGION:-us-central1}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "[-] ERROR: Google Cloud PROJECT_ID could not be determined."
  echo "    Please run 'gcloud config set project <PROJECT_ID>' or export PROJECT_ID=<PROJECT_ID>."
  exit 1
fi

export PATH="${HOME}/.local/bin:${PATH}"

echo "=========================================================================="
echo "    CONFIGURING GOOGLE AUTH PLATFORM & OAUTH CLIENTS (GEMINI ENTERPRISE)  "
echo "=========================================================================="
echo " Target Project: ${PROJECT_ID}"
echo " Region:         ${REGION}"

python3 "${SCRIPT_DIR}/setup_auth_platform.py" \
  --project-id="${PROJECT_ID}" \
  --region="${REGION}" \
  "$@"
