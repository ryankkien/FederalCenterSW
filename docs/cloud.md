# Cloud Setup

This document records the shared Azure setup for the project. It intentionally excludes secrets, passwords, access keys, and connection strings.

Infrastructure is now defined in Bicep under `infra/`. Use `bun run infra:whatif`
before changing Azure resources and `bun run infra:deploy` to apply intended changes.
See [infra.md](infra.md) for the Bicep/GitHub Actions workflow and drift policy.

Local PostgreSQL and Blob Storage dependencies are mirrored with Docker Compose for fast
development only. See [local-dev.md](local-dev.md). Keep Azure resource inventory,
access, and manual cloud commands in this file.

## Azure Account

- Tenant display name: `Default Directory`
- Tenant domain: `rkien29gmail.onmicrosoft.com`
- Subscription name: `Azure subscription 1`
- Subscription ID: `99596387-8247-4e94-9917-cf8bc695f106`
- Resource group: `federal-center-sw-dev`
- Resource group region: `eastus`

Everything for this project should live in the single resource group `federal-center-sw-dev`.

## Resources

| Purpose | Azure resource | Region | Notes |
| --- | --- | --- | --- |
| PostgreSQL database | `federal-center-sw-dev-pg-jal50w` | `centralus` | Azure Database for PostgreSQL Flexible Server. East US was restricted for this subscription, so the DB is in Central US while staying in the same resource group. |
| App database | `federal_center_sw` | `centralus` | Database inside the PostgreSQL server. |
| Blob storage account | `fcswdevcwm2xrlu` | `eastus` | Standard LRS StorageV2 account. |
| Blob container | `app-assets` | `eastus` | Private container for app files/assets. |
| Function package storage account | `fcswemailfunce7e9f2` | `eastus` | Standard LRS StorageV2 account used by Azure Functions Flex Consumption deployment storage. |
| Function package container | `app-package-fcswemailintakee7e9f2-3009836` | `eastus` | Private container for Function App package deployment. |
| Function App plan | `ASP-federalcenterswdev-818f` | `eastus` | Flex Consumption plan. |
| Backend worker Function App | `fcsw-email-intake-e7e9f2` | `eastus` | Timer-trigger Function App for email intake and queued document processing. |
| Azure Container Registry | `fcswdevacr` | `eastus` | Stores deployable pipeline service images. |
| Container Apps environment | `fcsw-dev-aca-env` | `eastus` | Managed environment for optional pipeline services. |
| Feature extractor Container App | `fcsw-feature-extractor-dev` | `eastus` | Optional service image built from `feature_extractor/`. This rename from the prior dev app name requires a delete/create cutover. |

## Portal Links

- Azure Portal: <https://portal.azure.com>
- Resource groups: <https://portal.azure.com/#browse/resourcegroups>
- Project resource group: <https://portal.azure.com/#@/resource/subscriptions/99596387-8247-4e94-9917-cf8bc695f106/resourceGroups/federal-center-sw-dev/overview>
- PostgreSQL server: <https://portal.azure.com/#@/resource/subscriptions/99596387-8247-4e94-9917-cf8bc695f106/resourceGroups/federal-center-sw-dev/providers/Microsoft.DBforPostgreSQL/flexibleServers/federal-center-sw-dev-pg-jal50w/overview>
- Storage account: <https://portal.azure.com/#@/resource/subscriptions/99596387-8247-4e94-9917-cf8bc695f106/resourceGroups/federal-center-sw-dev/providers/Microsoft.Storage/storageAccounts/fcswdevcwm2xrlu/overview>

## User Access

The following users were invited into the tenant as guests and assigned `Owner` on the `federal-center-sw-dev` resource group:

- `nringdahl27@gmail.com`
- `molly.CU@gmail.com`
- `edhadly@gmail.com`
- `jonathanmhtran@gmail.com`
- `rkien29@gmail.com`

To access the resources:

1. Accept the Microsoft/Azure guest invitation email.
2. Open <https://portal.azure.com>.
3. Switch directory to `Default Directory` / `rkien29gmail.onmicrosoft.com` from the account menu if the resources are not visible.
4. Search for `Resource groups`.
5. Open `federal-center-sw-dev`.

If access does not appear immediately, sign out and back in, then verify the directory selector in the Azure Portal.

## Azure CLI

Install Azure CLI on macOS:

```sh
brew install azure-cli
```

Login:

```sh
az login
az account set --subscription "99596387-8247-4e94-9917-cf8bc695f106"
```

Confirm account and resource group:

```sh
az account show --output table
az group show --name federal-center-sw-dev --output table
az resource list --resource-group federal-center-sw-dev --output table
```

## PostgreSQL

Show the PostgreSQL server:

```sh
az postgres flexible-server show \
  --resource-group federal-center-sw-dev \
  --name federal-center-sw-dev-pg-jal50w \
  --output table
```

List databases:

```sh
az postgres flexible-server db list \
  --resource-group federal-center-sw-dev \
  --server-name federal-center-sw-dev-pg-jal50w \
  --output table
```

Create another database:

```sh
az postgres flexible-server db create \
  --resource-group federal-center-sw-dev \
  --server-name federal-center-sw-dev-pg-jal50w \
  --database-name <database-name>
```

Add your current public IP to the PostgreSQL firewall:

```sh
MY_IP=$(curl -sS https://api.ipify.org)

az postgres flexible-server firewall-rule create \
  --resource-group federal-center-sw-dev \
  --name federal-center-sw-dev-pg-jal50w \
  --rule-name "dev-$USER" \
  --start-ip-address "$MY_IP" \
  --end-ip-address "$MY_IP"
```

Connection strings and passwords should live in local `.env` files or Azure app settings, not in git.

Example local backend env shape:

```env
DATABASE_URL=postgresql+psycopg://<user>:<password>@federal-center-sw-dev-pg-jal50w.postgres.database.azure.com:5432/federal_center_sw?sslmode=require
```

## Blob Storage

Show the storage account:

```sh
az storage account show \
  --resource-group federal-center-sw-dev \
  --name fcswdevcwm2xrlu \
  --output table
```

List containers:

```sh
az storage container list \
  --account-name fcswdevcwm2xrlu \
  --auth-mode login \
  --output table
```

Upload a file to the private `app-assets` container:

```sh
az storage blob upload \
  --account-name fcswdevcwm2xrlu \
  --container-name app-assets \
  --name path/in/blob/example.txt \
  --file ./example.txt \
  --auth-mode login
```

List blobs:

```sh
az storage blob list \
  --account-name fcswdevcwm2xrlu \
  --container-name app-assets \
  --auth-mode login \
  --output table
```

Download a blob:

```sh
az storage blob download \
  --account-name fcswdevcwm2xrlu \
  --container-name app-assets \
  --name path/in/blob/example.txt \
  --file ./example.txt \
  --auth-mode login
```

The app keeps the container private. The frontend downloads documents by calling the backend SAS endpoint:

```text
GET /api/documents/{document_id}/sas-url
```

That endpoint checks the signed-in user's document access and returns a read-only Blob URL that expires in 15 minutes. If Azure Blob Storage is not configured locally, the endpoint returns `501` and the frontend falls back to the backend download route.

New portal and email attachments store a source file plus extracted text metadata:

```text
documents/{uploader_id}/{document_id}/{original_filename}
documents/{uploader_id}/{document_id}/text.json
```

PDFs with a usable embedded text layer are extracted directly. Scanned PDFs, PDFs with
low-quality embedded OCR, and images use OCR. The current backend OCR path calls a local
Tesseract binary after rendering PDF pages with PyMuPDF. Standard Azure Functions zip
deployments should not be assumed to include Tesseract, so cloud OCR needs either a
custom runtime image that installs Tesseract or a managed OCR service such as Azure AI
Document Intelligence before scanned PDF extraction is considered production-ready.

Example local backend env shape:

```env
AZURE_STORAGE_ACCOUNT=fcswdevcwm2xrlu
AZURE_STORAGE_CONTAINER=app-assets
AZURE_STORAGE_CONNECTION_STRING=<connection-string>
```

Prefer managed identity or Azure app settings for deployed apps. Avoid committing storage keys or connection strings.

## Local Env File

Use `backend/.env.example` as the template for local configuration:

```sh
cp backend/.env.example backend/.env
```

Then fill in the real secret values locally. `backend/.env` is intentionally ignored by git.

Current env variables used by the backend:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string. |
| `AZURE_STORAGE_ACCOUNT` | Blob Storage account name. |
| `AZURE_STORAGE_CONTAINER` | Blob container name. |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage connection string for backend code or local scripts. |
| `INTERNAL_SERVICE_TOKEN` | Shared service token accepted by backend internal routes, including the feature-extractor analysis trigger. |
| `EMAIL_INTAKE_HOST` | IMAP host for email intake. |
| `EMAIL_INTAKE_PORT` | IMAP port, usually `993`. |
| `EMAIL_INTAKE_USERNAME` | IMAP username. |
| `EMAIL_INTAKE_PASSWORD` | IMAP password or app password. |
| `EMAIL_INTAKE_MAILBOX` | Source mailbox, default `INBOX`. |
| `EMAIL_INTAKE_SEARCH` | IMAP search criteria, default `UNSEEN`. |
| `EMAIL_INTAKE_PROCESSED_MAILBOX` | Mailbox for processed messages. |
| `EMAIL_INTAKE_FAILED_MAILBOX` | Mailbox for failed messages. |
| `EMAIL_INTAKE_DRY_RUN` | Keep `true` until moving messages is intended. |
| `EMAIL_INTAKE_OUTPUT_PATH` | Local JSONL audit output path. |
| `EMAIL_INTAKE_DEFAULT_UPLOADER_ID` | Contractor id assigned to emailed attachments until real contractor accounts exist. |
| `EMAIL_INTAKE_DEFAULT_DOCUMENT_TYPE` | Document type assigned to emailed attachments. |
| `DOCUMENT_PROCESSING_TIMER_SCHEDULE` | Azure Functions NCRONTAB schedule for draining queued document processing jobs. |
| `DOCUMENT_PROCESSING_LIMIT` | Maximum queued document jobs to drain per timer tick. |
| `DOCUMENT_OCR_TESSERACT_CMD` | Optional OCR command path, default `tesseract`. |
| `DOCUMENT_OCR_LANGUAGE` | Optional OCR language code, default `eng`. |
| `DOCUMENT_OCR_MAX_PAGES` | Optional max scanned PDF pages to OCR synchronously, default `25`; use `0` for no limit. |
| `DOCUMENT_OCR_DPI_SCALE` | Optional PDF render scale before OCR, default `2.0`. |

## Adding More People

Invite a guest user in Microsoft Entra ID, then assign access at the resource-group scope:

```sh
SCOPE="/subscriptions/99596387-8247-4e94-9917-cf8bc695f106/resourceGroups/federal-center-sw-dev"

az role assignment create \
  --assignee "person@example.com" \
  --role "Contributor" \
  --scope "$SCOPE"
```

Use `Reader` for view-only access, `Contributor` for normal development access, and `Owner` only for people who should manage permissions too.

## Cost And Cleanup

Current resources are low-cost/free-account-oriented, but still monitor spend in Azure Cost Management.

Useful links:

- Cost Management: <https://portal.azure.com/#view/Microsoft_Azure_CostManagement/Menu/~/overview>
- Azure free services: <https://azure.microsoft.com/free>

Delete the full project cloud environment only when the team no longer needs it:

```sh
az group delete --name federal-center-sw-dev
```

That command deletes the PostgreSQL server, database, storage account, blobs, permissions at that scope, and every other resource in the project resource group.
