# L1/L2 Architecture Alignment

Source: `Details.pdf` architecture slides.

## L1 / High-Level Architecture

| PDF architecture element | Implementation |
|---|---|
| TOM knowledge base | `pipeline/` source ingestion and sample TOM data |
| Ingestion pipeline | `pipeline/logic_app_workflow.json`, `/api/v1/ingest/*` |
| Store raw data in Azure Blob storage | `infra/main.bicep` storage account + `raw` container |
| Process and transform data | `pipeline/excel_to_graph.py`, `pipeline/document_to_vector.py`, Databricks workspace in IaC |
| Store processed data in Azure Blob storage | `processed` container in IaC |
| Vectorize document using Azure OpenAI / approved embedding model | `backend/app/clients/embedding_client.py` via KPMG Workbench gateway |
| Load vectors into index | `backend/app/clients/vector_azure_search.py`, Search index in IaC |
| Load edges and nodes to graph DB | `pipeline/excel_to_graph.py`, Neo4j/Gremlin `upsert_nodes` and `upsert_edges` |
| Azure Web App / SPA with SSO | `frontend/` React + MSAL; deployment through Azure DevOps pipeline |
| API Management | APIM service, product, and TOM API in `infra/main.bicep` |
| Intelligent agent routing and query decomposition | `backend/app/services/router.py`, `decomposition.py`, `orchestrator.py` |
| Vectorize user query | `EmbeddingClient` |
| Create Cypher / graph query | `TextToCypher`, Gremlin fast paths and read-only LLM traversal |
| Azure AI Search query/index store | `AzureSearchVectorStore`, `tom-knowledge` index in IaC |
| Graph Cosmos DB / Neo4j prototype | `graph_gremlin.py`, `graph_neo4j.py`, Gremlin DB/graph in IaC |
| Azure AI Foundry / Workbench LLM model | `LLMClient` using enterprise Workbench OpenAI-compatible endpoint |
| Chat persona and synthesis | `backend/app/services/synthesis.py`, `prompts/templates.py` |
| TOM asset generation | `visualizer.py`, `exporter.py`, export API |
| Memory Cosmos DB and Redis cache | `audit_store.py` for Cosmos audit, `cache.py` for Redis prompt window |
| Azure Monitor, Key Vault, Log Analytics | `core/telemetry.py`, `clients/keyvault.py`, IaC resources |
| RBAC | Entra token validation and app-role checks in `core/security.py` |

## L2 / Container Architecture

| PDF L2 element | Implementation |
|---|---|
| KPMG Knowledge Manager / Professional personas | Entra-authenticated users; `knowledge_manager` role gates ingestion; selectable chat personas in the SPA (`persona` field on `/api/v1/chat`, persona-aware synthesis prompts) |
| Global Azure Entra ID | MSAL frontend and backend JWT validation |
| Global One Platform SharePoint | Logic App ingestion definition with SharePoint trigger |
| Azure DevOps | `azure-pipelines.yml` validates, builds, and packages |
| Global Advisory Cloud - West Europe | IaC default `location = westeurope` |
| TOM Knowledge Assistant Agent / Container App | FastAPI backend in Container Apps |
| Single Page Application | `frontend/` React SPA; SPA Container App (`ca-*-spa`) behind the Application Gateway in `infra/main.bicep`, image built from `frontend/Dockerfile` |
| App Gateway / API gateway | Application Gateway (WAF_v2, public entry, path-based SPA/API routing) + APIM API/product shell in `infra/main.bicep`; TLS cert and final DNS are tenant handoff |
| Intelligent Agent Routing | Router/decomposer/orchestrator services |
| Database / model data | Cosmos Gremlin graph, Azure AI Search vector index, Cosmos audit |
| Azure Container Registry | ACR in IaC and Docker pipeline |
| Azure Key Vault | Key Vault in IaC and runtime hydration |
| Log Analytics Workspace | IaC and telemetry |
| Application Insights | IaC and OpenTelemetry setup |
| SFTP storage | ADLS Gen2/SFTP-enabled storage account |
| Workbench OpenAI APIs | `LLMClient` and `EmbeddingClient` |
| Consumer application/API access | APIM API + subscription-required product |

## Tenant-Specific Handoff

These are intentionally parameterized rather than hard-coded: Entra app IDs and
roles, SharePoint managed connector IDs, Workbench endpoint, Defender scan
endpoint, APIM gateway/front-door DNS, and final KPMG security approvals.
