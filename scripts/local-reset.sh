#!/usr/bin/env bash
set -euo pipefail

docker compose down -v
rm -f backend/.env.local
