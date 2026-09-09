#!/usr/bin/env bash
set -euo pipefail

# Interactive LinkedIn login on the cluster egress IP, then export cookies
# into jobsrss-collector-files. Do not expose this Service on the Gateway.
#
# Usage:
#   IMAGE_API=... bash deploy/gke/scripts/linkedin-session.sh start
#   bash deploy/gke/scripts/linkedin-session.sh --export
#   bash deploy/gke/scripts/linkedin-session.sh stop

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAMESPACE="${NAMESPACE:-jobsrss}"
ACTION="${1:-start}"
ENV_FILE="${JOBSRSS_ENV_FILE:-$HOME/jobsrss.env.gke}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_REGION="${GCP_REGION:-asia-southeast1}"
AR_REPOSITORY="${AR_REPOSITORY:-jobsrss}"
IMAGE_API="${IMAGE_API:-${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/jobsrss/jobsrss-api:2adea08}"

# shellcheck source=gke-env.sh
source "$(dirname "$0")/gke-env.sh"

apply_login_manifest() {
  local image="${IMAGE_API:?Set IMAGE_API to the existing jobsrss-api image}"
  local work
  work="$(mktemp)"
  kubectl -n "${NAMESPACE}" create configmap linkedin-login-scripts \
    --from-file=start.sh="${ROOT}/linkedin-login/start.sh" \
    --from-file=session.py="${ROOT}/linkedin-login/session.py" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  sed "s#image: jobsrss-api:local#image: ${image}#" \
    "${ROOT}/linkedin-login.yaml" > "${work}"
  kubectl apply -f "${work}"
  rm -f "${work}"
}

case "${ACTION}" in
  start)
    echo "This pod is ClusterIP only. Use kubectl port-forward; do not put it on demo-gateway."
    echo "Same-IP login can still hit a LinkedIn checkpoint because the ASN is Google Cloud."
    echo "You must complete login + 2FA yourself in noVNC."
    echo "A Windows GKE node does not help: egress is still a Google Cloud IP."
    apply_login_manifest
    echo "Waiting for linkedin-login (first start installs xvfb/novnc, ~1-3 minutes)..."
    kubectl -n "${NAMESPACE}" rollout status deploy/linkedin-login --timeout=300s
    echo
    echo "Linux GUI path (browser desktop, no Windows node):"
    echo "  1) Other Cloud Shell tab:"
    echo "       kubectl -n ${NAMESPACE} port-forward svc/linkedin-login 6080:6080"
    echo "  2) Web Preview -> port 6080, then open:"
    echo "       /vnc.html?autoconnect=1&resize=remote"
    echo "  3) In that desktop, log into LinkedIn (complete 2FA) until the feed loads."
    echo "  4) This tab:"
    echo "       bash deploy/gke/scripts/linkedin-session.sh --export"
    echo "       bash deploy/gke/scripts/linkedin-session.sh stop"
    ;;
  --export|export)
    echo "Exporting LinkedIn storage state from the login pod (cookie values are not printed)..."
    kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      python3 -c 'import json,urllib.request; req=urllib.request.Request("http://127.0.0.1:8080/export",method="POST"); print(urllib.request.urlopen(req,timeout=30).read().decode())'
    WORK="$(mktemp -d)"
    kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      cat /session/linkedin_state.json > "${WORK}/linkedin_state.json"
    python3 -c "import json,sys; doc=json.load(open(sys.argv[1],encoding='utf-8')); assert doc.get('cookies'), 'empty cookies'" \
      "${WORK}/linkedin_state.json"
    echo "Wrote $(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('cookies',[])))" "${WORK}/linkedin_state.json") cookies to a temp file"
    if [ ! -f "${ENV_FILE}" ]; then
      echo "Missing ${ENV_FILE}; cannot merge the env secret. Copy the state file yourself."
      echo "Temp file: ${WORK}/linkedin_state.json"
      exit 1
    fi
    sed -i 's/^LINKEDIN_AUTH_ENABLED=.*/LINKEDIN_AUTH_ENABLED=true/' "${ENV_FILE}"
    bash "$(dirname "$0")/apply-secrets.sh" "${ENV_FILE}" "${WORK}"
    kubectl -n "${NAMESPACE}" rollout restart deploy/worker
    echo "Worker restarted with the cluster-minted LinkedIn session."
    echo "Scale the login pod down when finished:"
    echo "  bash deploy/gke/scripts/linkedin-session.sh stop"
    ;;
  stop)
    kubectl -n "${NAMESPACE}" scale deploy/linkedin-login --replicas=0 || true
    echo "linkedin-login replicas=0"
    ;;
  *)
    echo "Usage: $0 {start|--export|stop}"
    exit 1
    ;;
esac
