#!/usr/bin/env bash
set -euo pipefail

# Create/update Kubernetes secrets for JobsRSS.
# Usage:
#   bash deploy/gke/scripts/apply-secrets.sh /path/to/.env.gke [/path/to/secrets-dir]
#
# secrets-dir may contain:
#   linkedin_state.json
#   liepin_state.json

ENV_FILE="${1:?Usage: apply-secrets.sh /path/to/.env.gke [/path/to/secrets-dir]}"
SECRETS_DIR="${2:-}"
NAMESPACE="${NAMESPACE:-jobsrss}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

kubectl apply -f "$(dirname "$0")/../namespace.yaml"

kubectl create secret generic jobsrss-env \
  --namespace "${NAMESPACE}" \
  --from-env-file="${ENV_FILE}" \
  --dry-run=client -o yaml | kubectl apply -f -

from_file_args=()
if [ -n "${SECRETS_DIR}" ]; then
  if [ -f "${SECRETS_DIR}/linkedin_state.json" ]; then
    from_file_args+=(--from-file="linkedin_state.json=${SECRETS_DIR}/linkedin_state.json")
  fi
  if [ -f "${SECRETS_DIR}/liepin_state.json" ]; then
    from_file_args+=(--from-file="liepin_state.json=${SECRETS_DIR}/liepin_state.json")
  fi
fi

if [ "${#from_file_args[@]}" -gt 0 ]; then
  kubectl create secret generic jobsrss-collector-files \
    --namespace "${NAMESPACE}" \
    "${from_file_args[@]}" \
    --dry-run=client -o yaml | kubectl apply -f -
else
  echo "No collector session files provided; worker will run without LinkedIn/Liepin cookies."
fi

echo "Secrets applied in namespace ${NAMESPACE}."
