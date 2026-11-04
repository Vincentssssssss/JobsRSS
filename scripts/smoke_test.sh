#!/usr/bin/env bash
# Smoke test for a running docker compose stack.
#
#   scripts/smoke_test.sh            read-only checks
#   scripts/smoke_test.sh --write    also round-trips the favorite/applied/view endpoints
#                                    on one job and restores its marks afterwards
#
# Environment overrides: API_URL (default http://localhost:8000), WEB_URL
# (default http://localhost:3000), COMPOSE (default "docker compose"),
# EXPECT_VERSION (default: APP_VERSION in backend/app/core/config.py).
# Written for bash 3.2 so it runs unchanged on macOS.

set -u

cd "$(dirname "$0")/.."

API_URL="${API_URL:-http://localhost:8000}"
WEB_URL="${WEB_URL:-http://localhost:3000}"
COMPOSE="${COMPOSE:-docker compose}"
WRITE=0
[ "${1:-}" = "--write" ] && WRITE=1
EXPECT_VERSION="${EXPECT_VERSION:-$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' backend/app/core/config.py)}"
if [ -z "$EXPECT_VERSION" ]; then
  echo "Could not read APP_VERSION from backend/app/core/config.py; set EXPECT_VERSION." >&2
  exit 2
fi

PASS=0
FAIL=0
WARN=0
FAILED_CHECKS=""

pass() { PASS=$((PASS + 1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); FAILED_CHECKS="$FAILED_CHECKS\n  - $1"; printf '  \033[31mFAIL\033[0m %s\n' "$1"; [ -n "${2:-}" ] && printf '       %s\n' "$2"; }
warn() { WARN=$((WARN + 1)); printf '  \033[33mWARN\033[0m %s\n' "$1"; [ -n "${2:-}" ] && printf '       %s\n' "$2"; }
section() { printf '\n== %s\n' "$1"; }

# Evaluates a Python expression against a JSON (or XML) document inside the api
# container, so the host needs nothing but curl and docker.
api_python() {
  $COMPOSE exec -T api python -c "$1"
}

json_check() {
  # $1 name, $2 url, $3 python expression over `d` that must be truthy
  local body
  if ! body="$(curl -fsS --max-time 20 "$2" 2>&1)"; then
    fail "$1" "$2 -> $body"
    return
  fi
  if printf '%s' "$body" | api_python "import json,sys; d=json.load(sys.stdin); sys.exit(0 if ($3) else 1)" >/dev/null 2>&1; then
    pass "$1"
  else
    fail "$1" "$2 -> $(printf '%s' "$body" | head -c 300)"
  fi
}

status_check() {
  # $1 name, $2 expected HTTP status, $3 url, [$4 method]
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X "${4:-GET}" "$3")"
  if [ "$code" = "$2" ]; then pass "$1"; else fail "$1" "$3 -> HTTP $code (expected $2)"; fi
}

psql_value() {
  $COMPOSE exec -T postgres psql -U jobsrss -d jobsrss -tAc "$1" 2>/dev/null | tr -d '[:space:]'
}

section "Containers"
running="$($COMPOSE ps --status running --services 2>/dev/null)"
for service in postgres api worker frontend; do
  if printf '%s\n' "$running" | grep -qx "$service"; then pass "$service is running"; else fail "$service is running" "docker compose ps does not list it as running"; fi
done
for service in api worker frontend; do
  cid="$($COMPOSE ps -q "$service" 2>/dev/null)"
  [ -z "$cid" ] && continue
  restarts="$(docker inspect -f '{{.RestartCount}}' "$cid" 2>/dev/null || echo "?")"
  if [ "$restarts" = "0" ]; then pass "$service has not restarted"; else warn "$service restart count is $restarts" "check: $COMPOSE logs --tail 100 $service"; fi
done
if $COMPOSE exec -T api sh -c 'test -f /app/app/main.py && test -f /app/app/api/routes/jobs.py' >/dev/null 2>&1 \
  && $COMPOSE exec -T api cat app/api/routes/jobs.py | diff -q - backend/app/api/routes/jobs.py >/dev/null 2>&1; then
  pass "api runs the checked-out backend code"
else
  fail "api runs the checked-out backend code" "recreate it: $COMPOSE up -d --force-recreate api worker"
fi
if $COMPOSE exec -T worker cat app/scheduler/runner.py 2>/dev/null | diff -q - backend/app/scheduler/runner.py >/dev/null 2>&1; then
  pass "worker runs the checked-out backend code"
else
  fail "worker runs the checked-out backend code" "recreate it: $COMPOSE up -d --force-recreate worker"
fi

section "API"
json_check "healthz reports ok and version $EXPECT_VERSION" "$API_URL/healthz" "d.get('status')=='ok' and d.get('version')=='$EXPECT_VERSION'"
json_check "GET /jobs returns a list" "$API_URL/jobs?limit=5&status=" "isinstance(d, list)"
json_check "GET /jobs/count returns a total" "$API_URL/jobs/count?status=" "isinstance(d.get('total'), int)"
json_check "GET /jobs/source-counts returns counts" "$API_URL/jobs/source-counts" "isinstance(d.get('counts'), list)"
json_check "GET /jobs/summary/last-24h" "$API_URL/jobs/summary/last-24h" "'total_new_jobs' in d and isinstance(d.get('by_source'), list)"
json_check "GET /sources/official lists sources" "$API_URL/sources/official" "len(d.get('sources', [])) > 0"
json_check "AI precision filter is accepted" "$API_URL/jobs/count?llm_verdict=strong_fit,possible_fit&min_llm_score=60" "isinstance(d.get('total'), int)"
for mark in favorited applied not_applied viewed not_viewed; do
  json_check "mark=$mark filter is accepted" "$API_URL/jobs/count?mark=$mark&status=" "isinstance(d.get('total'), int)"
done
status_check "unknown mark filter is rejected" 422 "$API_URL/jobs/count?mark=bogus"
json_check "GET /jobs/locations groups cities by country" "$API_URL/jobs/locations" "isinstance(d.get('countries'), list) and all(c.get('label') and isinstance(c.get('cities'), list) for c in d['countries'])"
json_check "jobs carry a standardized location" "$API_URL/jobs?limit=50" "all('location_label' in j and isinstance(j.get('cities'), list) for j in d)"
json_check "city filter returns only that city" "$API_URL/jobs?city=Shanghai&limit=100" "all('Shanghai' in j['cities'] for j in d)"
json_check "city filter accepts a Chinese alias" "$API_URL/jobs?city=%E4%B8%8A%E6%B5%B7&limit=100" "all('Shanghai' in j['cities'] for j in d)"
city_total="$(curl -fsS --max-time 20 "$API_URL/jobs/count?city=Shanghai" 2>/dev/null | api_python "import json,sys; print(json.load(sys.stdin)['total'])" 2>/dev/null)"
search_total="$(curl -fsS --max-time 20 "$API_URL/jobs/count?q=%E4%B8%8A%E6%B5%B7" 2>/dev/null | api_python "import json,sys; print(json.load(sys.stdin)['total'])" 2>/dev/null)"
if [ -n "$city_total" ] && [ -n "$search_total" ] && [ "$search_total" -ge "$city_total" ]; then
  pass "searching 上海 finds every Shanghai job ($search_total >= $city_total)"
else
  fail "searching 上海 finds every Shanghai job" "q=上海 -> ${search_total:-error}, city=Shanghai -> ${city_total:-error}"
fi
status_check "unknown job returns 404" 404 "$API_URL/jobs/999999999"

first_id="$(curl -fsS --max-time 20 "$API_URL/jobs?limit=1" 2>/dev/null | api_python "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null)"
if [ -n "$first_id" ]; then
  json_check "job detail has description sections" "$API_URL/jobs/$first_id" "d['id']==$first_id and 'description_sections' in d and d.get('apply_url')"
else
  warn "no active jobs yet; skipped job detail" "the worker fills the database within ~15 minutes of starting"
fi

section "RSS"
for feed in all high-match; do
  url="$API_URL/rss/$feed.xml"
  if curl -fsS --max-time 30 "$url" 2>/dev/null | api_python "import sys, xml.etree.ElementTree as ET; root=ET.fromstring(sys.stdin.buffer.read()); sys.exit(0 if root.find('channel') is not None else 1)" >/dev/null 2>&1; then
    pass "$feed.xml is well-formed RSS"
  else
    fail "$feed.xml is well-formed RSS" "$url"
  fi
done

section "Dashboard"
page="$(curl -fsS --max-time 30 "$WEB_URL/" 2>/dev/null)"
if printf '%s' "$page" | grep -q "JobsRSS Intelligence"; then pass "dashboard page renders"; else fail "dashboard page renders" "$WEB_URL/"; fi
json_check "dashboard proxy reaches the API" "$WEB_URL/api/backend/healthz" "d.get('status')=='ok' and d.get('version')=='$EXPECT_VERSION'"
json_check "dashboard proxy forwards job queries" "$WEB_URL/api/backend/jobs/count?min_llm_score=0" "isinstance(d.get('total'), int)"

section "Database"
for column in location_category location_cities llm_verdict llm_fit_score last_verified_at favorited_at applied_at last_viewed_at view_count; do
  found="$(psql_value "SELECT count(*) FROM information_schema.columns WHERE table_name='jobs' AND column_name='$column'")"
  if [ "$found" = "1" ]; then pass "jobs.$column exists"; else fail "jobs.$column exists" "restart the api to apply schema changes: $COMPOSE up -d --force-recreate api"; fi
done
bad_categories="$(psql_value "SELECT count(*) FROM jobs WHERE status='active' AND location_category NOT IN ('confirmed_shanghai','confirmed_yangtze_delta','confirmed_hong_kong','confirmed_malaysia','confirmed_southeast_asia','unclassified','excluded')")"
if [ "$bad_categories" = "0" ]; then pass "active jobs have known location categories"; else warn "$bad_categories active jobs have an unknown location category"; fi
region_companies="$(psql_value "SELECT count(*) FROM jobs WHERE status='active' AND source LIKE 'official_%' AND company IN ('中国大陆','中国香港','中国台湾','中国澳门','中国','China','Hong Kong')")"
if [ "$region_companies" = "0" ]; then pass "no official job uses a region as its company"; else fail "$region_companies official jobs use a region as the company"; fi
active="$(psql_value "SELECT count(*) FROM jobs WHERE status='active'")"
scored="$(psql_value "SELECT count(*) FROM jobs WHERE status='active' AND llm_fit_score IS NOT NULL AND llm_verdict IS NOT NULL")"
printf '       active jobs: %s, AI-scored: %s\n' "${active:-?}" "${scored:-?}"
no_place="$(psql_value "SELECT count(*) FROM jobs WHERE status='active' AND location_cities IS NULL AND country IS NULL")"
printf '       active jobs with no recognizable place: %s\n' "${no_place:-?}"

section "Worker"
logs="$($COMPOSE logs --no-color --since 6h worker 2>/dev/null)"
runs="$(printf '%s\n' "$logs" | grep -c 'collector_run source=')"
failed_runs="$(printf '%s\n' "$logs" | grep -c 'collector_run_failed')"
if [ "$runs" -gt 0 ]; then pass "collectors ran in the last 6h ($runs runs)"; else warn "no collector run logged in the last 6h" "official sources start 30 seconds apart after the worker starts"; fi
if [ "$failed_runs" -eq 0 ]; then pass "no collector run failed in the last 6h"; else warn "$failed_runs collector runs failed in the last 6h" "$(printf '%s\n' "$logs" | grep -o 'collector_run_failed source=[a-z_0-9]*' | sort | uniq -c | tr '\n' ';')"; fi
if printf '%s\n' "$logs" | grep -q 'llm_client_unavailable\|DeploymentNotFound\|insufficient_quota\|llm_rerank_failed'; then
  fail "LLM rerank has no configuration errors" "$(printf '%s\n' "$logs" | grep -o 'llm_client_unavailable[^"]*\|DeploymentNotFound\|insufficient_quota\|llm_rerank_failed' | sort -u | head -3 | tr '\n' ';')"
else
  pass "LLM rerank has no configuration errors"
fi
llm_state="$($COMPOSE exec -T worker python -c "
from app.core.config import get_settings
s = get_settings()
key = (s.llm_api_key or '').strip()
if not s.llm_rerank_enabled:
    print('disabled')
elif s.llm_azure_use_default_credential:
    print('ok model=%s' % s.llm_model)
elif not key:
    print('missing_key')
elif any(ord(c) > 127 or c.isspace() for c in key):
    print('non_ascii_key')
else:
    print('ok model=%s key_length=%d' % (s.llm_model, len(key)))
" 2>/dev/null)"
case "$llm_state" in
  ok*) pass "LLM settings look valid ($llm_state)" ;;
  disabled) warn "LLM rerank is disabled (LLM_RERANK_ENABLED=false); jobs will not get AI scores" ;;
  *) fail "LLM settings look valid" "worker reports: ${llm_state:-no answer}; fix LLM_* in .env, then $COMPOSE up -d --force-recreate worker" ;;
esac

if [ "$WRITE" = "1" ]; then
  section "Marks (write)"
  if [ -z "$first_id" ]; then
    warn "no active jobs; skipped marks round-trip"
  else
    before="$(curl -fsS "$API_URL/jobs/$first_id" | api_python "import json,sys; d=json.load(sys.stdin); print('%s %s %s' % (d.get('favorited_at') is not None, d.get('applied_at') is not None, d.get('view_count', 0)))")"
    was_fav="$(echo "$before" | cut -d' ' -f1)"
    was_applied="$(echo "$before" | cut -d' ' -f2)"
    views="$(echo "$before" | cut -d' ' -f3)"
    body="$(curl -fsS -X PUT -H 'content-type: application/json' -d '{"favorited":true,"applied":true}' "$WEB_URL/api/backend/jobs/$first_id/marks")"
    if printf '%s' "$body" | api_python "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['favorited_at'] and d['applied_at'] else 1)" >/dev/null 2>&1; then pass "favorite and applied can be set"; else fail "favorite and applied can be set" "$body"; fi
    body="$(curl -fsS -X POST "$WEB_URL/api/backend/jobs/$first_id/view")"
    if printf '%s' "$body" | api_python "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['view_count']==$views+1 and d['last_viewed_at'] else 1)" >/dev/null 2>&1; then pass "view is recorded"; else fail "view is recorded" "$body"; fi
    restore="{\"favorited\": $( [ "$was_fav" = "True" ] && echo true || echo false ), \"applied\": $( [ "$was_applied" = "True" ] && echo true || echo false )}"
    curl -fsS -X PUT -H 'content-type: application/json' -d "$restore" "$API_URL/jobs/$first_id/marks" >/dev/null && pass "marks restored on job $first_id (view count stays +1)"
  fi
fi

printf '\n%d passed, %d failed, %d warnings\n' "$PASS" "$FAIL" "$WARN"
if [ "$FAIL" -gt 0 ]; then
  printf 'Failed:%b\n' "$FAILED_CHECKS"
  exit 1
fi
exit 0
