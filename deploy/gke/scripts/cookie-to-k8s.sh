#!/usr/bin/env bash
set -euo pipefail

# Log in locally in a real browser, then push the session cookie straight into
# the cluster so the worker keeps refreshing jobs on its own.
#
# Runs from any machine with kubectl + gcloud. Does not need ~/jobsrss.env.gke
# and never prints cookie values.
#
# Usage:
#   bash deploy/gke/scripts/cookie-to-k8s.sh              # mint linkedin, then push
#   bash deploy/gke/scripts/cookie-to-k8s.sh mint liepin
#   bash deploy/gke/scripts/cookie-to-k8s.sh push linkedin ~/secrets/linkedin_state.json
#   bash deploy/gke/scripts/cookie-to-k8s.sh check

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
  if ! "${PYTHON_BIN}" -c "import playwright" >/dev/null 2>&1; then
    echo "Playwright is missing locally. Install it once:"
    echo "  ${PYTHON_BIN} -m pip install playwright"
    echo "  ${PYTHON_BIN} -m playwright install chromium"
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

case "${ACTION}" in
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
    echo "Usage: $0 {all|mint|push|check} [linkedin|liepin] [state.json]"
    exit 1
    ;;
esac
