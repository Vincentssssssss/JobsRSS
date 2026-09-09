# Shared helpers. Source from other deploy scripts; do not execute directly.

list_gke_clusters() {
  gcloud container clusters list \
    --project="${GCP_PROJECT_ID}" \
    --format="table(name,location,status,locationType)"
}

resolve_existing_cluster() {
  local rows
  mapfile -t rows < <(
    gcloud container clusters list \
      --project="${GCP_PROJECT_ID}" \
      --format="csv[no-heading](name,location,locationType)"
  )

  if [ "${#rows[@]}" -eq 0 ] || [ -z "${rows[0]:-}" ]; then
    echo "No GKE clusters found in project ${GCP_PROJECT_ID}."
    echo "This script will not create a cluster. Use your existing GKE environment."
    exit 1
  fi

  if [ -z "${GKE_CLUSTER:-}" ]; then
    if [ "${#rows[@]}" -eq 1 ]; then
      IFS=',' read -r GKE_CLUSTER GKE_LOCATION GKE_LOCATION_TYPE <<< "${rows[0]}"
    else
      echo "Multiple GKE clusters found. Set GKE_CLUSTER to one of:"
      list_gke_clusters
      echo
      echo "  export GKE_CLUSTER=<name>"
      exit 1
    fi
  else
    local match=""
    local row
    for row in "${rows[@]}"; do
      if [ "${row%%,*}" = "${GKE_CLUSTER}" ]; then
        match="${row}"
        break
      fi
    done
    if [ -z "${match}" ]; then
      echo "Cluster ${GKE_CLUSTER} was not found in ${GCP_PROJECT_ID}."
      echo "Existing clusters:"
      list_gke_clusters
      echo
      echo "Re-run with the existing name, for example:"
      echo "  export GKE_CLUSTER=<name-from-the-list>"
      exit 1
    fi
    IFS=',' read -r GKE_CLUSTER GKE_LOCATION GKE_LOCATION_TYPE <<< "${match}"
  fi

  GKE_LOCATION="${GKE_LOCATION:-${GCP_REGION:-}}"
  if [ "${GKE_LOCATION_TYPE:-}" = "ZONAL" ] || [[ "${GKE_LOCATION}" =~ -[a-z]$ ]]; then
    GKE_LOCATION_FLAG="--zone"
  else
    GKE_LOCATION_FLAG="--region"
  fi

  echo "Using existing cluster ${GKE_CLUSTER} (${GKE_LOCATION_FLAG}=${GKE_LOCATION})"
}

gke_get_credentials() {
  resolve_existing_cluster
  gcloud container clusters get-credentials "${GKE_CLUSTER}" \
    "${GKE_LOCATION_FLAG}"="${GKE_LOCATION}" \
    --project="${GCP_PROJECT_ID}"
}

allow_jobsrss_on_existing_gateway() {
  export JOBSRSS_GATEWAY_NAME="${JOBSRSS_GATEWAY_NAME:-demo-gateway}"
  export JOBSRSS_GATEWAY_NAMESPACE="${JOBSRSS_GATEWAY_NAMESPACE:-default}"

  if ! kubectl get gateway "${JOBSRSS_GATEWAY_NAME}" \
    -n "${JOBSRSS_GATEWAY_NAMESPACE}" >/dev/null 2>&1; then
    echo "Existing Gateway ${JOBSRSS_GATEWAY_NAMESPACE}/${JOBSRSS_GATEWAY_NAME} was not found."
    echo "Set JOBSRSS_GATEWAY_NAME and JOBSRSS_GATEWAY_NAMESPACE to the Gateway you want to reuse."
    kubectl get gateway -A
    exit 1
  fi

  JOBSRSS_GATEWAY_ADDRESS="$(
    kubectl get gateway "${JOBSRSS_GATEWAY_NAME}" \
      -n "${JOBSRSS_GATEWAY_NAMESPACE}" \
      -o jsonpath='{.status.addresses[0].value}'
  )"
  export JOBSRSS_GATEWAY_HOST="${JOBSRSS_GATEWAY_HOST:-jobsrss.vincentspace.com}"

  python3 - <<'PY'
import json, subprocess, os, sys
name = os.environ["JOBSRSS_GATEWAY_NAME"]
ns = os.environ["JOBSRSS_GATEWAY_NAMESPACE"]
raw = subprocess.check_output(
    ["kubectl", "get", "gateway", name, "-n", ns, "-o", "json"]
)
doc = json.loads(raw)
doc.pop("status", None)
changed = False
for listener in doc.get("spec", {}).get("listeners", []):
    namespaces = listener.setdefault("allowedRoutes", {}).setdefault("namespaces", {})
    if namespaces.get("from") != "All":
        namespaces["from"] = "All"
        namespaces.pop("selector", None)
        changed = True
if not changed:
    sys.exit(0)
proc = subprocess.run(
    ["kubectl", "replace", "-f", "-"],
    input=json.dumps(doc),
    text=True,
    check=False,
)
sys.exit(proc.returncode)
PY

  echo "Reusing Gateway ${JOBSRSS_GATEWAY_NAMESPACE}/${JOBSRSS_GATEWAY_NAME}"
  echo "JobsRSS host: http://${JOBSRSS_GATEWAY_HOST}/"
}

enable_gke_gateway_api() {
  resolve_existing_cluster
  if kubectl get gatewayclass >/dev/null 2>&1 \
    && [ "$(kubectl get gatewayclass -o name 2>/dev/null | wc -l)" -gt 0 ]; then
    echo "Gateway API is already enabled:"
    kubectl get gatewayclass
    return
  fi
  echo "Enabling GKE Gateway API (standard) on ${GKE_CLUSTER}..."
  gcloud container clusters update "${GKE_CLUSTER}" \
    "${GKE_LOCATION_FLAG}"="${GKE_LOCATION}" \
    --project="${GCP_PROJECT_ID}" \
    --gateway-api=standard
}

require_ar_image() {
  local image="${1:?image is required}"
  if gcloud artifacts docker images describe "${image}" \
    --project="${GCP_PROJECT_ID}" \
    --quiet >/dev/null 2>&1; then
    echo "Found ${image}"
    return 0
  fi
  echo "Image not in Artifact Registry: ${image}"
  echo "Existing tags (if any):"
  gcloud artifacts docker images list "${image%:*}" \
    --project="${GCP_PROJECT_ID}" \
    --include-tags \
    --limit=15 \
    --format='table(version,tags,createTime)' || true
  echo
  echo "Do not set SKIP_CLOUD_BUILD=1 unless this tag already exists."
  echo "To build frontend only and keep the current API image:"
  echo "  unset SKIP_CLOUD_BUILD"
  echo "  export IMAGE_API_TAG=2adea08"
  echo "  export SKIP_API_BUILD=1"
  echo "  unset IMAGE_TAG"
  echo "  bash deploy/gke/scripts/cloud-shell-deploy.sh"
  exit 1
}

ensure_cloudbuild_worker_sa() {
  CICD_SA_NAME="${CICD_SA_NAME:-jobsrss-cicd}"
  CLOUDBUILD_SA="${CICD_SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
  CLOUDBUILD_SA_RESOURCE="projects/${GCP_PROJECT_ID}/serviceAccounts/${CLOUDBUILD_SA}"
  PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)')"

  gcloud services enable \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    iamcredentials.googleapis.com \
    --project="${GCP_PROJECT_ID}"

  if ! gcloud iam service-accounts describe "${CLOUDBUILD_SA}" \
    --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${CICD_SA_NAME}" \
      --project="${GCP_PROJECT_ID}" \
      --display-name="JobsRSS Cloud Build / deploy"
  fi

  gcloud iam service-accounts enable "${CLOUDBUILD_SA}" \
    --project="${GCP_PROJECT_ID}" >/dev/null

  for ROLE in \
    roles/cloudbuild.builds.builder \
    roles/artifactregistry.writer \
    roles/logging.logWriter \
    roles/storage.objectAdmin \
    roles/container.developer
  do
    gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
      --member="serviceAccount:${CLOUDBUILD_SA}" \
      --role="${ROLE}" \
      --condition=None >/dev/null
  done

  gcloud iam service-accounts add-iam-policy-binding "${CLOUDBUILD_SA}" \
    --project="${GCP_PROJECT_ID}" \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser" >/dev/null

  echo "Cloud Build worker SA: ${CLOUDBUILD_SA}"
}
