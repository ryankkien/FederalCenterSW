#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/backend/.env.local"
ENV_EXAMPLE="$ROOT_DIR/backend/.env.local.example"
CONTAINER_NAME="${AZURE_STORAGE_CONTAINER:-app-assets}"
POSTGRES_READY_ATTEMPTS="${POSTGRES_READY_ATTEMPTS:-60}"
AZURITE_SETUP_RETRIES="${AZURITE_SETUP_RETRIES:-90}"
AZURITE_ACCOUNT_KEY="Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
AZURITE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=${AZURITE_ACCOUNT_KEY};BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
PYTHON_BIN=""

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then run bun run local:up again." >&2
  exit 1
fi

if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
fi

_create_azurite_container() {
  if [ -n "$PYTHON_BIN" ]; then
    "$PYTHON_BIN" - "$AZURITE_CONNECTION_STRING" "$CONTAINER_NAME" <<'PY'
import sys

try:
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient
except ImportError:
    sys.exit(90)

connection_string, container_name = sys.argv[1], sys.argv[2]
service = BlobServiceClient.from_connection_string(connection_string)
try:
    service.create_container(container_name)
except ResourceExistsError:
    pass
PY
    status=$?
    if [ "$status" -ne 90 ]; then
      return "$status"
    fi
  fi

  if command -v az >/dev/null 2>&1; then
    az storage container create \
      --name "$CONTAINER_NAME" \
      --connection-string "$AZURITE_CONNECTION_STRING" \
      --only-show-errors >/dev/null
    return $?
  fi

  echo "Install backend Python dependencies or Azure CLI to initialize the Azurite blob container." >&2
  return 1
}

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
for _ in $(seq 1 "$AZURITE_SETUP_RETRIES"); do
  if _create_azurite_container 2>/tmp/fcsw-azurite-setup.err; then
    echo "Local services are ready. Env file: backend/.env.local"
    exit 0
  fi
  LAST_AZURITE_ERROR="$(tail -n 5 /tmp/fcsw-azurite-setup.err 2>/dev/null || true)"
  sleep 1
done

echo "Local services started, but Azurite container setup did not finish." >&2
if [ -n "$LAST_AZURITE_ERROR" ]; then
  echo "$LAST_AZURITE_ERROR" >&2
fi
exit 1
