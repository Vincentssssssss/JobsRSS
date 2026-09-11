#!/usr/bin/env bash
set -euo pipefail

# Log in locally in a real browser, then push the session cookie straight into
# the cluster so the worker keeps refreshing jobs on its own.
#
# Runs from any machine with kubectl + gcloud. Does not need ~/jobsrss.env.gke
# and never prints cookie values.
#
# Usage:
#   bash deploy/gke/scripts/cookie-to-k8s.sh desktop      # cluster-IP browser, drive it locally
#   bash deploy/gke/scripts/cookie-to-k8s.sh from-pod     # take that pod's cookie into the secret
#   bash deploy/gke/scripts/cookie-to-k8s.sh              # mint locally instead (laptop egress IP)
#   bash deploy/gke/scripts/cookie-to-k8s.sh mint liepin
#   bash deploy/gke/scripts/cookie-to-k8s.sh push linkedin ~/secrets/linkedin_state.json
#   bash deploy/gke/scripts/cookie-to-k8s.sh check
#
# desktop + from-pod keep the GKE egress IP. Plain mint uses your laptop IP,
# which LinkedIn usually rejects when the worker later reuses the cookie.

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
NAMESPACE="${NAMESPACE:-jobsrss}"
ACTION="${1:-all}"
SITE="${2:-linkedin}"
STATE_FILE="${3:-$HOME/secrets/${SITE}_state.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

case "${SITE}" in
  linkedin) FLAG_KEY="LINKEDIN_AUTH_ENABLED" ;;
  liepin) FLAG_KEY="LIEPIN_AUTH_ENABLED" ;;
  *) echo "Unsupported site: ${SITE} (use linkedin or liepin)"; exit 1 ;;
esac
SECRET_KEY="${SITE}_state.json"

require_cluster() {
  if ! kubectl -n "${NAMESPACE}" get deploy/worker >/dev/null 2>&1; then
    echo "Cannot see deploy/worker in namespace ${NAMESPACE}."
    echo "Point kubectl at the cluster first:"
    echo "  gcloud container clusters get-credentials asp-gke-dev-gke-d9df \\"
    echo "    --zone=asia-southeast1-a --project=gcp-bcgx-dev-vincents-d597"
    exit 1
  fi
}

mint_state() {
  echo "NOTE: this mints the cookie on THIS machine's IP."
  echo "LinkedIn usually rejects it once the GKE worker reuses it."
  echo "For the cluster egress IP use: cookie-to-k8s.sh desktop"
  if ! "${PYTHON_BIN}" -c "import playwright" >/dev/null 2>&1; then
    echo
    echo "Playwright is missing locally. Homebrew Python blocks plain pip (PEP 668),"
    echo "so use a virtualenv:"
    echo "  python3 -m venv ~/.jobsrss-venv"
    echo "  ~/.jobsrss-venv/bin/pip install playwright"
    echo "  ~/.jobsrss-venv/bin/playwright install chromium"
    echo "  PYTHON_BIN=~/.jobsrss-venv/bin/python bash $0 ${ACTION} ${SITE}"
    exit 1
  fi
  mkdir -p "$(dirname "${STATE_FILE}")"
  echo "A browser window will open. Log into ${SITE} until the feed/home page loads,"
  echo "then come back here and press Enter."
  "${PYTHON_BIN}" "${REPO_ROOT}/backend/scripts/export_storage_state.py" \
    --site "${SITE}" \
    --mode interactive \
    --out "${STATE_FILE}"
}

push_state() {
  require_cluster
  if [ ! -f "${STATE_FILE}" ]; then
    echo "Missing ${STATE_FILE}. Mint it first:"
    echo "  bash deploy/gke/scripts/cookie-to-k8s.sh mint ${SITE}"
    exit 1
  fi
  "${PYTHON_BIN}" - "${STATE_FILE}" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
cookies = doc.get("cookies") or []
if not cookies:
    raise SystemExit("state file has no cookies; log in again before pushing")
print(f"local state file has {len(cookies)} cookies")
PY

  if ! kubectl -n "${NAMESPACE}" get secret jobsrss-collector-files >/dev/null 2>&1; then
    kubectl -n "${NAMESPACE}" create secret generic jobsrss-collector-files \
      --from-file="${SECRET_KEY}=${STATE_FILE}"
  else
    local encoded
    encoded="$("${PYTHON_BIN}" -c "import base64,sys;sys.stdout.write(base64.b64encode(open(sys.argv[1],'rb').read()).decode())" "${STATE_FILE}")"
    kubectl -n "${NAMESPACE}" patch secret jobsrss-collector-files \
      --type=merge -p "{\"data\":{\"${SECRET_KEY}\":\"${encoded}\"}}" >/dev/null
  fi
  echo "Secret jobsrss-collector-files now has: $(kubectl -n "${NAMESPACE}" get secret jobsrss-collector-files -o json | "${PYTHON_BIN}" -c 'import json,sys;print(" ".join(sorted((json.load(sys.stdin).get("data") or {}))))')"

  kubectl -n "${NAMESPACE}" patch secret jobsrss-env \
    --type=merge -p "{\"stringData\":{\"${FLAG_KEY}\":\"true\"}}" >/dev/null
  echo "${FLAG_KEY}=true"

  kubectl -n "${NAMESPACE}" scale deploy/worker --replicas=1 >/dev/null
  kubectl -n "${NAMESPACE}" rollout restart deploy/worker
  echo "Worker restarted. It remounts /secrets and will use the new ${SITE} session."
  echo
  echo "Check in a few minutes:"
  echo "  bash deploy/gke/scripts/cookie-to-k8s.sh check"
}

check_state() {
  require_cluster
  echo "== flags =="
  kubectl -n "${NAMESPACE}" get secret jobsrss-env -o json | "${PYTHON_BIN}" -c '
import base64, json, sys
data = json.load(sys.stdin).get("data") or {}
for key in ("LINKEDIN_AUTH_ENABLED", "LIEPIN_AUTH_ENABLED"):
    raw = data.get(key)
    print(key, "=", base64.b64decode(raw).decode() if raw else "<unset>")
'
  echo
  echo "== cookie files mounted in the worker =="
  kubectl -n "${NAMESPACE}" exec deploy/worker -c worker -- ls -la /secrets \
    || echo "worker is not running yet"
  echo
  echo "== recent collector lines =="
  kubectl -n "${NAMESPACE}" logs deploy/worker -c worker --tail=200 \
    | grep -E 'linkedin|liepin|collector_run |missing_storage|auth_wall' \
    || echo "no collector lines yet; the worker runs LinkedIn every 20 minutes"
}

wait_login_pod() {
  local i
  kubectl -n "${NAMESPACE}" scale deploy/linkedin-login --replicas=1 >/dev/null
  for i in $(seq 1 120); do
    if kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      python3 -c 'import pathlib,sys; sys.exit(0 if pathlib.Path("/tmp/novnc.ready").exists() else 1)' \
      >/dev/null 2>&1; then
      return 0
    fi
    echo "  waiting for the in-cluster desktop (${i}/120)"
    sleep 5
  done
  echo "Desktop never became ready. Logs:"
  kubectl -n "${NAMESPACE}" logs deploy/linkedin-login -c login --tail=80 || true
  return 1
}

case "${ACTION}" in
  desktop)
    require_cluster
    if ! kubectl -n "${NAMESPACE}" get deploy/linkedin-login >/dev/null 2>&1; then
      echo "deploy/linkedin-login does not exist yet. Create it once from Cloud Shell:"
      echo "  export IMAGE_API=asia-southeast1-docker.pkg.dev/gcp-bcgx-dev-vincents-d597/jobsrss/jobsrss-api:2adea08"
      echo "  bash deploy/gke/scripts/linkedin-session.sh start"
      exit 1
    fi
    wait_login_pod
    echo
    echo "The browser runs inside the cluster, so LinkedIn sees the GKE egress IP."
    echo "Your local browser is only a screen for it."
    echo
    echo "Open this in your local browser once the forward is up:"
    echo "  http://127.0.0.1:6080/"
    echo "Fallback if the desktop will not paint: http://127.0.0.1:8080/"
    echo
    echo "Leave this running. Ctrl+C when the LinkedIn feed has loaded, then:"
    echo "  bash deploy/gke/scripts/cookie-to-k8s.sh from-pod"
    echo
    exec kubectl -n "${NAMESPACE}" port-forward deploy/linkedin-login 6080:6080 8080:8080
    ;;
  from-pod)
    require_cluster
    WORK="$(mktemp -d)"
    echo "Asking the in-cluster browser to save its ${SITE} cookies..."
    kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      python3 -c 'import urllib.request; req=urllib.request.Request("http://127.0.0.1:8080/export",method="POST"); print(urllib.request.urlopen(req,timeout=30).read().decode())'
    kubectl -n "${NAMESPACE}" exec deploy/linkedin-login -c login -- \
      cat "/session/${SECRET_KEY}" > "${WORK}/${SECRET_KEY}"
    STATE_FILE="${WORK}/${SECRET_KEY}"
    push_state
    echo
    echo "Scale the desktop back down:"
    echo "  kubectl -n ${NAMESPACE} scale deploy/linkedin-login --replicas=0"
    ;;
  all)
    mint_state
    push_state
    ;;
  mint)
    mint_state
    echo "Now push it:"
    echo "  bash deploy/gke/scripts/cookie-to-k8s.sh push ${SITE} ${STATE_FILE}"
    ;;
  push)
    push_state
    ;;
  check)
    check_state
    ;;
  *)
    echo "Usage: $0 {desktop|from-pod|all|mint|push|check} [linkedin|liepin] [state.json]"
    exit 1
    ;;
esac
