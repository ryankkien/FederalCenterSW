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

output functionAppHostName string = functionApp.properties.defaultHostName
output postgresFullyQualifiedDomainName string = postgresServer.properties.fullyQualifiedDomainName
output appStorageBlobEndpoint string = appStorage.properties.primaryEndpoints.blob
