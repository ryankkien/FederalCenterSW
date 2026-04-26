# Infrastructure

This project uses Azure Bicep for the shared development infrastructure.

Local development dependencies are mirrored separately with Docker Compose. See
[local-dev.md](local-dev.md). Keep Bicep as the cloud source of truth and Compose as the
local test mirror.

The local mirror is validated by `.github/workflows/local-mirror.yml`; Azure resource
drift is validated separately by `.github/workflows/infra-whatif.yml`.

The desired dev environment is defined in:

- `infra/main.bicep`
- `infra/dev.bicepparam`

Local helper scripts:

```sh
bun run infra:whatif
bun run infra:deploy
```

`infra:whatif` previews Azure changes without applying them. `infra:deploy` applies the
Bicep deployment to the `federal-center-sw-dev` resource group.

## Current Scope

The Bicep template currently adopts the resources that already exist in Azure:

- App Blob Storage account `fcswdevcwm2xrlu`
- Private Blob container `app-assets`
- Azure Functions runtime/package storage account `fcswemailfunce7e9f2`
- Azure Functions package container `app-package-fcswemailintakee7e9f2-3009836`
- Flex Consumption plan `ASP-federalcenterswdev-818f`
- Email intake Function App `fcsw-email-intake-e7e9f2`
- PostgreSQL Flexible Server `federal-center-sw-dev-pg-jal50w`
- PostgreSQL database `federal_center_sw`

Function App app settings are not fully managed by Bicep yet because the current settings
include mailbox passwords and storage connection strings. Do not add those secrets directly
to Bicep parameter files. The next step should be moving secrets into Azure Key Vault and
then referencing them from app settings.

## GitHub Actions

The repo includes three Azure-facing workflows:

- `.github/workflows/infra-whatif.yml` runs Bicep build and Azure what-if on pull requests
  that touch infrastructure files, and can also be run manually.
- `.github/workflows/infra-deploy.yml` runs Bicep build and deploy manually against the
  `azure-dev` GitHub environment.
- `.github/workflows/function-deploy.yml` deploys the backend worker Function App from
  `backend/` on pushes to `main` that touch backend files, and can also be run manually.
  The Function App currently hosts the email intake timer and the queued document
  processing timer.

The repo also includes `.github/workflows/discord-pr-notifications.yml`, which posts
pull request lifecycle events to Discord. Create a Discord channel such as
`#pull-requests`, add a webhook for that channel, and save the webhook URL as the GitHub
repository secret `DISCORD_PULL_REQUEST_WEBHOOK_URL`. The workflow uses
`pull_request_target` so forked pull requests can still notify Discord, but it does not
check out or run pull request code.

The Azure workflows use Azure OIDC login. Configure these GitHub repository variables:

| Variable | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | Client ID for the Azure app registration or managed identity used by GitHub Actions. |
| `AZURE_TENANT_ID` | `c821732f-0ded-4db0-96c8-cf2013d16974` |
| `AZURE_SUBSCRIPTION_ID` | `99596387-8247-4e94-9917-cf8bc695f106` |
| `AZURE_RESOURCE_GROUP` | `federal-center-sw-dev` |
| `AZURE_FUNCTION_APP_NAME` | `fcsw-email-intake-e7e9f2` |
| `AZURE_STORAGE_CONTAINER` | Optional override; defaults to `app-assets`. |
| `EMAIL_INTAKE_DEFAULT_UPLOADER_ID` | Optional override; defaults to `contractor-demo`. |
| `EMAIL_INTAKE_DEFAULT_DOCUMENT_TYPE` | Optional override; defaults to `Email Attachment`. |
| `DOCUMENT_PROCESSING_TIMER_SCHEDULE` | Optional Azure Functions NCRONTAB schedule; defaults to every five minutes. |
| `DOCUMENT_PROCESSING_LIMIT` | Optional queued document jobs to drain per timer tick; defaults to `25`. |

Configure these GitHub repository secrets for deployment and notifications:

| Secret | Purpose |
| --- | --- |
| `AZURE_FUNCTION_DATABASE_URL` | PostgreSQL connection string written to the Function App as `DATABASE_URL`. |
| `AZURE_FUNCTION_STORAGE_CONNECTION_STRING` | Blob Storage connection string written to the Function App as `AZURE_STORAGE_CONNECTION_STRING`. |
| `DISCORD_PULL_REQUEST_WEBHOOK_URL` | Discord webhook URL for the pull request notification channel. |

The Azure identity needs permission to run resource group deployments in
`federal-center-sw-dev` and deploy to the Function App. Use least privilege when possible;
Contributor at the resource group is the simple starting point.

The Azure app registration or managed identity also needs federated credentials that match
the GitHub workflow subjects. The deploy workflows use the `azure-dev` GitHub environment,
so include that environment in the deploy federated credential.

## Drift Policy

Normal changes should happen through Bicep and pull requests:

1. Edit `infra/main.bicep` or `infra/dev.bicepparam`.
2. Run `bun run infra:whatif`.
3. Open a pull request and review the GitHub Actions what-if output.
4. After merge, run the manual deploy workflow or `bun run infra:deploy`.

Portal changes are acceptable for investigation or emergency repair, but copy any intended
change back into `infra/` immediately. Otherwise the next what-if will report drift.

Azure what-if can report provider default noise. At the time this was added, the known
noise is on `Microsoft.Web/sites/fcsw-email-intake-e7e9f2` for default Function App
`siteConfig` fields.
