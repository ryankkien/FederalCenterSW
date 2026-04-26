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
- Azure Key Vault `fcsw-dev-kv-e7e9f2`
- Function App managed identity `fcsw-email-intake-dev-mi`
- Azure Functions runtime/package storage account `fcswemailfunce7e9f2`
- Azure Functions package container `app-package-fcswemailintakee7e9f2-3009836`
- Flex Consumption plan `ASP-federalcenterswdev-818f`
- Email intake Function App `fcsw-email-intake-e7e9f2`
- PostgreSQL Flexible Server `federal-center-sw-dev-pg-jal50w`
- PostgreSQL database `federal_center_sw`
- Log Analytics workspace `fcsw-dev-aca-env-logs`
- Application Insights component `fcsw-dev-aca-env-appi`
- Azure Container Registry `fcswdevacr`
- Container Apps environment `fcsw-dev-aca-env`
- Feature extractor managed identity `fcsw-feature-extractor-dev-mi`
- Feature extractor Container App `fcsw-feature-extractor-dev`

Secret-bearing app settings are managed as Azure Key Vault references. Do not add raw
passwords, API keys, storage keys, database URLs, or connection strings to Bicep parameter
files, GitHub workflow YAML, or plain app settings.

Key Vault uses Azure RBAC. The Function App and Feature Extractor Container App use
user-assigned managed identities with the `Key Vault Secrets User` role scoped to the dev
vault so they can resolve secret references at runtime.

Required dev Key Vault secret names:

| Secret | Used by |
| --- | --- |
| `app-storage-connection-string` | Backend document storage and feature extractor Blob access. |
| `function-storage-connection-string` | Azure Functions runtime and Flex deployment storage. |
| `database-url` | Backend and feature extractor PostgreSQL connection string. |
| `email-intake-host` | IMAP email intake host. |
| `email-intake-username` | IMAP email intake username. |
| `email-intake-password` | IMAP email intake worker. |
| `openai-api-key` | Backend AI processing and feature extractor OpenAI fallback. |
| `resend-api-key` | Email intake auto-reply sends when enabled. |
| `anthropic-api-key` | Feature extractor Claude provider. |

Set or rotate those values with Azure CLI:

```sh
az keyvault secret set \
  --vault-name fcsw-dev-kv-e7e9f2 \
  --name database-url \
  --value "<postgres-connection-string>"
```

## GitHub Actions

The repo includes four Azure-facing workflows:

- `.github/workflows/infra-whatif.yml` runs Bicep build and Azure what-if on pull requests
  that touch infrastructure files, and can also be run manually.
- `.github/workflows/infra-deploy.yml` runs Bicep build and deploy manually against the
  `azure-dev` GitHub environment.
- `.github/workflows/function-deploy.yml` deploys the backend worker Function App from
  `backend/` on pushes to `main` that touch backend files, configures the non-secret
  Application Insights connection string, and can also be run manually.
  The Function App currently hosts the email intake timer and the queued document
  processing timer. The workflow always runs backend lint and tests. It skips the Azure
  login, app setting writes, and Function App deployment when required deployment
  variables or secrets are missing, so code validation can still pass in repositories
  that have not completed Azure secret setup.
- `.github/workflows/feature-extractor-deploy.yml` builds `feature_extractor/`, pushes
  the `feature-extractor` image to ACR, and updates the dev Container App.

The repo also includes `.github/workflows/discord-pr-notifications.yml`, which posts
pull request lifecycle events to Discord. Create a Discord channel such as
`#pull-requests`, add a webhook for that channel, and save the webhook URL as the GitHub
repository secret `DISCORD_PULL_REQUEST_WEBHOOK_URL`. The workflow uses
`pull_request_target` so forked pull requests can still notify Discord, but it does not
check out or run pull request code.

The Azure workflows use Azure OIDC login. Configure these GitHub `azure-dev`
environment variables:

| Variable | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | `4650ab5a-7546-45cd-8694-83fc65ae586c` |
| `AZURE_TENANT_ID` | `c821732f-0ded-4db0-96c8-cf2013d16974` |
| `AZURE_SUBSCRIPTION_ID` | `99596387-8247-4e94-9917-cf8bc695f106` |
| `AZURE_RESOURCE_GROUP` | `federal-center-sw-dev` |
| `AZURE_FUNCTION_APP_NAME` | `fcsw-email-intake-e7e9f2` |
| `AZURE_STORAGE_CONTAINER` | Optional override; defaults to `app-assets`. |
| `ACR_NAME` | `fcswdevacr` |
| `ACR_LOGIN_SERVER` | `fcswdevacr.azurecr.io` |
| `FEATURE_EXTRACTOR_APP_NAME` | `fcsw-feature-extractor-dev` |
| `APPINSIGHTS_COMPONENT_NAME` | Optional override; defaults to `fcsw-dev-aca-env-appi`. |
| `EMAIL_INTAKE_DEFAULT_UPLOADER_ID` | Optional override; defaults to `contractor-demo`. |
| `EMAIL_INTAKE_DEFAULT_DOCUMENT_TYPE` | Optional override; defaults to `Email Attachment`. |
| `DOCUMENT_PROCESSING_TIMER_SCHEDULE` | Optional Azure Functions NCRONTAB schedule; defaults to every five minutes. |
| `DOCUMENT_PROCESSING_LIMIT` | Optional queued document jobs to drain per timer tick; defaults to `25`. |

Configure these GitHub repository secrets for deployment and notifications:

| Secret | Purpose |
| --- | --- |
| `DISCORD_PULL_REQUEST_WEBHOOK_URL` | Discord webhook URL for the pull request notification channel. |

The Azure identity needs permission to run resource group deployments in
`federal-center-sw-dev`, deploy to the Function App, push ACR images, update the feature
extractor Container App, and create role assignments for managed identities when Key
Vault access is deployed. Use least privilege when possible; Contributor plus User Access
Administrator at the resource group is the simple starting point for this dev
environment.

The Azure app registration or managed identity also needs federated credentials that match
the GitHub workflow subjects. The Azure workflows use the `azure-dev` GitHub environment,
so include that environment in the federated credential.

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

Renaming the feature extractor Container App from the prior dev app name to
`fcsw-feature-extractor-dev` is a delete/create change in Azure because Container App
resource names are immutable. Coordinate the cutover window, confirm the new app has the
expected secrets and image, then remove the old dev app after traffic and manual checks
are complete.
