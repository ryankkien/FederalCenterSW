# Federal Center SW

Starter framework with a TypeScript frontend and Python backend.

## Stack

- Frontend: React, TypeScript, Vite, Vitest, ESLint
- Backend: Python, FastAPI, Uvicorn, Pytest

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   ├── requirements-dev.txt
│   └── requirements.txt
├── docs/
├── infra/
├── scripts/
├── compose.yaml
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
└── package.json
```

## Setup

Install frontend dependencies:

```sh
bun install
```

Create and install backend dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
```

## Development

Start local backing services:

```sh
bun run local:up
```

Run the backend API:

```sh
bun run dev:backend
```

Run the frontend in another terminal:

```sh
bun run dev:frontend
```

Or run both together:

```sh
bun run dev
```

The frontend runs on `http://localhost:5173` and proxies `/api/*` requests to the backend on `http://127.0.0.1:8000`.

See [docs/local-dev.md](docs/local-dev.md) for the Docker-based local mirror of PostgreSQL and Blob Storage.

## Checks

```sh
bun run build
bun run lint
bun run test
```

## Infrastructure

Azure infrastructure is defined with Bicep in `infra/`.

Preview infrastructure changes:

```sh
bun run infra:whatif
```

Apply infrastructure changes:

```sh
bun run infra:deploy
```

See [docs/infra.md](docs/infra.md) for the Bicep/GitHub Actions workflow and drift policy.

## Email Intake

The backend includes a stubbed IMAP intake worker that parses unread mailbox messages into JSONL records. It can also send an optional receipt auto-reply in commit mode. Configure it with `EMAIL_INTAKE_*` environment variables, then run:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output looks correct; commit mode moves processed messages to a `Processed` mailbox. See [docs/email-intake.md](docs/email-intake.md).

## Cloud

Azure resource inventory, access steps, PostgreSQL commands, and Blob Storage commands are documented in [docs/cloud.md](docs/cloud.md).

Local development mirrors the cloud-facing PostgreSQL and Blob Storage contract with Docker Compose. Keep Azure inventory and access notes in `docs/cloud.md`, infrastructure workflow notes in `docs/infra.md`, and local mirror instructions in `docs/local-dev.md`.
