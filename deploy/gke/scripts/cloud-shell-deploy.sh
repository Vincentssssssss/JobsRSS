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
export IMAGE_API="${AR_HOST}/jobsrss-api:${IMAGE_TAG}"
export IMAGE_FRONTEND="${AR_HOST}/jobsrss-frontend:${IMAGE_TAG}"

echo "Project=${GCP_PROJECT_ID} Artifact Registry region=${GCP_REGION}"
echo "Building ${IMAGE_API} and ${IMAGE_FRONTEND} with Cloud Build"

ensure_cloudbuild_worker_sa

gcloud builds submit \
  --project="${GCP_PROJECT_ID}" \
  --service-account="${CLOUDBUILD_SA_RESOURCE}" \
  --config=deploy/gke/cloudbuild.yaml \
  --substitutions="_REGION=${GCP_REGION},_AR_REPOSITORY=${AR_REPOSITORY},_IMAGE_TAG=${IMAGE_TAG}" \
  .

gke_get_credentials
bash deploy/gke/scripts/apply-workloads.sh

echo
echo "Deploy finished on existing cluster ${GKE_CLUSTER}."
echo "Ingress (may take a few minutes):"
kubectl -n jobsrss get ingress jobsrss || true
