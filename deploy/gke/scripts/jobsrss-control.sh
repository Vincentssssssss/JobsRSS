#!/usr/bin/env bash
set -euo pipefail

# Pause/resume JobsRSS worker and LLM spend. Does not touch postgres/api/frontend.
#
# Usage:
#   bash deploy/gke/scripts/jobsrss-control.sh status
#   bash deploy/gke/scripts/jobsrss-control.sh worker-stop
#   bash deploy/gke/scripts/jobsrss-control.sh worker-start
#   bash deploy/gke/scripts/jobsrss-control.sh llm-off
#   bash deploy/gke/scripts/jobsrss-control.sh llm-on
#   bash deploy/gke/scripts/jobsrss-control.sh login-stop

NAMESPACE="${NAMESPACE:-jobsrss}"
ENV_FILE="${JOBSRSS_ENV_FILE:-$HOME/jobsrss.env.gke}"
ACTION="${1:-status}"

secret_flag() {
  local key="$1"
  kubectl -n "${NAMESPACE}" get secret jobsrss-env -o json | python3 -c '
import base64, json, sys
key = sys.argv[1]
data = json.load(sys.stdin).get("data") or {}
raw = data.get(key)
print(base64.b64decode(raw).decode("utf-8", "replace") if raw else "<unset>")
' "${key}"
}

set_env_flag() {
  local key="$1" value="$2"
  if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}; cannot update ${key}."
    exit 1
  fi
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s/^${key}=.*/${key}=${value}/" "${ENV_FILE}"
  else
    echo "${key}=${value}" >> "${ENV_FILE}"
  fi
  bash "$(dirname "$0")/apply-secrets.sh" "${ENV_FILE}"
}

case "${ACTION}" in
  status)
    echo "=== deployments ==="
    kubectl -n "${NAMESPACE}" get deploy worker linkedin-login api frontend \
      -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas \
      2>/dev/null || kubectl -n "${NAMESPACE}" get deploy
    echo
    echo "LLM_RERANK_ENABLED=$(secret_flag LLM_RERANK_ENABLED)"
    echo "LINKEDIN_AUTH_ENABLED=$(secret_flag LINKEDIN_AUTH_ENABLED)"
    echo "LIEPIN_AUTH_ENABLED=$(secret_flag LIEPIN_AUTH_ENABLED)"
    echo
    echo "Azure/LLM calls only happen in deploy/worker. Scaling worker to 0 stops them."
    echo "api/frontend/postgres stay up so the portal still serves already-collected jobs."
    ;;
  worker-stop|pause)
    kubectl -n "${NAMESPACE}" scale deploy/worker --replicas=0
    kubectl -n "${NAMESPACE}" scale deploy/linkedin-login --replicas=0 2>/dev/null || true
    echo "worker=0 linkedin-login=0"
    echo "No collectors and no LLM rerank until worker-start."
    echo "Portal (api/frontend) is unchanged."
    ;;
  worker-start|resume)
    kubectl -n "${NAMESPACE}" scale deploy/worker --replicas=1
    kubectl -n "${NAMESPACE}" rollout status deploy/worker --timeout=180s
    echo "worker=1"
    echo "LLM will run only if LLM_RERANK_ENABLED=true (now: $(secret_flag LLM_RERANK_ENABLED))."
    ;;
  llm-off)
    set_env_flag LLM_RERANK_ENABLED false
    if kubectl -n "${NAMESPACE}" get deploy/worker >/dev/null 2>&1; then
      kubectl -n "${NAMESPACE}" rollout restart deploy/worker
      echo "LLM_RERANK_ENABLED=false. Worker restarted; collectors still run, Azure scoring does not."
    fi
    ;;
  llm-on)
    set_env_flag LLM_RERANK_ENABLED true
    if kubectl -n "${NAMESPACE}" get deploy/worker >/dev/null 2>&1; then
      kubectl -n "${NAMESPACE}" rollout restart deploy/worker
      echo "LLM_RERANK_ENABLED=true. Worker restarted."
    fi
    ;;
  login-stop)
    kubectl -n "${NAMESPACE}" scale deploy/linkedin-login --replicas=0 2>/dev/null || true
    echo "linkedin-login=0"
    ;;
  *)
    echo "Usage: $0 {status|worker-stop|worker-start|llm-off|llm-on|login-stop}"
    exit 1
    ;;
esac
