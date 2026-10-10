#!/usr/bin/env bash
set -euo pipefail

# Diagnose official/Liepin collection and LLM scoring on the live GKE worker.
# Prints flags, whether cookie files are mounted, and relevant log lines.
# Does not print cookie contents.

NAMESPACE="${NAMESPACE:-jobsrss}"

echo "== platform flags in secret/jobsrss-env =="
kubectl -n "${NAMESPACE}" get secret jobsrss-env -o json | python3 -c '
import base64, json, sys
data = json.load(sys.stdin).get("data") or {}
keys = [
    "LINKEDIN_AUTH_ENABLED",
    "LINKEDIN_EMAIL_ENABLED",
    "LIEPIN_AUTH_ENABLED",
    "LIEPIN_AUTH_STORAGE_STATE_PATH",
    "OFFICIAL_SOURCES_ENABLED",
    "LLM_RERANK_ENABLED",
    "LLM_ONLY_UNSCORED",
    "LLM_MAX_JOBS_PER_RUN",
]
for key in keys:
    raw = data.get(key)
    value = base64.b64decode(raw).decode("utf-8", "replace") if raw else "<unset>"
    print(f"{key}={value}")
'

echo
echo "== secret/jobsrss-collector-files keys (names only) =="
if kubectl -n "${NAMESPACE}" get secret jobsrss-collector-files >/dev/null 2>&1; then
  kubectl -n "${NAMESPACE}" get secret jobsrss-collector-files -o json | python3 -c '
import json, sys
keys = sorted((json.load(sys.stdin).get("data") or {}).keys())
print(" ".join(keys) if keys else "<empty secret>")
'
else
  echo "secret/jobsrss-collector-files is missing"
fi

echo
echo "== files mounted at /secrets in the worker =="
if kubectl -n "${NAMESPACE}" get deploy/worker >/dev/null 2>&1; then
  kubectl -n "${NAMESPACE}" exec deploy/worker -c worker -- ls -la /secrets \
    || echo "worker cannot list /secrets (volume may be empty/optional)"
else
  echo "deploy/worker not found"
fi

echo
echo "== worker log lines for official/Liepin/LLM (last 400) =="
kubectl -n "${NAMESPACE}" logs deploy/worker -c worker --tail=400 \
  | grep -E 'official_|liepin|llm_rerank|storage_state|collector_skipped|collector_run |collector_run_failed|auth_wall|missing_storage' \
  || echo "no matching worker log lines yet"

echo
echo "== jobs already in the API =="
echo "Use these from Cloud Shell or a laptop:"
echo "  curl -sS http://jobsrss.vincentspace.com/jobs?source=liepin_auth&limit=1"
echo
echo "Expected GKE mode: LinkedIn flags false; official + LLM true."
echo "Liepin is optional and needs /secrets/liepin_state.json only when enabled."
