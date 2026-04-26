#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/backend/.env.local"
ENV_EXAMPLE="$ROOT_DIR/backend/.env.local.example"
CONTAINER_NAME="${AZURE_STORAGE_CONTAINER:-app-assets}"
AZURITE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFeqCnf2mqk3aE7GcxY8wEkxSQ9fL3aPo/l72tK4G8Y7YX8WfPjY4I3K0W2d8t0oL8+/hQ==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"

wait_for_postgres() {
  for _ in {1..60}; do
    if docker compose exec -T postgres pg_isready -U fcadmin -d federal_center_sw >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "PostgreSQL container did not become ready." >&2
  docker compose logs --no-color --tail=80 postgres >&2 || true
  return 1
}

wait_for_azurite() {
  local container_id
  local status

  for _ in {1..60}; do
    container_id="$(docker compose ps -q azurite)"
    status="$(
      docker inspect \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$container_id" 2>/dev/null || true
    )"
    if [ "$status" = "healthy" ]; then
      return 0
    fi
    sleep 1
  done

  echo "Azurite container did not become healthy." >&2
  docker compose logs --no-color --tail=80 azurite >&2 || true
  return 1
}

create_blob_container() {
  local output

  for _ in {1..90}; do
    if output="$(
      az storage container create \
        --name "$CONTAINER_NAME" \
        --connection-string "$AZURITE_CONNECTION_STRING" \
        --only-show-errors 2>&1
    )"; then
      echo "Local services are ready. Env file: backend/.env.local"
      return 0
    fi
    sleep 1
  done

  echo "Local services started, but Azurite container setup did not finish." >&2
  if [ -n "${output:-}" ]; then
    echo "$output" >&2
  fi
  docker compose logs --no-color --tail=80 azurite >&2 || true
  return 1
}

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

wait_for_postgres
wait_for_azurite
create_blob_container
