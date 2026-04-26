#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/backend/.env.local"
ENV_EXAMPLE="$ROOT_DIR/backend/.env.local.example"
CONTAINER_NAME="${AZURE_STORAGE_CONTAINER:-app-assets}"
AZURITE_ACCOUNT_NAME="${AZURITE_ACCOUNT_NAME:-devstoreaccount1}"
AZURITE_ACCOUNT_KEY="${AZURITE_ACCOUNT_KEY:-Eby8vdM02xNOcqFeqCnf2mqk3aE7GcxY8wEkxSQ9fL3aPo/l72tK4G8Y7YX8WfPjY4I3K0W2d8t0oL8+/hQ==}"
AZURITE_BLOB_ENDPOINT="${AZURITE_BLOB_ENDPOINT:-http://127.0.0.1:10000/devstoreaccount1}"
AZURITE_API_VERSION="${AZURITE_API_VERSION:-2021-12-02}"
POSTGRES_READY_ATTEMPTS="${POSTGRES_READY_ATTEMPTS:-60}"
AZURITE_READY_ATTEMPTS="${AZURITE_READY_ATTEMPTS:-90}"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then run bun run local:up again." >&2
  exit 1
fi

for command_name in curl openssl xxd; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required to initialize the Azurite blob container." >&2
    exit 1
  fi
done

docker compose up -d postgres azurite

if [ ! -f "$ENV_FILE" ]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

for _ in $(seq 1 "$POSTGRES_READY_ATTEMPTS"); do
  if docker compose exec -T postgres pg_isready -U fcadmin -d federal_center_sw >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

LAST_AZURITE_ERROR=""
for _ in $(seq 1 "$AZURITE_READY_ATTEMPTS"); do
  # Sign the Blob REST call directly so local startup does not depend on Azure CLI behavior.
  REQUEST_DATE="$(LC_ALL=C date -u '+%a, %d %b %Y %H:%M:%S GMT')"
  STRING_TO_SIGN="$(printf 'PUT\n\n\n\n\n\n\n\n\n\n\n\nx-ms-date:%s\nx-ms-version:%s\n/%s/%s\nrestype:container' \
    "$REQUEST_DATE" \
    "$AZURITE_API_VERSION" \
    "$AZURITE_ACCOUNT_NAME" \
    "$CONTAINER_NAME")"
  ACCOUNT_KEY_HEX="$(printf '%s' "$AZURITE_ACCOUNT_KEY" | openssl enc -A -d -base64 | xxd -p -c 256)"
  SIGNATURE="$(printf '%s' "$STRING_TO_SIGN" | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$ACCOUNT_KEY_HEX" -binary | openssl enc -A -base64)"
  STATUS_CODE="$(curl -sS -o /tmp/fcsw-azurite-create.out -w '%{http_code}' -X PUT \
    -H "Authorization: SharedKey ${AZURITE_ACCOUNT_NAME}:${SIGNATURE}" \
    -H "x-ms-date: ${REQUEST_DATE}" \
    -H "x-ms-version: ${AZURITE_API_VERSION}" \
    "${AZURITE_BLOB_ENDPOINT%/}/${CONTAINER_NAME}?restype=container" \
    2>"/tmp/fcsw-azurite-create.err" || true)"
  if [ "$STATUS_CODE" = "201" ] || [ "$STATUS_CODE" = "409" ]; then
    echo "Local services are ready. Env file: backend/.env.local"
    exit 0
  fi
  LAST_AZURITE_ERROR="$(cat /tmp/fcsw-azurite-create.err /tmp/fcsw-azurite-create.out 2>/dev/null || true)
HTTP status: $STATUS_CODE"
  sleep 1
done

echo "Local services started, but Azurite container setup did not finish." >&2
if [ -n "$LAST_AZURITE_ERROR" ]; then
  echo "$LAST_AZURITE_ERROR" >&2
fi
exit 1
