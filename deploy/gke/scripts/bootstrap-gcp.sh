#!/usr/bin/env bash
set -euo pipefail

# One-time GCP bootstrap for JobsRSS on GKE Autopilot + Artifact Registry.
# Usage:
#   export GCP_PROJECT_ID=my-project
#   export GCP_REGION=asia-southeast1
#   export GKE_CLUSTER=jobsrss
#   export AR_REPOSITORY=jobsrss
#   bash deploy/gke/scripts/bootstrap-gcp.sh

GCP_PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
GCP_REGION="${GCP_REGION:-asia-southeast1}"
GKE_CLUSTER="${GKE_CLUSTER:-jobsrss}"
AR_REPOSITORY="${AR_REPOSITORY:-jobsrss}"
CICD_SA_NAME="${CICD_SA_NAME:-jobsrss-cicd}"

echo "Using project=${GCP_PROJECT_ID} region=${GCP_REGION} cluster=${GKE_CLUSTER}"

gcloud config set project "${GCP_PROJECT_ID}"

gcloud services enable \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com

if ! gcloud artifacts repositories describe "${AR_REPOSITORY}" \
  --location="${GCP_REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPOSITORY}" \
    --repository-format=docker \
    --location="${GCP_REGION}" \
    --description="JobsRSS container images"
fi

if ! gcloud container clusters describe "${GKE_CLUSTER}" \
  --region="${GCP_REGION}" >/dev/null 2>&1; then
  gcloud container clusters create-auto "${GKE_CLUSTER}" \
    --region="${GCP_REGION}" \
    --release-channel=regular
fi

SA_EMAIL="${CICD_SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${CICD_SA_NAME}" \
    --display-name="JobsRSS GitHub Actions / Jenkins"
fi

gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer" \
  --condition=None >/dev/null

gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/container.developer" \
  --condition=None >/dev/null

gcloud container clusters get-credentials "${GKE_CLUSTER}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT_ID}"

kubectl apply -f "$(dirname "$0")/../namespace.yaml"

echo
echo "Bootstrap complete."
echo "Next:"
echo "  1) Create a JSON key for ${SA_EMAIL} and store it as GitHub secret GCP_SA_KEY"
echo "     gcloud iam service-accounts keys create cicd-sa.json --iam-account=${SA_EMAIL}"
echo "  2) Copy deploy/gke/.env.gke.example, fill values, then:"
echo "     bash deploy/gke/scripts/apply-secrets.sh /path/to/.env.gke /path/to/secrets-dir"
echo "  3) Set GitHub variables GCP_PROJECT_ID, GCP_REGION, GKE_CLUSTER, AR_REPOSITORY"
echo "  4) Run the Deploy to GKE workflow"
echo
echo "Artifact Registry: ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPOSITORY}"
