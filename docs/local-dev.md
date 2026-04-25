# Local Development Mirror

The local mirror is for development and testing only. It mirrors the app-facing service
contract of Azure without trying to run Azure control-plane resources locally.

Local services:

- PostgreSQL 16 in Docker, matching the Azure PostgreSQL major version.
- Azurite in Docker, matching the Blob Storage API used by email intake stub persistence.
- Local env values in `backend/.env.local`, copied from `backend/.env.local.example`.

Start local dependencies:

```sh
bun run local:up
```

This requires Docker Desktop and Azure CLI. The Azure CLI is used only to initialize the
local Azurite blob container.

Stop local dependencies:

```sh
bun run local:down
```

Reset local dependency data:

```sh
bun run local:reset
```

Run the app normally after `local:up`:

```sh
bun run dev
```

## Mirroring Rules

Keep the cloud and local environments mirrored at the contract level:

- Same database name: `federal_center_sw`.
- Same app database user name: `fcadmin`.
- Same Blob container name: `app-assets`.
- Same backend env variable names as Azure app settings.
- Same email intake blob prefix shape, with a local-only prefix by default:
  `email-intake-local`.

Local values may use different hosts, passwords, and storage account names. Those values
must remain local-only and should not be copied into Bicep or Azure app settings.

## What Belongs Where

- Cloud resource definitions: `infra/main.bicep`.
- Cloud environment values: `infra/dev.bicepparam`.
- Local service definitions: `compose.yaml`.
- Local app env example: `backend/.env.local.example`.
- Real local app env file: `backend/.env.local`, ignored by git.
- Shared env contract examples: `backend/.env.example`.

## Azurite Notes

`bun run local:up` creates the local `app-assets` container in Azurite. The email intake
worker can then write blob stub records when these local env values are active:

```env
EMAIL_INTAKE_STUB_BLOB_ENABLED=true
EMAIL_INTAKE_STUB_BLOB_CONTAINER=app-assets
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;...
```

## Boundaries

The local mirror does not emulate:

- Azure Functions hosting and scaling behavior.
- Azure PostgreSQL firewall, identity, backup, or regional behavior.
- Azure RBAC, managed identities, or Key Vault references.
- Real IMAP/SMTP mailbox behavior.

Use local tests for fast feedback. Use `bun run infra:whatif` and the GitHub Actions
what-if workflow for Azure drift and cloud resource changes.

## CI

`.github/workflows/local-mirror.yml` starts the Docker Compose mirror in GitHub Actions
and runs backend tests. This catches local/cloud contract drift for service names, env
shape, and dependency startup without touching Azure.
