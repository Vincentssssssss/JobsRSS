#!/usr/bin/env bash
set -euo pipefail

# Create/update Kubernetes secrets for JobsRSS.
# Usage:
#   bash deploy/gke/scripts/apply-secrets.sh /path/to/.env.gke [/path/to/secrets-dir]
#
# secrets-dir may contain:
#   linkedin_state.json
#   liepin_state.json
#
# New session files are merged into jobsrss-collector-files. Uploading only
# Liepin does not delete an existing LinkedIn cookie, and the reverse.

ENV_FILE="${1:?Usage: apply-secrets.sh /path/to/.env.gke [/path/to/secrets-dir]}"
SECRETS_DIR="${2:-}"
NAMESPACE="${NAMESPACE:-jobsrss}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

kubectl apply -f "${ROOT}/namespace.yaml"

kubectl create secret generic jobsrss-env \
  --namespace "${NAMESPACE}" \
  --from-env-file="${ENV_FILE}" \
  --dry-run=client -o yaml | kubectl apply -f -

if kubectl -n "${NAMESPACE}" get secret jobsrss-collector-files >/dev/null 2>&1; then
  python3 - <<PY
import base64, json, os, subprocess
ns = os.environ.get("NAMESPACE", "${NAMESPACE}")
dest = "${WORK}"
raw = subprocess.check_output(
    ["kubectl", "-n", ns, "get", "secret", "jobsrss-collector-files", "-o", "json"]
)
doc = json.loads(raw)
for name, encoded in (doc.get("data") or {}).items():
    if name not in {"linkedin_state.json", "liepin_state.json"}:
        continue
    path = os.path.join(dest, name)
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(encoded))
    os.chmod(path, 0o600)
PY
fi

copied=()
if [ -n "${SECRETS_DIR}" ]; then
  for name in linkedin_state.json liepin_state.json; do
    if [ -f "${SECRETS_DIR}/${name}" ]; then
      python3 -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))" \
        "${SECRETS_DIR}/${name}"
      cp "${SECRETS_DIR}/${name}" "${WORK}/${name}"
      chmod 600 "${WORK}/${name}"
      copied+=("${name}")
    fi
  done
fi

from_file_args=()
for name in linkedin_state.json liepin_state.json; do
  if [ -f "${WORK}/${name}" ]; then
    from_file_args+=(--from-file="${name}=${WORK}/${name}")
  fi
done

if [ "${#from_file_args[@]}" -gt 0 ]; then
  kubectl create secret generic jobsrss-collector-files \
    --namespace "${NAMESPACE}" \
    "${from_file_args[@]}" \
    --dry-run=client -o yaml | kubectl apply -f -
  if [ "${#copied[@]}" -gt 0 ]; then
    echo "Updated collector session files: ${copied[*]}"
  else
    echo "Kept existing collector session files."
  fi
  echo -n "Secret jobsrss-collector-files keys: "
  kubectl -n "${NAMESPACE}" get secret jobsrss-collector-files -o json \
    | python3 -c 'import json,sys; print(" ".join(sorted(json.load(sys.stdin).get("data") or {})))'
else
  echo "No collector session files provided; worker will run without LinkedIn/Liepin cookies."
fi

echo "Secrets applied in namespace ${NAMESPACE}."

if ! kubectl -n "${NAMESPACE}" get deploy/worker >/dev/null 2>&1; then
  echo
  echo "No JobsRSS Deployments exist yet (api/frontend/worker were not found)."
  echo "apply-secrets.sh only writes Kubernetes Secrets. It does not start pods."
  echo "Do not run: kubectl -n ${NAMESPACE} rollout restart deploy/worker"
else
  echo "Reload worker (and api) so they remount /secrets:"
  echo "  kubectl -n ${NAMESPACE} rollout restart deploy/api deploy/worker"
fi
