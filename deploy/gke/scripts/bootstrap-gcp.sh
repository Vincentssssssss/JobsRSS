#!/usr/bin/env bash
set -euo pipefail

# Attach JobsRSS to an existing GKE cluster. Never creates a cluster.
# Usage (Cloud Shell, from the repo root):
#   export GCP_PROJECT_ID=my-project
#   export GKE_CLUSTER=your-existing-cluster   # optional if the project has only one
#   bash deploy/gke/scripts/bootstrap-gcp.sh

GCP_PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
GCP_REGION="${GCP_REGION:-asia-southeast1}"
GKE_CLUSTER="${GKE_CLUSTER:-}"
AR_REPOSITORY="${AR_REPOSITORY:-jobsrss}"
CICD_SA_NAME="${CICD_SA_NAME:-jobsrss-cicd}"

# shellcheck source=gke-env.sh
source "$(dirname "$0")/gke-env.sh"

echo "Using project=${GCP_PROJECT_ID} (will not create a GKE cluster)"

gcloud config set project "${GCP_PROJECT_ID}"

gcloud services enable \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  cloudbuild.googleapis.com

if ! gcloud artifacts repositories describe "${AR_REPOSITORY}" \
  --location="${GCP_REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPOSITORY}" \
    --repository-format=docker \
    --location="${GCP_REGION}" \
    --description="JobsRSS container images"
fi

ensure_cloudbuild_worker_sa
gke_get_credentials
enable_gke_gateway_api
kubectl apply -f "$(dirname "$0")/../namespace.yaml"

echo
echo "Bootstrap complete. Attached to existing cluster ${GKE_CLUSTER}."
echo "Next in Cloud Shell:"
echo "  1) bash deploy/gke/scripts/write-env-gke.sh && nano ~/jobsrss.env.gke"
echo "  2) bash deploy/gke/scripts/apply-secrets.sh ~/jobsrss.env.gke"
echo "  3) bash deploy/gke/scripts/cloud-shell-deploy.sh"
echo
echo "Artifact Registry: ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPOSITORY}"
