#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-federal-center-sw-dev}"
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-99596387-8247-4e94-9917-cf8bc695f106}"
PARAM_FILE="${1:-$ROOT_DIR/infra/dev.bicepparam}"

az account set --subscription "$SUBSCRIPTION_ID"

az deployment group what-if \
  --resource-group "$RESOURCE_GROUP" \
  --parameters "$PARAM_FILE" \
  --exclude-change-types NoChange
