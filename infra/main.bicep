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

@description('Azure Functions Flex Consumption plan name.')
param functionPlanName string

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

@description('Container App name for the Summarizer service.')
param summarizerAppName string

@description('Summarizer Docker image tag to deploy.')
param summarizerImageTag string = 'latest'

@description('Anthropic API key secret for the Summarizer.')
@secure()
param anthropicApiKey string = ''

@description('OpenAI API key secret for the Summarizer (used if Anthropic key is empty).')
@secure()
param openaiApiKey string = ''

@description('PostgreSQL connection string for the Summarizer.')
@secure()
param summarizerDatabaseUrl string = ''

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
  properties: {
    serverFarmId: functionPlan.id
    clientAffinityEnabled: false
    httpsOnly: false
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

// --- Summarizer Container App ---

resource summarizerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: summarizerAppName
  location: appLocation
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
          value: 'DefaultEndpointsProtocol=https;AccountName=${appStorage.name};AccountKey=${appStorage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        }
        {
          name: 'anthropic-api-key'
          value: anthropicApiKey
        }
        {
          name: 'openai-api-key'
          value: openaiApiKey
        }
        {
          name: 'database-url'
          value: summarizerDatabaseUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'summarizer'
          image: '${acr.properties.loginServer}/summarizer:${summarizerImageTag}'
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
              name: 'ANTHROPIC_API_KEY'
              secretRef: 'anthropic-api-key'
            }
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
            {
              name: 'MODEL_PREFERENCE'
              value: 'claude'
            }
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'EMBEDDING_MODEL'
              value: 'text-embedding-3-small'
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

output functionAppHostName string = functionApp.properties.defaultHostName
output postgresFullyQualifiedDomainName string = postgresServer.properties.fullyQualifiedDomainName
output appStorageBlobEndpoint string = appStorage.properties.primaryEndpoints.blob
output acrLoginServer string = acr.properties.loginServer
output summarizerUrl string = 'https://${summarizerApp.properties.configuration.ingress.fqdn}'
