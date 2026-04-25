# AGENTS.md

## Project Overview

Federal Center SW is a small full-stack workspace with:

- A React + TypeScript + Vite frontend in `frontend/`.
- A Python FastAPI backend in `backend/`.
- Azure infrastructure defined with Bicep in `infra/`.
- Shared developer commands in the root `package.json`.
- Operational notes in `docs/`.

The frontend talks to the backend through `/api/*` routes. During local development,
Vite proxies those requests to `http://127.0.0.1:8000`.

## Architecture

### Frontend

- Put React application code in `frontend/src/`.
- `frontend/src/main.tsx` is the browser entry point.
- `frontend/src/App.tsx` currently owns the main starter UI and calls `/api/health`.
- `frontend/src/styles.css` contains global styles for the starter UI.
- `frontend/src/test/setup.ts` configures Vitest and Testing Library.
- Frontend tests should live beside the code they cover or in `frontend/src/` using
  the existing `*.test.tsx` pattern.

Prefer TypeScript, React function components, and existing Vite/Vitest patterns.
Keep browser API calls relative, such as `/api/health`, so the Vite proxy and deployed
same-origin routing can both work.

### Backend

- Put FastAPI routes, service logic, and backend modules in `backend/app/`.
- `backend/app/main.py` creates the FastAPI app, configures CORS, and defines API routes.
- `backend/app/email_intake.py` contains the IMAP email intake worker, message parsing,
  JSONL/Azure Blob stub persistence, and auto-reply logic.
- `backend/function_app.py` is the Azure Functions timer-trigger entry point for
  running email intake in Azure.
- `backend/host.json` contains Azure Functions host configuration.
- Backend tests live in `backend/tests/`.

When adding API features, keep route definitions close to `backend/app/main.py` unless
the app grows enough to justify routers. Put reusable parsing, persistence, or workflow
logic in separate modules under `backend/app/` and cover it with pytest tests.

### Infrastructure And Cloud

- Azure infrastructure lives in `infra/` and is managed with Bicep.
- `infra/main.bicep` defines the shared dev resources.
- `infra/dev.bicepparam` pins the current dev names and regions.
- Use `bun run infra:whatif` before changing Azure resources.
- Use `bun run infra:deploy` only when the what-if output is understood.
- GitHub Actions workflows for infrastructure live in `.github/workflows/`.
- Keep cloud inventory, access notes, and manual CLI operations in `docs/cloud.md`.
- Keep infrastructure workflow and drift policy in `docs/infra.md`.
- The active development resource group is `federal-center-sw-dev`.
- Do not commit secrets, app passwords, storage keys, database passwords, or connection
  strings. Use local `.env` files, GitHub environment configuration, Azure app settings,
  or Key Vault.
- Function App app settings currently contain secrets and are not fully managed by Bicep.
  Move secrets to Key Vault before making app settings fully declarative.

### Docs And Config

- Use `README.md` for project setup, common commands, and high-level orientation.
- Use `docs/` for longer operational notes, cloud details, and workflow-specific docs.
- Keep backend environment examples in `backend/.env.example`.
- Do not commit local secrets or generated local data files.

## Commands

Install frontend dependencies:

```sh
bun install
```

Create and install backend dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
```

Run both dev servers:

```sh
bun run dev
```

Run one side only:

```sh
bun run dev:frontend
bun run dev:backend
```

Run checks:

```sh
bun run build
bun run lint
bun run test
```

Run the email intake worker:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output has been checked.

Preview or apply infrastructure:

```sh
bun run infra:whatif
bun run infra:deploy
```

## Coding Conventions

- Use `rg`/`rg --files` for repository searches.
- Keep changes scoped to the requested feature or fix.
- Follow the existing style before introducing new abstractions.
- Prefer structured libraries and framework APIs over ad hoc parsing.
- Use ASCII unless the edited file already uses another character set or the content
  requires it.
- Add comments only where they clarify non-obvious behavior.

## Testing Guidance

- For frontend UI behavior, use Vitest and Testing Library.
- For backend behavior, use pytest under `backend/tests/`.
- Add or update tests when changing API responses, parsing behavior, email intake logic,
  or user-visible frontend behavior.
- Run the narrowest relevant test first, then run `bun run test` when the change affects
  both sides or shared behavior.

## Where New Work Should Go

- New React components: `frontend/src/`, split out from `App.tsx` when the UI grows.
- New frontend styles: `frontend/src/styles.css` unless a component-level styling
  convention is introduced later.
- New API endpoints: `backend/app/main.py` for now; introduce routers only when route
  groups become meaningfully separate.
- New backend domain logic: focused modules under `backend/app/`.
- New Azure Function triggers: `backend/function_app.py`, reusing logic from
  `backend/app/` instead of duplicating worker behavior.
- New Azure resources: `infra/main.bicep` and environment parameters in
  `infra/dev.bicepparam`.
- New cloud workflow notes: `docs/infra.md`.
- New backend tests: `backend/tests/test_<feature>.py`.
- New frontend tests: `frontend/src/<feature>.test.tsx` or beside the component.
- New operational documentation: `docs/`.

## Current Feature Notes

- `/api/health` is the basic backend health endpoint consumed by the starter frontend.
- Email intake is currently a worker-style module, not a FastAPI route.
- Email intake persistence is intentionally stubbed: it writes JSONL locally by default
  and can write JSON records to Azure Blob Storage when configured.
- In Azure Functions, email intake should use Blob Storage for durable stub output
  because local function storage is ephemeral.
- Cloud setup and Azure resource notes belong in `docs/cloud.md`.
- Infrastructure workflow and drift policy belong in `docs/infra.md`.
- Email intake configuration and operating notes belong in `docs/email-intake.md`.
