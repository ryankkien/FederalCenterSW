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

## Checks

```sh
bun run build
bun run lint
bun run test
```

## Email Intake

The backend includes a stubbed IMAP intake worker that parses unread mailbox messages into JSONL records. It can also send an optional receipt auto-reply in commit mode. Configure it with `EMAIL_INTAKE_*` environment variables, then run:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output looks correct; commit mode moves processed messages to a `Processed` mailbox. See [docs/email-intake.md](docs/email-intake.md).

## Cloud

Azure resource inventory, access steps, PostgreSQL commands, and Blob Storage commands are documented in [docs/cloud.md](docs/cloud.md).
