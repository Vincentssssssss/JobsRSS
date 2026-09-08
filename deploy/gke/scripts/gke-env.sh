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
