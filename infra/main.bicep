// ---------------------------------------------------------------------------
// TOM AI Knowledge Assistant - Azure infrastructure
// Scope: resource group
//
// Covers the L1/L2 architecture primitives:
// - Application Gateway (WAF_v2) as the public entry point for SPA + API
// - Container Apps backend + SPA on a VNet-integrated environment
// - Key Vault, Storage, Azure AI Search, Cosmos Gremlin, Cosmos NoSQL memory,
//   Redis, App Insights, Log Analytics, ACR
// - Private endpoints + Private DNS for data-plane services
// - SFTP-enabled ADLS Gen2 landing storage
// - Logic App shell for SharePoint -> Defender -> Blob -> processor ingestion
// - Databricks workspace for heavy raw-to-processed transforms
// - Azure AI Search vector/semantic index
// - Cosmos Gremlin database/graph and Cosmos NoSQL conversation-audit container
// - APIM product/API shell for TOM-as-a-service onboarding
// ---------------------------------------------------------------------------

@allowed(['dev', 'test', 'uat', 'prod'])
param env string = 'dev'
param location string = 'westeurope'
param namePrefix string = 'tom'
param backendImage string = ''

@description('SPA (frontend) container image. Leave empty to skip the SPA Container App.')
param spaImage string = ''

@description('Comma-separated SPA origins allowed by the backend CORS policy.')
param allowedCorsOrigins string

@description('KPMG Workbench OpenAI-compatible gateway base URL.')
param workbenchOpenAIBaseUrl string

@description('Microsoft Entra tenant ID.')
param entraTenantId string

@description('SPA/API application client ID.')
param entraClientId string

@description('Expected API audience/app ID URI.')
param entraApiAudience string

@description('Enterprise malware scan endpoint used by /api/v1/ingest/scan.')
param defenderScanEndpoint string

@description('Approved SharePoint site identifier/URL for TOM assets. Wired to the Logic App after managed connection approval.')
param sharePointSite string = ''

@description('Approved SharePoint library/folder path for TOM assets.')
param sharePointLibrary string = ''

@description('Backend processor endpoint reachable by Logic App. Use APIM/backend private endpoint value per environment.')
param ingestionProcessorEndpoint string = ''

param vnetAddressPrefix string = '10.42.0.0/16'
param appSubnetPrefix string = '10.42.1.0/24'
param privateEndpointSubnetPrefix string = '10.42.2.0/24'
param appGatewaySubnetPrefix string = '10.42.3.0/24'

var suffix = '${namePrefix}-${env}'
var compact = replace(suffix, '-', '')
var processorEndpoint = empty(ingestionProcessorEndpoint) ? 'https://configure-processor-endpoint' : ingestionProcessorEndpoint
var tags = {
  application: 'tom-ai-knowledge-assistant'
  environment: env
  classification: 'KPMG-Confidential'
}

// ---- Network ---------------------------------------------------------------
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-${suffix}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: [
      {
        name: 'snet-containerapps'
        properties: {
          addressPrefix: appSubnetPrefix
          delegations: [
            {
              name: 'container-apps-delegation'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-appgw'
        properties: {
          addressPrefix: appGatewaySubnetPrefix
        }
      }
    ]
  }
}

var appSubnetId = '${vnet.id}/subnets/snet-containerapps'
var privateEndpointSubnetId = '${vnet.id}/subnets/snet-private-endpoints'
var appGatewaySubnetId = '${vnet.id}/subnets/snet-appgw'

var privateZones = [
  'privatelink.vaultcore.azure.net'
  'privatelink.blob.core.windows.net'
  'privatelink.search.windows.net'
  'privatelink.gremlin.cosmos.azure.com'
  'privatelink.documents.azure.com'
  'privatelink.redis.cache.windows.net'
]

resource dnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in privateZones: {
  name: zone
  location: 'global'
  tags: tags
}]

resource dnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zone, i) in privateZones: {
  parent: dnsZones[i]
  name: 'link-${compact}-${i}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}]

// ---- Identity --------------------------------------------------------------
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${suffix}'
  location: location
  tags: tags
}

// ---- Observability ---------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${suffix}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 90
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${suffix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ---- Secrets ---------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${suffix}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
    publicNetworkAccess: 'Disabled'
  }
}

resource kvPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-kv-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'kv'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource kvDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: kvPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'vault', properties: { privateDnsZoneId: dnsZones[0].id } }
    ]
  }
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, uami.id, 'kv-secrets-user')
  scope: keyVault
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// ---- Container registry ----------------------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${compact}'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, 'acr-pull')
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// ---- Storage (raw / processed / quarantine) --------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'st${compact}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    isHnsEnabled: true
    isSftpEnabled: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 30 }
    containerDeleteRetentionPolicy: { enabled: true, days: 30 }
  }
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'raw'
}
resource processedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'processed'
}
resource quarantineContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'quarantine'
}

// Logic App shell for the L2 SharePoint ingestion path. Managed API connection
// IDs are tenant-owned and supplied after KPMG connection approval, so the
// workflow is deployed disabled until those values are bound.
resource ingestionWorkflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-${suffix}-ingest'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Disabled'
    definition: loadJsonContent('../pipeline/logic_app_workflow.json').definition
    parameters: {
      sharePointSite: { value: sharePointSite }
      sharePointLibrary: { value: sharePointLibrary }
      rawContainerUri: { value: 'https://${storage.name}.blob.core.windows.net/raw' }
      quarantineContainerUri: { value: 'https://${storage.name}.blob.core.windows.net/quarantine' }
      processorEndpoint: { value: processorEndpoint }
      '$connections': { value: {} }
    }
  }
}

resource storagePe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-blob-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'blob'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: ['blob']
        }
      }
    ]
  }
}

resource storageDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: storagePe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'blob', properties: { privateDnsZoneId: dnsZones[1].id } }
    ]
  }
}

// ---- Azure AI Search (vector store) ---------------------------------------
resource search 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: 'srch-${suffix}'
  location: location
  tags: tags
  sku: { name: 'standard' }
  properties: {
    replicaCount: env == 'prod' ? 2 : 1
    partitionCount: 1
    semanticSearch: 'standard'
    publicNetworkAccess: 'disabled'
  }
}

resource searchIndex 'Microsoft.Search/searchServices/indexes@2024-03-01-preview' = {
  parent: search
  name: 'tom-knowledge'
  properties: {
    fields: [
      { name: 'id', type: 'Edm.String', key: true, searchable: false, filterable: true }
      { name: 'content', type: 'Edm.String', searchable: true, retrievable: true }
      { name: 'source', type: 'Edm.String', searchable: true, filterable: true, retrievable: true }
      { name: 'locator', type: 'Edm.String', searchable: true, filterable: true, retrievable: true }
      { name: 'classification', type: 'Edm.String', searchable: true, filterable: true, retrievable: true }
      { name: 'sector', type: 'Edm.String', searchable: true, filterable: true, retrievable: true }
      { name: 'function', type: 'Edm.String', searchable: true, filterable: true, retrievable: true }
      { name: 'technology', type: 'Edm.String', searchable: true, filterable: true, retrievable: true }
      { name: 'content_hash', type: 'Edm.String', searchable: false, filterable: true, retrievable: true }
      {
        name: 'content_vector'
        type: 'Collection(Edm.Single)'
        searchable: true
        retrievable: false
        dimensions: 1536
        vectorSearchProfile: 'tom-vector-profile'
      }
    ]
    vectorSearch: {
      algorithms: [
        { name: 'tom-hnsw', kind: 'hnsw' }
      ]
      profiles: [
        { name: 'tom-vector-profile', algorithm: 'tom-hnsw' }
      ]
    }
    semantic: {
      configurations: [
        {
          name: 'tom-semantic'
          prioritizedFields: {
            contentFields: [
              { fieldName: 'content' }
            ]
          }
        }
      ]
    }
  }
}

resource searchPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-search-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'search'
        properties: {
          privateLinkServiceId: search.id
          groupIds: ['searchService']
        }
      }
    ]
  }
}

resource searchDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: searchPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'search', properties: { privateDnsZoneId: dnsZones[2].id } }
    ]
  }
}

// ---- Cosmos DB for Gremlin (process graph) --------------------------------
resource graphCosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-graph-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [{ name: 'EnableGremlin' }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0 }]
    publicNetworkAccess: 'Disabled'
  }
}

resource gremlinDb 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-05-15' = {
  parent: graphCosmos
  name: 'tom'
  properties: {
    resource: { id: 'tom' }
  }
}

resource gremlinGraph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-05-15' = {
  parent: gremlinDb
  name: 'processes'
  properties: {
    resource: {
      id: 'processes'
      partitionKey: {
        paths: ['/pk']
        kind: 'Hash'
      }
    }
    options: {
      throughput: env == 'prod' ? 1000 : 400
    }
  }
}

resource graphPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-gremlin-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'gremlin'
        properties: {
          privateLinkServiceId: graphCosmos.id
          groupIds: ['Gremlin']
        }
      }
    ]
  }
}

resource graphDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: graphPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'gremlin', properties: { privateDnsZoneId: dnsZones[3].id } }
    ]
  }
}

// ---- Cosmos DB for durable conversation memory/audit -----------------------
resource memoryCosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-mem-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0 }]
    publicNetworkAccess: 'Disabled'
  }
}

resource memoryDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: memoryCosmos
  name: 'tom'
  properties: { resource: { id: 'tom' } }
}

resource memoryContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: memoryDb
  name: 'conversation_audit'
  properties: {
    resource: {
      id: 'conversation_audit'
      partitionKey: { paths: ['/session_id'], kind: 'Hash' }
      defaultTtl: 15552000 // 180 days; align with final KPMG retention approval
    }
    options: { throughput: 400 }
  }
}

resource memoryPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-cosmos-mem-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'documents'
        properties: {
          privateLinkServiceId: memoryCosmos.id
          groupIds: ['Sql']
        }
      }
    ]
  }
}

resource memoryDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: memoryPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'documents', properties: { privateDnsZoneId: dnsZones[4].id } }
    ]
  }
}

// ---- Redis (hot conversation window / cache) -------------------------------
resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: 'redis-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'Standard', family: 'C', capacity: 1 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
  }
}

resource redisPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-redis-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'redis'
        properties: {
          privateLinkServiceId: redis.id
          groupIds: ['redisCache']
        }
      }
    ]
  }
}

resource redisDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: redisPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'redis', properties: { privateDnsZoneId: dnsZones[5].id } }
    ]
  }
}

// ---- Databricks workspace (heavy ingestion transform) ----------------------
resource databricks 'Microsoft.Databricks/workspaces@2023-02-01' = {
  name: 'dbw-${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'standard'
  }
  properties: {
    managedResourceGroupId: subscriptionResourceId('Microsoft.Resources/resourceGroups', 'rg-${suffix}-databricks-managed')
    publicNetworkAccess: 'Disabled'
    requiredNsgRules: 'NoAzureDatabricksRules'
  }
}

// ---- API Management shell --------------------------------------------------
resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: 'apim-${suffix}'
  location: location
  tags: tags
  sku: {
    name: env == 'prod' ? 'StandardV2' : 'Developer'
    capacity: 1
  }
  properties: {
    publisherEmail: 'tom-ai-platform@kpmg.com'
    publisherName: 'KPMG TOM AI Platform'
  }
}

resource apimProduct 'Microsoft.ApiManagement/service/products@2023-09-01-preview' = {
  parent: apim
  name: 'tom-as-a-service'
  properties: {
    displayName: 'TOM as a Service'
    description: 'Entitlement-scoped API product for TOM AI Assistant consumers.'
    subscriptionRequired: true
    approvalRequired: true
    state: 'published'
  }
}

resource apimApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'tom-ai-assistant'
  properties: {
    displayName: 'TOM AI Assistant API'
    path: 'tom-ai'
    protocols: ['https']
    serviceUrl: processorEndpoint
    subscriptionRequired: true
    type: 'http'
  }
}

resource apimProductApi 'Microsoft.ApiManagement/service/products/apis@2023-09-01-preview' = {
  parent: apimProduct
  name: apimApi.name
  dependsOn: [
    apimApi
  ]
}

// ---- Container Apps environment + backend ---------------------------------
resource caeEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${suffix}'
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: appSubnetId
      internal: true
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource backend 'Microsoft.App/containerApps@2024-03-01' = if (!empty(backendImage)) {
  name: 'ca-${suffix}-backend'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: caeEnv.id
    configuration: {
      ingress: { external: false, targetPort: 8000, transport: 'auto' }
      registries: [{ server: acr.properties.loginServer, identity: uami.id }]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'ENVIRONMENT', value: env }
            { name: 'GRAPH_BACKEND', value: 'gremlin' }
            { name: 'VECTOR_BACKEND', value: 'azure_search' }
            { name: 'CACHE_BACKEND', value: 'redis' }
            { name: 'AUTH_DISABLED', value: 'false' }
            { name: 'ALLOWED_CORS_ORIGINS', value: allowedCorsOrigins }
            { name: 'KEY_VAULT_URI', value: keyVault.properties.vaultUri }
            { name: 'WORKBENCH_OPENAI_BASE_URL', value: workbenchOpenAIBaseUrl }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_CLIENT_ID', value: entraClientId }
            { name: 'ENTRA_API_AUDIENCE', value: entraApiAudience }
            { name: 'DEFENDER_SCAN_ENDPOINT', value: defenderScanEndpoint }
            { name: 'SEARCH_ENDPOINT', value: 'https://${search.name}.search.windows.net' }
            { name: 'SEARCH_INDEX', value: searchIndex.name }
            { name: 'GREMLIN_ENDPOINT', value: 'wss://${graphCosmos.name}.gremlin.cosmos.azure.com:443/' }
            { name: 'GREMLIN_DATABASE', value: gremlinDb.name }
            { name: 'GREMLIN_GRAPH', value: gremlinGraph.name }
            { name: 'COSMOS_MEMORY_ENDPOINT', value: memoryCosmos.properties.documentEndpoint }
            { name: 'COSMOS_MEMORY_DATABASE', value: memoryDb.name }
            { name: 'COSMOS_MEMORY_CONTAINER', value: memoryContainer.name }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
          ]
        }
      ]
      scale: { minReplicas: env == 'prod' ? 2 : 1, maxReplicas: 6 }
    }
  }
}

// ---- SPA Container App (L2: Single Page Application) -----------------------
resource spa 'Microsoft.App/containerApps@2024-03-01' = if (!empty(spaImage)) {
  name: 'ca-${suffix}-spa'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: caeEnv.id
    configuration: {
      // Internal-only ingress: the SPA is fronted by the Application Gateway
      // (public entry point + WAF), per the approved L2 architecture.
      ingress: { external: false, targetPort: 80, transport: 'auto' }
      registries: [{ server: acr.properties.loginServer, identity: uami.id }]
    }
    template: {
      containers: [
        {
          name: 'spa'
          image: spaImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: env == 'prod' ? 2 : 1, maxReplicas: 4 }
    }
  }
}

// ---- Application Gateway (L2: public entry point, WAF, regional availability)
resource appGwWafPolicy 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2023-11-01' = if (!empty(spaImage) && !empty(backendImage)) {
  name: 'wafpol-${suffix}'
  location: location
  tags: tags
  properties: {
    policySettings: {
      state: 'Enabled'
      mode: env == 'prod' ? 'Prevention' : 'Detection'
      requestBodyCheck: true
    }
    managedRules: {
      managedRuleSets: [
        { ruleSetType: 'OWASP', ruleSetVersion: '3.2' }
      ]
    }
  }
}

resource appGwPip 'Microsoft.Network/publicIPAddresses@2023-11-01' = if (!empty(spaImage) && !empty(backendImage)) {
  name: 'pip-appgw-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource appGateway 'Microsoft.Network/applicationGateways@2023-11-01' = if (!empty(spaImage) && !empty(backendImage)) {
  name: 'agw-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'WAF_v2', tier: 'WAF_v2', capacity: env == 'prod' ? 2 : 1 }
    firewallPolicy: { id: appGwWafPolicy.id }
    gatewayIPConfigurations: [
      { name: 'appgw-ipcfg', properties: { subnet: { id: appGatewaySubnetId } } }
    ]
    frontendIPConfigurations: [
      { name: 'appgw-fe-public', properties: { publicIPAddress: { id: appGwPip.id } } }
    ]
    frontendPorts: [
      // TLS listener/cert (Key Vault certificate + approved DNS) is a
      // tenant-specific handoff; the HTTP listener is replaced at onboarding.
      { name: 'port-80', properties: { port: 80 } }
    ]
    backendAddressPools: [
      {
        name: 'spa-pool'
        properties: { backendAddresses: [{ fqdn: spa.properties.configuration.ingress.fqdn }] }
      }
      {
        name: 'api-pool'
        properties: { backendAddresses: [{ fqdn: backend.properties.configuration.ingress.fqdn }] }
      }
    ]
    backendHttpSettingsCollection: [
      {
        name: 'https-settings'
        properties: {
          port: 443
          protocol: 'Https'
          pickHostNameFromBackendAddress: true
          requestTimeout: 120
        }
      }
    ]
    httpListeners: [
      {
        name: 'public-http'
        properties: {
          frontendIPConfiguration: { id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', 'agw-${suffix}', 'appgw-fe-public') }
          frontendPort: { id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', 'agw-${suffix}', 'port-80') }
          protocol: 'Http'
        }
      }
    ]
    urlPathMaps: [
      {
        name: 'spa-api-paths'
        properties: {
          defaultBackendAddressPool: { id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', 'agw-${suffix}', 'spa-pool') }
          defaultBackendHttpSettings: { id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', 'agw-${suffix}', 'https-settings') }
          pathRules: [
            {
              name: 'api'
              properties: {
                paths: ['/api/*']
                backendAddressPool: { id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', 'agw-${suffix}', 'api-pool') }
                backendHttpSettings: { id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', 'agw-${suffix}', 'https-settings') }
              }
            }
          ]
        }
      }
    ]
    requestRoutingRules: [
      {
        name: 'route-all'
        properties: {
          ruleType: 'PathBasedRouting'
          priority: 100
          httpListener: { id: resourceId('Microsoft.Network/applicationGateways/httpListeners', 'agw-${suffix}', 'public-http') }
          urlPathMap: { id: resourceId('Microsoft.Network/applicationGateways/urlPathMaps', 'agw-${suffix}', 'spa-api-paths') }
        }
      }
    ]
  }
}

output appIdentityClientId string = uami.properties.clientId
output keyVaultUri string = keyVault.properties.vaultUri
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output gremlinEndpoint string = 'wss://${graphCosmos.name}.gremlin.cosmos.azure.com:443/'
output memoryCosmosEndpoint string = memoryCosmos.properties.documentEndpoint
output acrLoginServer string = acr.properties.loginServer
output apimGatewayUrl string = apim.properties.gatewayUrl
output appGatewayPublicIp string = (!empty(spaImage) && !empty(backendImage)) ? appGwPip.properties.ipAddress : ''
