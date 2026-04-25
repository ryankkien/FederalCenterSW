#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/backend/.env.local"
ENV_EXAMPLE="$ROOT_DIR/backend/.env.local.example"
CONTAINER_NAME="${AZURE_STORAGE_CONTAINER:-app-assets}"
AZURITE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFeqCnf2mqk3aE7GcxY8wEkxSQ9fL3aPo/l72tK4G8Y7YX8WfPjY4I3K0W2d8t0oL8+/hQ==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then run bun run local:up again." >&2
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI is required to initialize the Azurite blob container." >&2
  echo "Install it with: brew install azure-cli" >&2
  exit 1
fi

docker compose up -d postgres azurite

if [ ! -f "$ENV_FILE" ]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

for _ in {1..30}; do
  if docker compose exec -T postgres pg_isready -U fcadmin -d federal_center_sw >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for _ in {1..30}; do
  if az storage container create \
    --name "$CONTAINER_NAME" \
    --connection-string "$AZURITE_CONNECTION_STRING" \
    --only-show-errors >/dev/null 2>&1; then
    echo "Local services are ready. Env file: backend/.env.local"
    exit 0
  fi
  sleep 1
done

echo "Local services started, but Azurite container setup did not finish." >&2
exit 1
