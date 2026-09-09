#!/usr/bin/env bash
set -euo pipefail

# Apply JobsRSS onto an existing GKE Gateway (HTTPRoute only).
# Usage:
#   IMAGE_API=... IMAGE_FRONTEND=... bash deploy/gke/scripts/apply-workloads.sh

IMAGE_API="${IMAGE_API:?IMAGE_API is required}"
IMAGE_FRONTEND="${IMAGE_FRONTEND:?IMAGE_FRONTEND is required}"
NAMESPACE="${NAMESPACE:-jobsrss}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# shellcheck source=gke-env.sh
source "$(dirname "$0")/gke-env.sh"

if ! kubectl get secret jobsrss-env --namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing secret jobsrss-env in ${NAMESPACE}."
  echo "Run: bash deploy/gke/scripts/apply-secrets.sh /path/to/.env.gke"
  exit 1
fi

allow_jobsrss_on_existing_gateway

kubectl apply -f "${ROOT}/namespace.yaml"

sed \
  -e "s/name: demo-gateway/name: ${JOBSRSS_GATEWAY_NAME}/" \
  -e "s/namespace: default/namespace: ${JOBSRSS_GATEWAY_NAMESPACE}/" \
  -e "s/jobsrss.vincentspace.com/${JOBSRSS_GATEWAY_HOST}/" \
  "${ROOT}/httproute.yaml" > "${WORK}/httproute.yaml"

API_NAME="${IMAGE_API%:*}"
API_TAG="${IMAGE_API##*:}"
FRONTEND_NAME="${IMAGE_FRONTEND%:*}"
FRONTEND_TAG="${IMAGE_FRONTEND##*:}"

# Kustomize refuses absolute paths and files outside the overlay directory.
# Copy manifests into the temp overlay and reference them by relative name.
cp \
  "${ROOT}/postgres.yaml" \
  "${ROOT}/api.yaml" \
  "${ROOT}/worker.yaml" \
  "${ROOT}/frontend.yaml" \
  "${WORK}/"

cat > "${WORK}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: ${NAMESPACE}
resources:
  - postgres.yaml
  - api.yaml
  - worker.yaml
  - frontend.yaml
images:
  - name: jobsrss-api
    newName: ${API_NAME}
    newTag: ${API_TAG}
  - name: jobsrss-frontend
    newName: ${FRONTEND_NAME}
    newTag: ${FRONTEND_TAG}
EOF

kubectl apply -k "${WORK}"
kubectl apply -f "${ROOT}/referencegrant.yaml"
kubectl apply -n "${NAMESPACE}" -f "${ROOT}/healthcheck.yaml"
kubectl apply -f "${WORK}/httproute.yaml"
# Older deploys put this HTTPRoute in default; keep only the jobsrss copy.
kubectl -n "${JOBSRSS_GATEWAY_NAMESPACE}" delete httproute jobsrss --ignore-not-found
kubectl -n "${NAMESPACE}" rollout status statefulset/postgres --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/api --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/frontend --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/worker --timeout=300s

echo "JobsRSS attached to Gateway ${JOBSRSS_GATEWAY_NAMESPACE}/${JOBSRSS_GATEWAY_NAME}"
echo "Open: http://${JOBSRSS_GATEWAY_HOST}/"
echo "Gateway health checks can take 1-2 minutes after this apply."
kubectl -n "${NAMESPACE}" get svc,deploy,statefulset,pods
kubectl -n "${NAMESPACE}" get httproute jobsrss -o wide
kubectl -n "${NAMESPACE}" describe httproute jobsrss | sed -n '/Status:/,$p'
kubectl -n "${JOBSRSS_GATEWAY_NAMESPACE}" get gateway "${JOBSRSS_GATEWAY_NAME}" -o wide
