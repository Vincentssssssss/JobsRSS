#!/usr/bin/env bash
set -euo pipefail

# Apply GKE manifests with image tags from the CI/CD pipeline.
# Uses GKE Gateway API, not Ingress / nginx.
# Usage:
#   IMAGE_API=... IMAGE_FRONTEND=... bash deploy/gke/scripts/apply-workloads.sh

IMAGE_API="${IMAGE_API:?IMAGE_API is required}"
IMAGE_FRONTEND="${IMAGE_FRONTEND:?IMAGE_FRONTEND is required}"
NAMESPACE="${NAMESPACE:-jobsrss}"
GKE_GATEWAY_CLASS="${GKE_GATEWAY_CLASS:-gke-l7-regional-external-managed}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if ! kubectl get secret jobsrss-env --namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing secret jobsrss-env in ${NAMESPACE}."
  echo "Run: bash deploy/gke/scripts/apply-secrets.sh /path/to/.env.gke"
  exit 1
fi

if ! kubectl get gatewayclass "${GKE_GATEWAY_CLASS}" >/dev/null 2>&1; then
  echo "GatewayClass ${GKE_GATEWAY_CLASS} was not found."
  echo "Enable Gateway API on the existing cluster, then retry:"
  echo "  gcloud container clusters update <cluster> --location=<region-or-zone> --gateway-api=standard"
  echo "Or set GKE_GATEWAY_CLASS to one of:"
  kubectl get gatewayclass 2>/dev/null || true
  exit 1
fi

kubectl apply -f "${ROOT}/namespace.yaml"

sed "s/gke-l7-regional-external-managed/${GKE_GATEWAY_CLASS}/g" \
  "${ROOT}/gateway.yaml" > "${WORK}/gateway.yaml"

if [ -n "${JOBSRSS_GATEWAY_HOST:-}" ]; then
  python3 - <<PY
from pathlib import Path
path = Path("${WORK}/gateway.yaml")
text = path.read_text()
needle = "  parentRefs:\n    - name: jobsrss\n      kind: Gateway\n"
insert = (
    "  parentRefs:\n    - name: jobsrss\n      kind: Gateway\n"
    "  hostnames:\n    - ${JOBSRSS_GATEWAY_HOST}\n"
)
if needle not in text:
    raise SystemExit("HTTPRoute parentRefs block not found")
path.write_text(text.replace(needle, insert, 1))
PY
fi

API_NAME="${IMAGE_API%:*}"
API_TAG="${IMAGE_API##*:}"
FRONTEND_NAME="${IMAGE_FRONTEND%:*}"
FRONTEND_TAG="${IMAGE_FRONTEND##*:}"

cat > "${WORK}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: ${NAMESPACE}
resources:
  - ${ROOT}/postgres.yaml
  - ${ROOT}/api.yaml
  - ${ROOT}/worker.yaml
  - ${ROOT}/frontend.yaml
  - gateway.yaml
images:
  - name: jobsrss-api
    newName: ${API_NAME}
    newTag: ${API_TAG}
  - name: jobsrss-frontend
    newName: ${FRONTEND_NAME}
    newTag: ${FRONTEND_TAG}
EOF

kubectl apply -k "${WORK}"
kubectl -n "${NAMESPACE}" rollout status statefulset/postgres --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/api --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/frontend --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/worker --timeout=300s

echo "Workloads rolled out on GKE Gateway class ${GKE_GATEWAY_CLASS}."
kubectl -n "${NAMESPACE}" get gateway,httproute,svc,deploy,statefulset
echo
echo "Gateway address (may take a few minutes):"
kubectl -n "${NAMESPACE}" get gateway jobsrss -o wide
