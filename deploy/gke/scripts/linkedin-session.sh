#!/usr/bin/env bash
set -euo pipefail

# Interactive LinkedIn login on the cluster egress IP, then export cookies
# into jobsrss-collector-files. Do not expose this Service on the Gateway.
#
# Usage:
#   IMAGE_API=... bash deploy/gke/scripts/linkedin-session.sh start
#   bash deploy/gke/scripts/linkedin-session.sh port-forward
#   bash deploy/gke/scripts/linkedin-session.sh status
#   bash deploy/gke/scripts/linkedin-session.sh --export
#   bash deploy/gke/scripts/linkedin-session.sh stop
#
# start Cloud Builds a thin xvfb/noVNC layer on IMAGE_API (not a Cloud Shell docker build).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT}/.." && pwd)"
NAMESPACE="${NAMESPACE:-jobsrss}"
ACTION="${1:-start}"
ENV_FILE="${JOBSRSS_ENV_FILE:-$HOME/jobsrss.env.gke}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_REGION="${GCP_REGION:-asia-southeast1}"
AR_REPOSITORY="${AR_REPOSITORY:-jobsrss}"
IMAGE_API="${IMAGE_API:-${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/jobsrss/jobsrss-api:2adea08}"
API_TAG="${IMAGE_API##*:}"
LOGIN_TAG="${LOGIN_TAG:-desktop-${API_TAG}-r1}"
IMAGE_LOGIN="${IMAGE_LOGIN:-${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPOSITORY}/jobsrss-linkedin-login:${LOGIN_TAG}}"

# shellcheck source=gke-env.sh
source "$(dirname "$0")/gke-env.sh"

print_checkout() {
  local sha branch
  sha="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  branch="$(git -C "${REPO_ROOT}" branch --show-current 2>/dev/null || echo unknown)"
  echo "linkedin-session checkout=${sha} branch=${branch}"
}

require_current_scripts() {
  if [ -f "${ROOT}/linkedin-login/boot.py" ] && grep -q "linkedin_login_boot = 4" "${ROOT}/linkedin-login/boot.py"; then
    return 0
  fi
  echo "This ~/JobsRSS checkout is too old (missing boot.py supervisor)."
  echo "Cloud Shell 'git pull' on the wrong branch stays 'Already up to date'."
  echo "Fix:"
  echo "  git fetch origin"
  echo "  git checkout cursor/jobs-intelligence-bootstrap-0a74"
  echo "  git reset --hard origin/cursor/jobs-intelligence-bootstrap-0a74"
  echo "  git log -1 --oneline"
  exit 1
}

ensure_login_image() {
  echo "Login image: ${IMAGE_LOGIN}"
  echo "Base API image: ${IMAGE_API}"
  if gcloud artifacts docker images describe "${IMAGE_LOGIN}" \
    --project="${GCP_PROJECT_ID}" --quiet >/dev/null 2>&1; then
    echo "Found ${IMAGE_LOGIN}"
    return 0
  fi
  if [ "${SKIP_LOGIN_BUILD:-}" = "1" ]; then
    require_ar_image "${IMAGE_LOGIN}"
  fi
  require_ar_image "${IMAGE_API}"
  echo "Cloud Building xvfb/noVNC layer from ${IMAGE_API} (do not docker build in Cloud Shell)..."
  ensure_cloudbuild_worker_sa
  (
    cd "${REPO_ROOT}"
    gcloud builds submit \
      --project="${GCP_PROJECT_ID}" \
      --service-account="${CLOUDBUILD_SA_RESOURCE}" \
      --config=deploy/gke/cloudbuild.linkedin-login.yaml \
      --substitutions="_REGION=${GCP_REGION},_AR_REPOSITORY=${AR_REPOSITORY},_API_TAG=${API_TAG},_LOGIN_TAG=${LOGIN_TAG}" \
      .
  )
  require_ar_image "${IMAGE_LOGIN}"
}

apply_login_manifest() {
  local image="${IMAGE_LOGIN:?Set IMAGE_LOGIN to the desktop login image}"
  local work checksum restart_ts
  work="$(mktemp)"
  checksum="$(cat "${ROOT}/linkedin-login/boot.py" "${ROOT}/linkedin-login/session.py" "${ROOT}/linkedin-login/start.sh" | sha256sum | awk '{print $1}')"
  restart_ts="ts-$(date +%s)"
  kubectl -n "${NAMESPACE}" create configmap linkedin-login-scripts \
    --from-file=boot.py="${ROOT}/linkedin-login/boot.py" \
    --from-file=start.sh="${ROOT}/linkedin-login/start.sh" \
    --from-file=session.py="${ROOT}/linkedin-login/session.py" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  sed -e "s#image: jobsrss-api:local#image: ${image}#" \
    -e "s#SCRIPT_CHECKSUM#${checksum}#" \
    -e "s#RESTART_TS#${restart_ts}#" \
    "${ROOT}/linkedin-login.yaml" > "${work}"
  kubectl apply -f "${work}"
  rm -f "${work}"
}

remove_old_login_pods() {
  echo "Removing leftover linkedin-login pods so port-forward cannot hit a dying one..."
  kubectl -n "${NAMESPACE}" scale deploy/linkedin-login --replicas=0 >/dev/null 2>&1 || true
  kubectl -n "${NAMESPACE}" delete pod -l app.kubernetes.io/component=linkedin-login \
    --wait=true --timeout=120s >/dev/null 2>&1 || true
}

wait_novnc() {
  local i
  echo "Waiting until the pod writes /tmp/novnc.ready (real noVNC, not the wait page)..."
  for i in $(seq 1 120); do
    if kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      python3 -c 'import pathlib,sys; sys.exit(0 if pathlib.Path("/tmp/novnc.ready").exists() else 1)' \
      >/dev/null 2>&1; then
      echo "NOVNC_READY :6080 /vnc.html"
      return 0
    fi
    echo "  desktop not ready (${i}/120) — do not port-forward yet"
    sleep 5
  done
  echo "Timed out waiting for noVNC. Recent logs:"
  kubectl -n "${NAMESPACE}" logs deploy/linkedin-login -c login --tail=120 || true
  return 1
}

ready_login_pod() {
  kubectl -n "${NAMESPACE}" get pods -l app.kubernetes.io/component=linkedin-login -o json \
  | python3 -c '
import json, sys
doc = json.load(sys.stdin)
for item in doc.get("items", []):
    if item.get("metadata", {}).get("deletionTimestamp"):
        continue
    status = item.get("status", {})
    if status.get("phase") != "Running":
        continue
    for cs in status.get("containerStatuses") or []:
        if cs.get("name") == "login" and cs.get("ready"):
            print(item["metadata"]["name"])
            raise SystemExit(0)
raise SystemExit(1)
'
}

case "${ACTION}" in
  start)
    print_checkout
    require_current_scripts
    echo "This pod is ClusterIP only. Do not put it on demo-gateway."
    echo "Same-IP login can still hit a LinkedIn checkpoint because the ASN is Google Cloud."
    echo "A Windows GKE node does not help: egress is still a Google Cloud IP."
    echo "Do not open a second terminal for port-forward until this script prints NOVNC_READY."
    ensure_login_image
    remove_old_login_pods
    apply_login_manifest
    echo "Waiting for linkedin-login rollout..."
    kubectl -n "${NAMESPACE}" rollout status deploy/linkedin-login --timeout=600s
    wait_novnc
    POD="$(ready_login_pod)"
    echo
    echo "============================================================"
    echo "NOVNC_READY pod=${POD}"
    echo
    echo "/vnc.html?autoconnect=1&resize=remote  不要在终端里输入。"
    echo "那是浏览器地址栏路径。"
    echo
    echo "现在才开第二个 Cloud Shell 终端（一直挂着，不要 Ctrl+C）："
    echo "  bash deploy/gke/scripts/linkedin-session.sh port-forward"
    echo "或："
    echo "  kubectl -n ${NAMESPACE} port-forward pod/${POD} 6080:6080"
    echo "不要再用 svc/linkedin-login（会误连正在退出的旧 Pod）。"
    echo
    echo "然后：Web Preview -> Change port -> 6080 -> Preview"
    echo "地址栏改成（只改路径，主机名保持 cloudshell.dev）："
    echo "  https://6080-cs-xxxx.cloudshell.dev/vnc.html?autoconnect=1&resize=remote"
    echo
    echo "登录 LinkedIn 直到 Feed 出现，再回到这个终端："
    echo "  bash deploy/gke/scripts/linkedin-session.sh --export"
    echo "  bash deploy/gke/scripts/linkedin-session.sh stop"
    echo "============================================================"
    ;;
  port-forward|pf)
    print_checkout
    wait_novnc
    POD="$(ready_login_pod)"
    echo "Forwarding pod/${POD} 6080:6080  (leave this running; use Web Preview on 6080)"
    exec kubectl -n "${NAMESPACE}" port-forward "pod/${POD}" 6080:6080
    ;;
  status)
    print_checkout
    echo "--- pods ---"
    kubectl -n "${NAMESPACE}" get pods -l app.kubernetes.io/component=linkedin-login -o wide
    echo
    echo "--- /tmp/novnc.ready and :6080 ---"
    kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      python3 -c 'import pathlib,urllib.request; p=pathlib.Path("/tmp/novnc.ready"); print("novnc.ready", p.exists()); r=urllib.request.urlopen("http://127.0.0.1:6080/vnc.html",timeout=5); print("vnc.html", r.status, r.headers.get("content-type"), "bytes", len(r.read()))' \
      || echo "6080 is not serving yet, or the login pod is not running"
    echo
    echo "--- recent login logs ---"
    kubectl -n "${NAMESPACE}" logs deploy/linkedin-login -c login --tail=80 || true
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
    echo "Usage: $0 {start|port-forward|status|--export|stop}"
    exit 1
    ;;
esac
