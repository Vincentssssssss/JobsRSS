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
  iam.googleapis.com \
  cloudbuild.googleapis.com

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

PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)')"
for MEMBER in \
  "serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  "serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="${MEMBER}" \
    --role="roles/artifactregistry.writer" \
    --condition=None >/dev/null
  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="${MEMBER}" \
    --role="roles/container.developer" \
    --condition=None >/dev/null
done

gcloud container clusters get-credentials "${GKE_CLUSTER}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT_ID}"

kubectl apply -f "$(dirname "$0")/../namespace.yaml"

echo
echo "Bootstrap complete."
echo "Cloud Shell next (no GitHub Actions install required):"
echo "  1) nano deploy/gke/.env.gke.example  (save as /tmp/jobsrss.env.gke)"
echo "  2) bash deploy/gke/scripts/apply-secrets.sh /tmp/jobsrss.env.gke"
echo "  3) bash deploy/gke/scripts/cloud-shell-deploy.sh"
echo
echo "Optional GitHub Actions later (also not installed on GKE):"
echo "  Create a key only if you want GitHub-hosted runners:"
echo "  gcloud iam service-accounts keys create cicd-sa.json --iam-account=${SA_EMAIL}"
echo
echo "Artifact Registry: ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPOSITORY}"
