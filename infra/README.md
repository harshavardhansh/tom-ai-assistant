# Infrastructure

`main.bicep` provisions the core Azure platform for the TOM AI Knowledge
Assistant in West Europe.

## Included

- User-assigned managed identity.
- VNet with Container Apps and private endpoint subnets.
- Private DNS zones and private endpoints for Key Vault, Blob, AI Search,
  Cosmos Gremlin, Cosmos NoSQL memory, and Redis.
- Log Analytics and Application Insights.
- Key Vault with RBAC, soft delete, purge protection, and public access disabled.
- ACR with managed-identity pull.
- Storage raw/processed/quarantine containers.
- SFTP-enabled ADLS Gen2 storage for the L2 landing zone.
- Logic App ingestion workflow shell for SharePoint to Defender to Blob to processor.
- Databricks workspace for heavy raw-to-processed transforms.
- Azure AI Search service plus `tom-knowledge` vector/semantic index.
- Cosmos DB for Gremlin database `tom` and graph `processes`.
- Cosmos DB NoSQL memory database/container for conversation audit.
- Azure Cache for Redis.
- APIM product and API shell for TOM-as-a-service.
- Internal Container Apps environment and backend app wiring.

## Deploy

```bash
az group create -n rg-tom-dev -l westeurope
az deployment group create -g rg-tom-dev -f infra/main.bicep \
  -p env=dev \
  -p backendImage=<acr-login-server>/tom-backend:<tag> \
  -p allowedCorsOrigins=https://<spa-host> \
  -p workbenchOpenAIBaseUrl=https://<kpmg-workbench-gateway> \
  -p entraTenantId=<tenant-id> \
  -p entraClientId=<client-id> \
  -p entraApiAudience=<api-audience> \
  -p defenderScanEndpoint=https://<enterprise-scan-endpoint> \
  -p sharePointSite=https://<tenant>.sharepoint.com/sites/<site> \
  -p sharePointLibrary=/Shared%20Documents/TOM \
  -p ingestionProcessorEndpoint=https://<apim-or-backend-endpoint>
```

## Required Key Vault Secrets

Store these after provisioning. The backend hydrates blank settings from Key
Vault through managed identity.

```bash
az keyvault secret set --vault-name <vault> --name workbench-openai-api-key --value <key>
az keyvault secret set --vault-name <vault> --name search-api-key --value <key>
az keyvault secret set --vault-name <vault> --name gremlin-key --value <key>
az keyvault secret set --vault-name <vault> --name cosmos-memory-key --value <key>
az keyvault secret set --vault-name <vault> --name redis-url --value <rediss-url>
```

## Tenant-Specific Follow-Up

The Bicep creates the platform primitives. Environment owners still need to bind
approved Entra app roles, approve Logic App managed connections to SharePoint,
enable the ingestion workflow after connector binding, finalize DNS/front-door
routing, configure budget alerts, set Azure DevOps service connections, and
complete KPMG security sign-off.
