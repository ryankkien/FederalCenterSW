targetScope = 'resourceGroup'

@description('Azure region for app-facing resources.')
param appLocation string

@description('Azure region for PostgreSQL. The current dev server is in Central US because East US was restricted when it was created.')
param postgresLocation string

@description('Primary private blob storage account for app files and email intake stub output.')
param appStorageAccountName string

@description('Private blob container for app files and email intake stub output.')
param appAssetsContainerName string

@description('Storage account used by the Azure Functions runtime and Flex Consumption package deployment.')
param functionStorageAccountName string

@description('Blob container used by Azure Functions Flex Consumption for package deployment.')
param functionPackageContainerName string

@description('Azure Key Vault name for development app secrets.')
param keyVaultName string

@description('Azure Functions Flex Consumption plan name.')
param functionPlanName string

@description('User-assigned managed identity name for the email intake Function App.')
param functionManagedIdentityName string

@description('Email intake Azure Function App name.')
param functionAppName string

@description('PostgreSQL Flexible Server name.')
param postgresServerName string

@description('PostgreSQL app database name.')
param postgresDatabaseName string

@description('Existing PostgreSQL administrator login. The password is intentionally not managed in this adoption template.')
param postgresAdministratorLogin string

@description('Azure Container Registry name for pipeline service images.')
param acrName string

@description('ACA managed environment name.')
param acaEnvironmentName string

@description('Container App name for the Feature Extractor service.')
param featureExtractorAppName string

@description('User-assigned managed identity name for the Feature Extractor Container App.')
param featureExtractorManagedIdentityName string

@description('Feature Extractor Docker image tag to deploy.')
param featureExtractorImageTag string = 'latest'

@description('Container App name for the Backend API service.')
param backendAppName string

@description('User-assigned managed identity name for the Backend API Container App.')
param backendManagedIdentityName string

@description('Azure Static Web App name for the Frontend.')
param staticWebAppName string

@description('Azure region for the Static Web App (limited regions supported).')
param staticWebAppLocation string = 'eastus2'

var keyVaultSecretsUserRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

var keyVaultSecretUris = {
  appStorageConnectionString: '${keyVault.properties.vaultUri}secrets/app-storage-connection-string'
  databaseUrl: '${keyVault.properties.vaultUri}secrets/database-url'
  emailIntakeHost: '${keyVault.properties.vaultUri}secrets/email-intake-host'
  emailIntakePassword: '${keyVault.properties.vaultUri}secrets/email-intake-password'
  emailIntakeUsername: '${keyVault.properties.vaultUri}secrets/email-intake-username'
  functionStorageConnectionString: '${keyVault.properties.vaultUri}secrets/function-storage-connection-string'
  openaiApiKey: '${keyVault.properties.vaultUri}secrets/openai-api-key'
  resendApiKey: '${keyVault.properties.vaultUri}secrets/resend-api-key'
}

var keyVaultReferences = {
  appStorageConnectionString: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.appStorageConnectionString})'
  databaseUrl: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.databaseUrl})'
  emailIntakeHost: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.emailIntakeHost})'
  emailIntakePassword: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.emailIntakePassword})'
  emailIntakeUsername: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.emailIntakeUsername})'
  functionStorageConnectionString: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.functionStorageConnectionString})'
  openaiApiKey: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.openaiApiKey})'
  resendApiKey: '@Microsoft.KeyVault(SecretUri=${keyVaultSecretUris.resendApiKey})'
}

resource appStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: appStorageAccountName
  location: appLocation
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource appBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: appStorage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      allowPermanentDelete: false
      enabled: false
    }
  }
}

resource appAssetsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: appBlobService
  name: appAssetsContainerName
  properties: {
    defaultEncryptionScope: '$account-encryption-key'
    denyEncryptionScopeOverride: false
    publicAccess: 'None'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: appLocation
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: false
    enableRbacAuthorization: true
    enableSoftDelete: true
    publicNetworkAccess: 'Enabled'
    softDeleteRetentionInDays: 90
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource functionStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: functionStorageAccountName
  location: appLocation
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource functionBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: functionStorage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      allowPermanentDelete: false
      enabled: false
    }
  }
}

resource functionPackageContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: functionBlobService
  name: functionPackageContainerName
  properties: {
    defaultEncryptionScope: '$account-encryption-key'
    denyEncryptionScopeOverride: false
    publicAccess: 'None'
  }
}

resource functionManagedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: functionManagedIdentityName
  location: appLocation
}

resource functionKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionManagedIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: functionManagedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: functionPlanName
  location: appLocation
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
    size: 'FC1'
    family: 'FC'
    capacity: 0
  }
  properties: {
    reserved: true
    zoneRedundant: false
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: appLocation
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${functionManagedIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: functionPlan.id
    clientAffinityEnabled: false
    httpsOnly: false
    keyVaultReferenceIdentity: functionManagedIdentity.id
    storageAccountRequired: false
    siteConfig: {
      localMySqlEnabled: false
      netFrameworkVersion: 'v4.6'
    }
    functionAppConfig: {
      runtime: {
        name: 'python'
        version: '3.11'
      }
      deployment: {
        storage: {
          type: 'blobContainer'
          value: 'https://${functionStorage.name}.blob.${environment().suffixes.storage}/${functionPackageContainer.name}'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'DEPLOYMENT_STORAGE_CONNECTION_STRING'
          }
        }
      }
      scaleAndConcurrency: {
        instanceMemoryMB: 2048
        maximumInstanceCount: 100
        alwaysReady: []
      }
    }
  }
}

resource functionAppSettings 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: functionApp
  name: 'appsettings'
  dependsOn: [
    functionKeyVaultSecretsUser
  ]
  properties: {
    AI_INLINE_PROCESSING_ENABLED: 'false'
    AI_MAX_RETRIES: '3'
    AI_PROCESSING_ENABLED: 'false'
    AI_PROVIDER: 'openai'
    AI_REQUEST_TIMEOUT_SECONDS: '60'
    AZURE_STORAGE_CONNECTION_STRING: keyVaultReferences.appStorageConnectionString
    AZURE_STORAGE_CONTAINER: appAssetsContainerName
    AZURE_STORAGE_ACCOUNT: appStorage.name
    AzureWebJobsStorage: keyVaultReferences.functionStorageConnectionString
    DATABASE_URL: keyVaultReferences.databaseUrl
    DEPLOYMENT_STORAGE_CONNECTION_STRING: keyVaultReferences.functionStorageConnectionString
    DOCUMENT_OCR_DPI_SCALE: '2.0'
    DOCUMENT_OCR_LANGUAGE: 'eng'
    DOCUMENT_OCR_MAX_PAGES: '25'
    DOCUMENT_OCR_TESSERACT_CMD: 'tesseract'
    PORTFOLIO_LESSONS_TIMER_SCHEDULE: '0 15 */6 * * *'
    PORTFOLIO_LESSONS_PERIOD: 'fy26'
    EMAIL_INTAKE_AUTO_REPLY_ENABLED: 'false'
    EMAIL_INTAKE_DEFAULT_DOCUMENT_TYPE: 'Email Attachment'
    EMAIL_INTAKE_DEFAULT_UPLOADER_ID: 'contractor-demo'
    EMAIL_INTAKE_DRY_RUN: 'false'
    EMAIL_INTAKE_FAILED_MAILBOX: 'Failed'
    EMAIL_INTAKE_HOST: keyVaultReferences.emailIntakeHost
    EMAIL_INTAKE_LIMIT: '25'
    EMAIL_INTAKE_MAILBOX: 'INBOX'
    EMAIL_INTAKE_PASSWORD: keyVaultReferences.emailIntakePassword
    EMAIL_INTAKE_PROCESSED_MAILBOX: 'Processed'
    EMAIL_INTAKE_SEARCH: 'UNSEEN'
    EMAIL_INTAKE_STUB_BLOB_CONTAINER: appAssetsContainerName
    EMAIL_INTAKE_STUB_BLOB_ENABLED: 'true'
    EMAIL_INTAKE_STUB_BLOB_PREFIX: 'email-intake'
    EMAIL_INTAKE_TIMER_SCHEDULE: '0 */5 * * * *'
    EMAIL_INTAKE_USERNAME: keyVaultReferences.emailIntakeUsername
    FUNCTIONS_EXTENSION_VERSION: '~4'
    OPENAI_API_KEY: keyVaultReferences.openaiApiKey
    OPENAI_EMBEDDING_DIMENSIONS: '3072'
    OPENAI_EMBEDDING_MODEL: 'text-embedding-3-large'
    OPENAI_LLM_MODEL: 'gpt-5.5'
    RESEND_API_KEY: keyVaultReferences.resendApiKey
  }
}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresServerName
  location: postgresLocation
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdministratorLogin
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    availabilityZone: '2'
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    dataEncryption: {
      type: 'SystemManaged'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    replica: {
      role: 'Primary'
    }
    replicationRole: 'Primary'
    storage: {
      autoGrow: 'Disabled'
      iops: 120
      storageSizeGB: 32
      tier: 'P4'
    }
    version: '16'
  }
}

resource postgresVectorExtension 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'azure.extensions'
  properties: {
    value: 'vector'
    source: 'user-override'
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgresServer
  name: postgresDatabaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// --- Azure Container Registry ---

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: appLocation
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: true
  }
}

// --- ACA Environment (Log Analytics + Managed Environment) ---

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${acaEnvironmentName}-logs'
  location: appLocation
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${acaEnvironmentName}-appi'
  location: appLocation
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource acaEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: acaEnvironmentName
  location: appLocation
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// --- Feature Extractor Container App ---

resource featureExtractorManagedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: featureExtractorManagedIdentityName
  location: appLocation
}

resource featureExtractorKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, featureExtractorManagedIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: featureExtractorManagedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource featureExtractorApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: featureExtractorAppName
  location: appLocation
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${featureExtractorManagedIdentity.id}': {}
    }
  }
  dependsOn: [
    featureExtractorKeyVaultSecretsUser
  ]
  properties: {
    managedEnvironmentId: acaEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'storage-connection-string'
          keyVaultUrl: keyVaultSecretUris.appStorageConnectionString
          identity: featureExtractorManagedIdentity.id
        }
        {
          name: 'openai-api-key'
          keyVaultUrl: keyVaultSecretUris.openaiApiKey
          identity: featureExtractorManagedIdentity.id
        }
        {
          name: 'database-url'
          keyVaultUrl: keyVaultSecretUris.databaseUrl
          identity: featureExtractorManagedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'feature-extractor'
          image: '${acr.properties.loginServer}/feature-extractor:${featureExtractorImageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STORAGE_CONTAINER'
              value: appAssetsContainerName
            }
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
            {
              name: 'MODEL_PREFERENCE'
              value: 'openai'
            }
            {
              name: 'OPENAI_LLM_MODEL'
              value: 'gpt-5.4-mini'
            }
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'EMBEDDING_MODEL'
              value: 'text-embedding-3-small'
            }
            {
              name: 'APPINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 10
      }
    }
  }
}

// --- Backend Container App ---

resource backendManagedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: backendManagedIdentityName
  location: appLocation
}

resource backendKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, backendManagedIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: backendManagedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: appLocation
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendManagedIdentity.id}': {}
    }
  }
  dependsOn: [
    backendKeyVaultSecretsUser
  ]
  properties: {
    managedEnvironmentId: acaEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'storage-connection-string'
          keyVaultUrl: keyVaultSecretUris.appStorageConnectionString
          identity: backendManagedIdentity.id
        }
        {
          name: 'openai-api-key'
          keyVaultUrl: keyVaultSecretUris.openaiApiKey
          identity: backendManagedIdentity.id
        }
        {
          name: 'database-url'
          keyVaultUrl: keyVaultSecretUris.databaseUrl
          identity: backendManagedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: '${acr.properties.loginServer}/backend:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STORAGE_CONTAINER'
              value: appAssetsContainerName
            }
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
            {
              name: 'AUTH_MODE'
              value: 'mock'
            }
            {
              name: 'AI_PROVIDER'
              value: 'openai'
            }
            {
              name: 'AI_PROCESSING_ENABLED'
              value: 'true'
            }
            {
              name: 'APPINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 5
      }
    }
  }
}

// --- Frontend Static Web App ---

resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: staticWebAppName
  location: staticWebAppLocation
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {}
}

// Proxy /api/* from the SWA to the backend Container App (no frontend code changes needed)
resource linkedBackend 'Microsoft.Web/staticSites/linkedBackends@2023-01-01' = {
  parent: staticWebApp
  name: 'backend'
  properties: {
    backendResourceId: backendApp.id
    region: appLocation
  }
}

output functionAppHostName string = functionApp.properties.defaultHostName
output postgresFullyQualifiedDomainName string = postgresServer.properties.fullyQualifiedDomainName
output appStorageBlobEndpoint string = appStorage.properties.primaryEndpoints.blob
output keyVaultUri string = keyVault.properties.vaultUri
output acrLoginServer string = acr.properties.loginServer
output featureExtractorUrl string = 'https://${featureExtractorApp.properties.configuration.ingress.fqdn}'
output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
