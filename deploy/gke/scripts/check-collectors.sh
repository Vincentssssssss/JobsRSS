#!/usr/bin/env bash
set -euo pipefail

# Diagnose LinkedIn/Liepin collection on the live GKE worker.
# Prints flags, whether cookie files are mounted, and relevant log lines.
# Does not print cookie contents.

NAMESPACE="${NAMESPACE:-jobsrss}"

echo "== platform flags in secret/jobsrss-env =="
kubectl -n "${NAMESPACE}" get secret jobsrss-env -o json | python3 -c '
import base64, json, sys
data = json.load(sys.stdin).get("data") or {}
keys = [
    "LINKEDIN_AUTH_ENABLED",
    "LIEPIN_AUTH_ENABLED",
    "LINKEDIN_REQUIRE_STORAGE_STATE",
    "LINKEDIN_AUTH_STORAGE_STATE_PATH",
    "LIEPIN_AUTH_STORAGE_STATE_PATH",
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
echo "== worker log lines for LinkedIn/Liepin (last 400) =="
kubectl -n "${NAMESPACE}" logs deploy/worker -c worker --tail=400 \
  | grep -E 'linkedin|liepin|storage_state|collector_skipped|collector_run |collector_run_failed|auth_wall|missing_storage' \
  || echo "no matching worker log lines yet"

echo
echo "== jobs already in the API =="
echo "Use these from Cloud Shell or a laptop:"
echo "  curl -sS http://jobsrss.vincentspace.com/jobs?source=linkedin_auth&limit=1"
echo "  curl -sS http://jobsrss.vincentspace.com/jobs?source=liepin_auth&limit=1"
echo
echo "If flags are false, cookies were never applied, or /secrets is empty,"
echo "this is configuration, not cookie interception."
echo "If flags are true, files are mounted, and logs show login/auth walls,"
echo "LinkedIn/Liepin are rejecting the GKE datacenter egress IP."
