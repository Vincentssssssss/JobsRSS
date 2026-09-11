#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/jobsrss}"
COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
ENV_FILE="${APP_DIR}/.env.prod"
RUNTIME_ENV_FILE="${APP_DIR}/.runtime.env"

: "${ACR_LOGIN_SERVER:?ACR_LOGIN_SERVER is required}"
: "${ACR_USERNAME:?ACR_USERNAME is required}"
: "${ACR_PASSWORD:?ACR_PASSWORD is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Missing compose file: $COMPOSE_FILE"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE"
  echo "Copy /opt/jobsrss/.env.prod.example to /opt/jobsrss/.env.prod and fill values."
  exit 1
fi

mkdir -p "${APP_DIR}/secrets"

cp "$ENV_FILE" "$RUNTIME_ENV_FILE"
{
  echo ""
  echo "ACR_LOGIN_SERVER=${ACR_LOGIN_SERVER}"
  echo "IMAGE_TAG=${IMAGE_TAG}"
} >> "$RUNTIME_ENV_FILE"

echo "$ACR_PASSWORD" | docker login "$ACR_LOGIN_SERVER" --username "$ACR_USERNAME" --password-stdin
docker compose --env-file "$RUNTIME_ENV_FILE" -f "$COMPOSE_FILE" pull
docker compose --env-file "$RUNTIME_ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans

if command -v curl >/dev/null 2>&1; then
  for _ in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:8000/healthz" >/dev/null; then
      echo "Deployment succeeded: API health check is OK."
      exit 0
    fi
    sleep 3
  done
  echo "Deployment finished but API health check did not return success in time."
  exit 1
fi

echo "Deployment finished (curl not installed, health check skipped)."
