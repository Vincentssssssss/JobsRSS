#!/usr/bin/env bash
set -euo pipefail

# Interactive Windows desktop for LinkedIn login, on the same Cloud NAT egress
# IP as the GKE worker.
#
# Windows containers do not support RDP or GUI (Microsoft removed both by
# design), so a "Windows pod" cannot give an interactive desktop. This uses a
# GCE Windows VM in the existing VPC. No new cluster, no new VPC, no new subnet.
#
# Usage:
#   bash deploy/gke/scripts/windows-login-vm.sh create
#   bash deploy/gke/scripts/windows-login-vm.sh password
#   bash deploy/gke/scripts/windows-login-vm.sh tunnel     # run on your laptop
#   bash deploy/gke/scripts/windows-login-vm.sh export
#   bash deploy/gke/scripts/windows-login-vm.sh stop
#   bash deploy/gke/scripts/windows-login-vm.sh delete

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAMESPACE="${NAMESPACE:-jobsrss}"
ACTION="${1:-status}"
ENV_FILE="${JOBSRSS_ENV_FILE:-$HOME/jobsrss.env.gke}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
GKE_CLUSTER="${GKE_CLUSTER:-asp-gke-dev-gke-d9df}"
GKE_ZONE="${GKE_ZONE:-asia-southeast1-a}"
VM_NAME="${VM_NAME:-jobsrss-win-login}"
VM_ZONE="${VM_ZONE:-${GKE_ZONE}}"
VM_REGION="${VM_REGION:-${VM_ZONE%-*}}"
VM_MACHINE="${VM_MACHINE:-e2-standard-4}"
VM_TAG="jobsrss-win-login"
FIREWALL_RULE="${FIREWALL_RULE:-jobsrss-iap-rdp}"
WINDOWS_USER="${WINDOWS_USER:-jobsrss}"

resolve_cluster_network() {
  local row
  row="$(gcloud container clusters describe "${GKE_CLUSTER}" \
    --zone="${GKE_ZONE}" --project="${GCP_PROJECT_ID}" \
    --format='csv[no-heading](network,subnetwork)')"
  CLUSTER_NETWORK="${row%%,*}"
  CLUSTER_SUBNET="${row##*,}"
  if [ -z "${CLUSTER_NETWORK}" ] || [ -z "${CLUSTER_SUBNET}" ]; then
    echo "Could not read network/subnetwork from cluster ${GKE_CLUSTER}."
    exit 1
  fi
  echo "Cluster network=${CLUSTER_NETWORK} subnet=${CLUSTER_SUBNET} region=${VM_REGION}"
}

require_cloud_nat() {
  local nats
  nats="$(gcloud compute routers list \
    --project="${GCP_PROJECT_ID}" \
    --filter="region:(${VM_REGION}) AND network:(${CLUSTER_NETWORK})" \
    --format='value(name)' || true)"
  if [ -z "${nats}" ]; then
    echo
    echo "No Cloud Router found in ${VM_REGION} on ${CLUSTER_NETWORK}."
    echo "A VM with no external IP then has no internet and cannot install Chromium,"
    echo "and it would not share the GKE egress IP either."
    echo "Ask whoever owns this VPC which router/NAT the GKE nodes use, or create the"
    echo "VM with an external IP by re-running with: VM_EXTERNAL_IP=1"
    if [ "${VM_EXTERNAL_IP:-0}" != "1" ]; then
      exit 1
    fi
  else
    echo "Cloud Routers in ${VM_REGION}: ${nats}"
    echo "The VM uses the same NAT as the GKE nodes, so LinkedIn sees the same egress IP."
  fi
}

ensure_iap_firewall() {
  if gcloud compute firewall-rules describe "${FIREWALL_RULE}" \
    --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    echo "Firewall rule ${FIREWALL_RULE} already exists"
    return
  fi
  echo "Creating ${FIREWALL_RULE} (IAP RDP range only, scoped to tag ${VM_TAG})"
  gcloud compute firewall-rules create "${FIREWALL_RULE}" \
    --project="${GCP_PROJECT_ID}" \
    --network="${CLUSTER_NETWORK}" \
    --direction=INGRESS \
    --action=allow \
    --rules=tcp:3389 \
    --source-ranges=35.235.240.0/20 \
    --target-tags="${VM_TAG}" \
    --description="IAP TCP forwarding RDP for the JobsRSS LinkedIn login VM"
}

case "${ACTION}" in
  create)
    resolve_cluster_network
    require_cloud_nat
    ensure_iap_firewall
    if gcloud compute instances describe "${VM_NAME}" \
      --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
      echo "VM ${VM_NAME} already exists; starting it"
      gcloud compute instances start "${VM_NAME}" \
        --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}"
    else
      ADDRESS_FLAG="--no-address"
      if [ "${VM_EXTERNAL_IP:-0}" = "1" ]; then
        ADDRESS_FLAG=""
        echo "WARNING: creating with an external IP. LinkedIn will NOT see the GKE egress IP."
      fi
      gcloud compute instances create "${VM_NAME}" \
        --project="${GCP_PROJECT_ID}" \
        --zone="${VM_ZONE}" \
        --machine-type="${VM_MACHINE}" \
        --subnet="${CLUSTER_SUBNET}" \
        ${ADDRESS_FLAG} \
        --tags="${VM_TAG}" \
        --image-family=windows-2022 \
        --image-project=windows-cloud \
        --boot-disk-size=80GB \
        --boot-disk-type=pd-balanced \
        --metadata-from-file="windows-startup-script-ps1=${ROOT}/windows-login/startup.ps1,jobsrss-session-py=${ROOT}/linkedin-login/session.py"
    fi
    echo
    echo "Windows boots and installs Python/Playwright in the background (~10 min)."
    echo "Next:"
    echo "  bash deploy/gke/scripts/windows-login-vm.sh password"
    echo "  bash deploy/gke/scripts/windows-login-vm.sh tunnel   # on your laptop"
    ;;
  password)
    echo "Creating/resetting the Windows account ${WINDOWS_USER}."
    echo "Copy the password now; it is shown once and is not stored in this repo."
    gcloud compute reset-windows-password "${VM_NAME}" \
      --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}" --user="${WINDOWS_USER}"
    ;;
  tunnel)
    echo "Run this on your LAPTOP, not in Cloud Shell (Cloud Shell has no RDP client)."
    echo "Keep it running, then point Microsoft Remote Desktop at 127.0.0.1:13389"
    echo "with user ${WINDOWS_USER} and the password from the 'password' step."
    exec gcloud compute start-iap-tunnel "${VM_NAME}" 3389 \
      --local-host-port=localhost:13389 \
      --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}"
    ;;
  export)
    WORK="$(mktemp -d)"
    echo "Copying linkedin_state.json off the VM (cookie values are not printed)..."
    gcloud compute scp "${VM_NAME}:C:\\jobsrss\\linkedin_state.json" \
      "${WORK}/linkedin_state.json" \
      --tunnel-through-iap --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}"
    python3 -c "import json,sys; doc=json.load(open(sys.argv[1],encoding='utf-8')); assert doc.get('cookies'), 'empty cookies'" \
      "${WORK}/linkedin_state.json"
    echo "Cookies: $(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('cookies',[])))" "${WORK}/linkedin_state.json")"
    if [ ! -f "${ENV_FILE}" ]; then
      echo "Missing ${ENV_FILE}; state file left at ${WORK}/linkedin_state.json"
      exit 1
    fi
    sed -i 's/^LINKEDIN_AUTH_ENABLED=.*/LINKEDIN_AUTH_ENABLED=true/' "${ENV_FILE}"
    bash "$(dirname "$0")/apply-secrets.sh" "${ENV_FILE}" "${WORK}"
    kubectl -n "${NAMESPACE}" rollout restart deploy/worker
    echo "Worker restarted with the Windows-minted LinkedIn session."
    echo "Stop the VM so it stops billing:"
    echo "  bash deploy/gke/scripts/windows-login-vm.sh stop"
    ;;
  stop)
    gcloud compute instances stop "${VM_NAME}" \
      --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}"
    echo "Stopped. Disk still bills; use 'delete' when the cookie is exported."
    ;;
  delete)
    gcloud compute instances delete "${VM_NAME}" \
      --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}" --quiet
    echo "Deleted ${VM_NAME}. Firewall rule ${FIREWALL_RULE} was left in place."
    ;;
  status)
    gcloud compute instances describe "${VM_NAME}" \
      --zone="${VM_ZONE}" --project="${GCP_PROJECT_ID}" \
      --format='table(name,status,machineType.basename(),networkInterfaces[0].networkIP)' \
      2>/dev/null || echo "VM ${VM_NAME} does not exist yet"
    ;;
  *)
    echo "Usage: $0 {create|password|tunnel|export|stop|delete|status}"
    exit 1
    ;;
esac
