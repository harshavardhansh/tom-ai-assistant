# Architecture

**Classification:** KPMG Confidential — Internal Use Only

The TOM AI Knowledge Assistant is an enterprise conversational system over KPMG's
Target Operating Model. It routes each question to the right knowledge source —
the **process graph**, the **document index**, or **both** — and synthesises a
grounded, citation-backed answer with optional auto-generated process diagrams and
Office/PDF export.

## The three brains

| Brain | Role | Implementation |
|---|---|---|
| **1 · Graph Navigator** | Structured hierarchy: list/count by level, roles, controls, process flows | `services/graph_navigator.py`, `clients/graph_*`, `services/text_to_cypher.py` |
| **2 · Knowledge Retriever** | Concepts & meaning from documents, grounded + cited | `services/knowledge_retriever.py`, `clients/vector_*`, `services/reranker.py` |
| **3 · Intelligent Router** | Decide graph vs vector vs multi-hop; decompose & combine | `services/router.py`, `services/decomposition.py`, `services/orchestrator.py` |

## Query flows (as demonstrated in the POC)

**Graph** — e.g. "List all L2 processes under Finance"
→ router (keyword) = GRAPH → graph store NL query (text-to-Cypher on Neo4j /
fast-path templates on Gremlin / pattern match offline) → narrative synthesis →
route badge `GRAPH` (+ diagram if a process flow is returned).

**Vector** — e.g. "What is AI-First TOM?"
→ router = VECTOR → embed query → hybrid search (vector + BM25, RRF) → cross-encoder
rerank + **relevance-threshold filtering** (drops weak passages; refuses if nothing
clears the bar) → grounded synthesis with `[n]` citations → badge `VECTOR`.

**Multi-hop** — e.g. "List L2 Finance processes AND explain TOM"
→ router detects compound intent = MULTIHOP → LLM/deterministic decomposition into
route-tagged sub-questions → **parallel execution** (ThreadPoolExecutor) → unified
synthesis with merged citations → badge `MULTIHOP`.

Every answer carries per-stage `timings_ms`. Redis/in-memory keeps the last 5
Q&A pairs per session for prompt continuity; Cosmos DB records durable
conversation audit when configured.

## Mapping to the approved L1 / L2 architecture

| Architecture element | This repo |
|---|---|
| Azure Web App / SPA with Entra ID SSO | `frontend/` (React + MSAL) |
| Intelligent agent: routing + query decomposition | `services/router.py`, `services/decomposition.py`, `services/orchestrator.py` |
| Vectorize user query (Workbench embeddings) | `clients/embedding_client.py` |
| Create Cypher query (Azure AI LLM) | `services/text_to_cypher.py` |
| Azure AI Search (query engine + index) | `clients/vector_azure_search.py` |
| Graph Cosmos DB (Gremlin); Neo4j for prototyping | `clients/graph_gremlin.py`, `clients/graph_neo4j.py` |
| TOM asset generation via prompt templates | `services/exporter.py`, `services/visualizer.py`, `prompts/templates.py` |
| Chat persona / synthesis (GPT-4-class) | `services/synthesis.py`, `clients/llm_client.py`; selectable personas (KPMG Professional / Knowledge Manager) in `prompts/templates.py` + SPA persona selector |
| Memory Cosmos DB + Redis cache | `services/memory.py`, `clients/cache.py`, `clients/audit_store.py` |
| Ingestion: SharePoint → Defender → Blob → graph + vector | `pipeline/` (`logic_app_workflow.json`, `excel_to_graph.py`, `document_to_vector.py`) |
| Key Vault, Azure Monitor, RBAC, Log Analytics | `clients/keyvault.py`, `core/telemetry.py`, `core/security.py`, `infra/main.bicep` |
| Azure DevOps | `azure-pipelines.yml` |
| Azure Logic App | `pipeline/logic_app_workflow.json` + Logic App resource in `infra/main.bicep` |
| SFTP / Blob landing zones | SFTP-enabled ADLS Gen2 storage in `infra/main.bicep` |
| Databricks transform workspace | Databricks workspace in `infra/main.bicep` |
| Consumer apps via API key ("TOM-as-a-service") | `api/` + APIM product/API shell in `infra/main.bicep` |

## Backend abstraction & environment switching

Every external dependency sits behind an interface with a config-only switch, so
the **same code** runs offline in dev and against Azure in production:

| Concern | Interface | Backends (`*_BACKEND`) |
|---|---|---|
| Graph | `GraphStore` | `memory` (offline) · `neo4j` (dev) · `gremlin` (prod) |
| Vector | `VectorStore` | `local` (offline) · `azure_search` (prod) |
| Cache/memory | `Cache` + `AuditStore` | `memory`/no-op audit (offline) · `redis` + Cosmos audit (prod) |
| LLM / embeddings | `LLMClient` / `EmbeddingClient` | Workbench gateway; deterministic fallback when unset |

Sector/function/technology scope is carried from chat and ingestion requests into
both stores. Graph nodes and vector chunks are tagged with this metadata, Azure
AI Search exposes it as filterable fields, and generated role/control graph codes
include metadata-aware hashes so future functions can be loaded without code
changes to the query path.

When the Workbench LLM is not configured, the system uses **faithful, deterministic
fallbacks** (keyword routing, template/pattern graph queries, structured synthesis)
rather than fabricating "AI" output — so it is honest and runnable with zero cloud
dependencies, and upgrades to full GPT-4-class behaviour by setting credentials.

## Request lifecycle (single entry point)

```
POST /api/v1/chat
        │
        ▼
  Orchestrator.answer(question, session)
        │  route ── Router (keyword → LLM fallback; multi-hop detection)
        │
   ┌────┴───────────────┬──────────────────────────┐
 GRAPH                VECTOR                      MULTIHOP
 graph store        hybrid search               decompose →
 → synth            → rerank+threshold          parallel branches
                    → grounded synth            → unified synth
        │                  │                          │
        └─────── visualize (SVG) · suggest · persist memory ───────┘
        ▼
   ChatResponse { answer, route, confidence, persona, citations,
                  process_diagram_svg, process_flow,
                  suggested_questions, timings_ms }
```

## Anti-hallucination controls

- Reranking + **relevance threshold**: low-relevance passages are dropped; if none
  remain, the retriever returns an explicit "insufficient grounding" answer.
- **Citation grounding**: vector answers cite numbered sources; synthesis is
  constrained to retrieved context.
- **Read-only graph queries**: generated Cypher is validated against a write/admin
  denylist and parameterised (injection-safe), with a bounded self-repair loop.
- **No fabricated facts offline**: deterministic fallbacks format only real data.
