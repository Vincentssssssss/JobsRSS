#!/usr/bin/env bash
set -euo pipefail

# Apply GKE manifests with image tags from the CI/CD pipeline.
# Usage:
#   IMAGE_API=... IMAGE_FRONTEND=... bash deploy/gke/scripts/apply-workloads.sh

IMAGE_API="${IMAGE_API:?IMAGE_API is required}"
IMAGE_FRONTEND="${IMAGE_FRONTEND:?IMAGE_FRONTEND is required}"
NAMESPACE="${NAMESPACE:-jobsrss}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if ! kubectl get secret jobsrss-env --namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing secret jobsrss-env in ${NAMESPACE}."
  echo "Run: bash deploy/gke/scripts/apply-secrets.sh /path/to/.env.gke"
  exit 1
fi

kubectl apply -f "${ROOT}/namespace.yaml"

if [ -z "${JOBSRSS_INGRESS_HOST:-}" ]; then
  NGINX_IP="$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  if [ -n "${NGINX_IP}" ]; then
    JOBSRSS_INGRESS_HOST="jobsrss.${NGINX_IP}.sslip.io"
  else
    JOBSRSS_INGRESS_HOST="jobsrss.local"
    echo "ingress-nginx has no LoadBalancer IP yet; host=${JOBSRSS_INGRESS_HOST}"
  fi
fi
echo "Ingress host: ${JOBSRSS_INGRESS_HOST}"

sed "s/jobsrss.example.invalid/${JOBSRSS_INGRESS_HOST}/g" \
  "${ROOT}/ingress.yaml" > "${WORK}/ingress.yaml"

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
  - ingress.yaml
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

echo "Workloads rolled out."
kubectl -n "${NAMESPACE}" get ingress,svc,deploy,statefulset
