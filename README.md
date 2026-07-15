# TOM AI Knowledge Assistant

Conversational access to KPMG's Target Operating Model. Consultants can ask
plain-English questions about process hierarchy (L0-L4), steps, roles, controls,
and concepts, then receive grounded, citation-backed answers with optional
process diagrams and export to Word, PDF, or PowerPoint.

Classification: KPMG Confidential - Internal Use Only

## Three Brains

- Graph Navigator: structured questions over the process graph, such as "List L2 processes under Finance".
- Knowledge Retriever: conceptual questions over supporting documents, grounded with citations.
- Intelligent Router: chooses graph, vector, or multi-hop and runs decomposed branches in parallel.

The app also includes process-flow SVG visualization, Office/PDF export, Redis
conversation context, Cosmos DB conversation audit, grounded follow-up
suggestions, and selectable chat personas (KPMG Professional / Knowledge
Manager) per the approved L2 architecture.

## Run Offline

The app runs locally with sample Finance data and deterministic fallbacks.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
curl -s localhost:8000/api/v1/chat -H "Content-Type: application/json" ^
  -d "{\"question\":\"List all L2 processes under Finance\"}"
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Enterprise Configuration

Set local values in `backend/.env`; in Azure, secrets are resolved from Key
Vault and non-secret endpoints are injected by Bicep.

```bash
GRAPH_BACKEND=gremlin
VECTOR_BACKEND=azure_search
CACHE_BACKEND=redis
WORKBENCH_OPENAI_BASE_URL=https://<kpmg-workbench-gateway>
WORKBENCH_OPENAI_API_KEY=<secret>
AUTH_DISABLED=false
ALLOWED_CORS_ORIGINS=https://<spa-host>
DEFENDER_SCAN_ENDPOINT=https://<enterprise-scan-endpoint>
```

For `uat` and `prod`, startup fails closed unless Entra ID, Workbench, Gremlin,
Azure AI Search, Redis, Cosmos memory, Key Vault, CORS, and Defender scan
settings are present.

## Repository Layout

```text
docs/                 Plan, architecture, compliance, API reference
backend/              FastAPI app and tests
pipeline/             SharePoint/Defender/Blob ingestion scripts and sample data
frontend/             React + Vite SPA with MSAL
infra/                Azure Bicep for the private platform
docker-compose.yml    Local dev stack
```

## Status

Working offline/dev: routing, graph navigation, hybrid retrieval with rerank and
threshold filtering, multi-hop orchestration, grounded fallback synthesis,
session memory, durable audit abstraction, process-flow visualization, export,
and ingestion control endpoints.

Enterprise wiring required before UAT/prod: KPMG Workbench credentials, Entra ID
app registration and app roles, Key Vault secrets for data-plane keys, Defender
scan endpoint, Logic App managed connections, and approved network/DNS values.
The Bicep provisions the core private Azure platform, Search index, Cosmos
Gremlin graph, Cosmos memory container, Redis, and APIM API/product shell.

See `docs/ARCHITECTURE_ALIGNMENT.md` for the explicit L1/L2 mapping from
`Details.pdf` to this implementation.
