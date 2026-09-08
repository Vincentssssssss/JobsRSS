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

if ! kubectl -n "${NAMESPACE}" get deploy/worker >/dev/null 2>&1; then
  echo
  echo "No JobsRSS Deployments exist yet (api/frontend/worker were not found)."
  echo "apply-secrets.sh only writes Kubernetes Secrets. It does not start pods."
  echo "Do not run: kubectl -n ${NAMESPACE} rollout restart deploy/worker"
  echo
  PROJECT_HINT="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
  echo "Next, from the repo root, build images and create the workloads:"
  echo "  export GCP_PROJECT_ID=${PROJECT_HINT:-your-project-id}"
  echo "  export JOBSRSS_GATEWAY_NAME=demo-gateway"
  echo "  export JOBSRSS_GATEWAY_NAMESPACE=default"
  echo "  export JOBSRSS_GATEWAY_HOST=jobsrss.vincentspace.com"
  echo "  bash deploy/gke/scripts/cloud-shell-deploy.sh"
  echo
  echo "Cloud Build can take 15-30 minutes. After that:"
  echo "  kubectl -n ${NAMESPACE} get pods"
else
  echo "Workloads already exist. Restart them only if you want pods to reload this secret:"
  echo "  kubectl -n ${NAMESPACE} rollout restart deploy/api deploy/frontend deploy/worker"
fi
