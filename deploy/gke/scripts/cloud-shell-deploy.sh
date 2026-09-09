#!/usr/bin/env bash
set -euo pipefail

# Deploy JobsRSS from GCP Cloud Shell onto an existing GKE cluster.
# Cloud Shell already has gcloud/kubectl; do not install GitHub Actions here.
# Images are built by Cloud Build (Cloud Shell disk is too small for Playwright).

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "${ROOT}"

# shellcheck source=gke-env.sh
source "$(dirname "$0")/gke-env.sh"

GCP_PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
GCP_REGION="${GCP_REGION:-asia-southeast1}"
GKE_CLUSTER="${GKE_CLUSTER:-}"
AR_REPOSITORY="${AR_REPOSITORY:-jobsrss}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"

if [ -z "${GCP_PROJECT_ID}" ] || [ "${GCP_PROJECT_ID}" = "(unset)" ]; then
  echo "Set GCP_PROJECT_ID or run: gcloud config set project YOUR_PROJECT"
  exit 1
fi

gcloud config set project "${GCP_PROJECT_ID}"

AR_HOST="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPOSITORY}"
SKIP_CLOUD_BUILD="${SKIP_CLOUD_BUILD:-0}"
SKIP_API_BUILD="${SKIP_API_BUILD:-0}"
IMAGE_API_TAG="${IMAGE_API_TAG:-${IMAGE_TAG}}"
export IMAGE_API="${AR_HOST}/jobsrss-api:${IMAGE_API_TAG}"
export IMAGE_FRONTEND="${AR_HOST}/jobsrss-frontend:${IMAGE_TAG}"

echo "Project=${GCP_PROJECT_ID} Artifact Registry region=${GCP_REGION}"

if [ "${SKIP_CLOUD_BUILD}" = "1" ]; then
  echo "Skipping Cloud Build; applying existing ${IMAGE_API} and ${IMAGE_FRONTEND}"
elif [ "${SKIP_API_BUILD}" = "1" ]; then
  echo "Reusing API image ${IMAGE_API}"
  echo "Building ${IMAGE_FRONTEND} with Cloud Build"
  ensure_cloudbuild_worker_sa
  gcloud builds submit \
    --project="${GCP_PROJECT_ID}" \
    --service-account="${CLOUDBUILD_SA_RESOURCE}" \
    --config=deploy/gke/cloudbuild.frontend.yaml \
    --substitutions="_REGION=${GCP_REGION},_AR_REPOSITORY=${AR_REPOSITORY},_IMAGE_TAG=${IMAGE_TAG}" \
    .
else
  echo "Building ${IMAGE_API} and ${IMAGE_FRONTEND} with Cloud Build"
  echo "To reuse an already-built tag later:"
  echo "  IMAGE_TAG=${IMAGE_TAG} SKIP_CLOUD_BUILD=1 bash deploy/gke/scripts/cloud-shell-deploy.sh"
  echo "To rebuild frontend only:"
  echo "  IMAGE_API_TAG=<existing-api-tag> SKIP_API_BUILD=1 bash deploy/gke/scripts/cloud-shell-deploy.sh"
  ensure_cloudbuild_worker_sa
  gcloud builds submit \
    --project="${GCP_PROJECT_ID}" \
    --service-account="${CLOUDBUILD_SA_RESOURCE}" \
    --config=deploy/gke/cloudbuild.yaml \
    --substitutions="_REGION=${GCP_REGION},_AR_REPOSITORY=${AR_REPOSITORY},_IMAGE_TAG=${IMAGE_TAG}" \
    .
fi

gke_get_credentials
enable_gke_gateway_api
bash deploy/gke/scripts/apply-workloads.sh

echo
echo "Deploy finished on existing cluster ${GKE_CLUSTER}."
echo "JobsRSS host: http://${JOBSRSS_GATEWAY_HOST:-<set-after-apply>}/"
echo "HTTPRoute lives in jobsrss and attaches to ${JOBSRSS_GATEWAY_NAMESPACE:-default}/${JOBSRSS_GATEWAY_NAME:-demo-gateway}."
kubectl -n jobsrss get httproute jobsrss || true
kubectl -n jobsrss get deploy,sts,pods || true
kubectl get gateway -A
