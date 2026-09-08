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
GCP_NETWORK="${GCP_NETWORK:-}"
GCP_SUBNETWORK="${GCP_SUBNETWORK:-}"
GCP_SUBNET_RANGE="${GCP_SUBNET_RANGE:-10.88.0.0/20}"
GCP_PODS_RANGE="${GCP_PODS_RANGE:-10.89.0.0/16}"
GCP_SERVICES_RANGE="${GCP_SERVICES_RANGE:-10.90.0.0/20}"

echo "Using project=${GCP_PROJECT_ID} region=${GCP_REGION} cluster=${GKE_CLUSTER}"

network_exists() {
  gcloud compute networks describe "$1" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1
}

subnet_exists() {
  gcloud compute networks subnets describe "$1" \
    --region="${GCP_REGION}" \
    --project="${GCP_PROJECT_ID}" >/dev/null 2>&1
}

ensure_jobsrss_vpc() {
  GCP_NETWORK="${GCP_NETWORK:-jobsrss}"
  GCP_SUBNETWORK="${GCP_SUBNETWORK:-jobsrss-${GCP_REGION}}"
  CLUSTER_SECONDARY_RANGE="jobsrss-pods"
  SERVICES_SECONDARY_RANGE="jobsrss-services"

  if ! network_exists "${GCP_NETWORK}"; then
    echo "No default VPC in this project. Creating ${GCP_NETWORK}..."
    gcloud compute networks create "${GCP_NETWORK}" \
      --project="${GCP_PROJECT_ID}" \
      --subnet-mode=custom \
      --bgp-routing-mode=regional
  fi

  if ! subnet_exists "${GCP_SUBNETWORK}"; then
    echo "Creating subnet ${GCP_SUBNETWORK} in ${GCP_REGION}..."
    gcloud compute networks subnets create "${GCP_SUBNETWORK}" \
      --project="${GCP_PROJECT_ID}" \
      --network="${GCP_NETWORK}" \
      --region="${GCP_REGION}" \
      --range="${GCP_SUBNET_RANGE}" \
      --secondary-range="${CLUSTER_SECONDARY_RANGE}=${GCP_PODS_RANGE},${SERVICES_SECONDARY_RANGE}=${GCP_SERVICES_RANGE}"
  fi
}

resolve_gke_network() {
  if [ -n "${GCP_NETWORK}" ] && [ -n "${GCP_SUBNETWORK}" ]; then
    echo "Using caller network=${GCP_NETWORK} subnet=${GCP_SUBNETWORK}"
    return
  fi

  if network_exists default; then
    GCP_NETWORK="default"
    GCP_SUBNETWORK="${GCP_SUBNETWORK:-}"
    echo "Using default VPC"
    return
  fi

  mapfile -t regional_subnets < <(
    gcloud compute networks subnets list \
      --project="${GCP_PROJECT_ID}" \
      --filter="region:(${GCP_REGION})" \
      --format="value(name,network.basename())"
  )

  if [ "${#regional_subnets[@]}" -eq 1 ]; then
    GCP_SUBNETWORK="${regional_subnets[0]%%$'\t'*}"
    GCP_NETWORK="${regional_subnets[0]#*$'\t'}"
    echo "Using the only ${GCP_REGION} subnet: ${GCP_NETWORK}/${GCP_SUBNETWORK}"
    return
  fi

  if [ "${#regional_subnets[@]}" -gt 1 ] && [ -z "${GCP_NETWORK}" ]; then
    echo "This project has no network named default, and more than one subnet in ${GCP_REGION}:"
    printf '  %s\n' "${regional_subnets[@]}"
    echo "Re-run with:"
    echo "  export GCP_NETWORK=<network>"
    echo "  export GCP_SUBNETWORK=<subnet>"
    exit 1
  fi

  ensure_jobsrss_vpc
}

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
  resolve_gke_network
  create_args=(
    --region="${GCP_REGION}"
    --release-channel=regular
    --network="${GCP_NETWORK}"
  )
  if [ -n "${GCP_SUBNETWORK}" ]; then
    create_args+=(--subnetwork="${GCP_SUBNETWORK}")
  fi
  if [ -n "${CLUSTER_SECONDARY_RANGE:-}" ]; then
    create_args+=(--cluster-secondary-range-name="${CLUSTER_SECONDARY_RANGE}")
  fi
  if [ -n "${SERVICES_SECONDARY_RANGE:-}" ]; then
    create_args+=(--services-secondary-range-name="${SERVICES_SECONDARY_RANGE}")
  fi
  echo "Creating Autopilot cluster on network=${GCP_NETWORK} subnet=${GCP_SUBNETWORK:-<auto>}"
  gcloud container clusters create-auto "${GKE_CLUSTER}" "${create_args[@]}"
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
