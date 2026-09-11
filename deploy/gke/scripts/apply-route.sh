#!/usr/bin/env bash
set -euo pipefail

# Attach JobsRSS to the existing Gateway by hostname. Does not rebuild images.
# Usage:
#   bash deploy/gke/scripts/apply-route.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=gke-env.sh
source "$(dirname "$0")/gke-env.sh"

export JOBSRSS_GATEWAY_NAME="${JOBSRSS_GATEWAY_NAME:-demo-gateway}"
export JOBSRSS_GATEWAY_NAMESPACE="${JOBSRSS_GATEWAY_NAMESPACE:-default}"
export JOBSRSS_GATEWAY_HOST="${JOBSRSS_GATEWAY_HOST:-jobsrss.vincentspace.com}"

allow_jobsrss_on_existing_gateway
export JOBSRSS_GATEWAY_HOST="${JOBSRSS_GATEWAY_HOST:-jobsrss.vincentspace.com}"

kubectl apply -f "${ROOT}/namespace.yaml"
kubectl apply -f "${ROOT}/referencegrant.yaml"
kubectl apply -n jobsrss -f "${ROOT}/healthcheck.yaml"

WORK="$(mktemp)"
sed \
  -e "s/name: demo-gateway/name: ${JOBSRSS_GATEWAY_NAME}/" \
  -e "s/namespace: default/namespace: ${JOBSRSS_GATEWAY_NAMESPACE}/" \
  -e "s/jobsrss.vincentspace.com/${JOBSRSS_GATEWAY_HOST}/" \
  "${ROOT}/httproute.yaml" > "${WORK}"

kubectl apply -f "${WORK}"
rm -f "${WORK}"
kubectl -n "${JOBSRSS_GATEWAY_NAMESPACE}" delete httproute jobsrss --ignore-not-found

echo
echo "HTTPRoute should now match Host: ${JOBSRSS_GATEWAY_HOST}"
kubectl -n jobsrss get httproute jobsrss -o wide
kubectl -n jobsrss describe httproute jobsrss | sed -n '/Status:/,$p'
echo
if ! kubectl -n jobsrss get svc api svc/frontend >/dev/null 2>&1; then
  echo "jobsrss Service/Pods are not deployed yet. The hostname will keep"
  echo "falling through to the demo app until you run:"
  echo "  bash deploy/gke/scripts/cloud-shell-deploy.sh"
  kubectl -n jobsrss get all || true
fi
echo "Open: http://${JOBSRSS_GATEWAY_HOST}/"
echo "Raw Gateway IP still serves the demo app."
