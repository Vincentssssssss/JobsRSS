#!/usr/bin/env bash
set -euo pipefail

# Recreate the GKE env file in $HOME (Cloud Shell /tmp is wiped).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/jobsrss.env.gke}"

cp "${ROOT}/.env.gke.example" "${DEST}"
echo "Wrote ${DEST}"
echo "Edit LLM_API_KEY, then:"
echo "  nano ${DEST}"
echo "  bash deploy/gke/scripts/apply-secrets.sh ${DEST}"
