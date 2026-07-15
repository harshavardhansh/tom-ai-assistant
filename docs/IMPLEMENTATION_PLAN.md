# TOM AI Knowledge Assistant — Implementation Plan (Agile)

**Document classification:** KPMG Confidential — Internal Use Only
**Version:** 1.0 (Build phase entry)
**Owner:** TOM AI Engagement Team
**Aligned to:** POC presentation (April 2026), approved L1/L2 architecture, and KT meeting notes.

---

## 1. Product vision

Enable any KPMG consultant to ask plain-English questions about a client's Target Operating Model — process hierarchy (L0–L4), steps, roles, controls, and leading practices across sectors/functions/technologies — and receive an instant, citation-grounded, professionally formatted answer, optionally exported to Word / PDF / PowerPoint with auto-generated process diagrams. The same capability is exposed as an API ("TOM-as-a-service") for downstream consumer applications.

### 1.1 Scope guardrails (from KT)

- **Phase-1 vertical slice:** one sector, one function (**Finance**), one technology — to prove data-integration complexity and the ingestion ontology. Designed to be extended to other functions/sectors by uploading additional source files.
- **Hierarchy:** L0→L4 stored **only** in the graph database. Supporting documents (policy, tech-agnostic/tech-specific narratives) stored **only** in the vector database.
- **Prototype vs production:** Neo4j (prototype/sandbox) → **Azure Cosmos DB for Apache Gremlin** (production). LLM/embeddings via **KPMG Workbench OpenAI APIs** (API-key), not direct public OpenAI.

### 1.2 Success metrics (measurable, baselined against POC)

| Metric | Baseline (pre-TOM AI) | Target |
|---|---|---|
| Median answer latency (single-hop) | 15–45 min (manual) | ≤ 8 s p50, ≤ 20 s p95 |
| Multi-hop answer latency | n/a | ≤ 30 s p95 |
| Asset (Word/PPT/PDF) generation | 2–4 h manual | ≤ 15 s |
| Answer groundedness (eval set, citation-faithful) | n/a | ≥ 95% |
| Routing accuracy (graph vs vector vs multihop) | n/a | ≥ 92% on labelled eval set |
| Retrieval relevance uplift from reranking | n/a | ≥ +40% nDCG@5 (matches POC finding) |
| Hallucination rate (eval set) | n/a | ≤ 2% |
| ARIS BPM license dependency | 100% | eliminated for in-scope process lookups |

---

## 2. Definition of Ready / Definition of Done

**Definition of Ready (story can enter a sprint):**
1. Acceptance criteria written and testable.
2. Dependencies identified and unblocked (or stubbed).
3. Data-classification and security impact noted.
4. Test approach agreed (unit / integration / eval).
5. Estimate (story points) assigned by the team.

**Definition of Done (story can be closed):**
1. Code merged to `main` via PR with ≥ 1 approval (Azure DevOps).
2. Unit tests added; coverage on changed modules ≥ 80%.
3. SAST (CodeQL/SonarQube), dependency scan, and secret scan pass in CI.
4. No hard-coded secrets — all via Azure Key Vault / managed identity.
5. Telemetry (logs + traces + key metrics) emitted.
6. Docs updated (README / ADR / API spec where relevant).
7. Acceptance criteria demonstrably met (demo or test evidence).

**Story-point scale:** Fibonacci (1, 2, 3, 5, 8, 13). 1 SP ≈ ½ day for a mid-level engineer; 13 SP must be split.

---

## 3. Epic map

| Epic | Title | Goal | Indicative SP |
|---|---|---|---|
| **E0** | Foundation & DevSecOps | Azure landing zone, IaC, CI/CD, secrets, RBAC | 42 |
| **E1** | Knowledge ingestion pipeline | SharePoint → Defender → Blob → graph + vector | 63 |
| **E2** | Graph knowledge layer (Brain 1) | Ontology L0–L4, Cosmos Gremlin/Neo4j, text-to-query | 71 |
| **E3** | Vector knowledge layer (Brain 2) | Azure AI Search hybrid + rerank + grounding | 55 |
| **E4** | Router & orchestration (Brain 3) | Routing, multi-hop decomposition, synthesis, memory | 68 |
| **E5** | TOM asset generation & visualizer | Process-JSON → diagram, Word/PDF/PPT export | 47 |
| **E6** | Conversational web app (SPA) | Entra ID SSO, chat UX, badges, export UI | 52 |
| **E7** | API productization | TOM-as-a-service, APIM, consumer onboarding | 29 |
| **E8** | Security, compliance & governance | Data classification, DLP, responsible AI, audit | 44 |
| **E9** | Observability, performance & reliability | Monitor/App Insights, caching, SLOs | 31 |
| **E10** | QA, UAT & release | Test + RAG eval harness, UAT, go-live, hypercare | 38 |
| | **Total** | | **540** |

---

## 4. Epics → Stories → Tasks → Subtasks

> IDs: `E#-S#` story, `T#` task, `t#` subtask. Priority: **P0** (must), **P1** (should), **P2** (could).

### E0 — Foundation & DevSecOps

**E0-S1 — Provision Azure landing zone (Global Advisory Cloud, West Europe)** · 8 SP · P0
*As a* platform engineer *I want* an IaC-defined resource group and core services *so that* environments are reproducible and policy-compliant.
- Acceptance: `bicep`/Terraform deploys RG, networking, and tags in West Europe; `what-if` is clean; Azure Policy assignments green.
- T1 Author IaC for RG + VNet + private endpoints
  - t1 Subnets for App, data, integration; t2 Private DNS zones; t3 NSGs
- T2 Provision Key Vault, Log Analytics, App Insights, Container Registry
- T3 Apply Azure Policy (region lock, tag enforcement, no public blob)
- T4 Wire managed identities (system + user-assigned) for app + pipeline

**E0-S2 — CI/CD via Azure DevOps** · 8 SP · P0
- Acceptance: PR pipeline runs lint + unit + SAST + secret scan; main pipeline builds container, pushes to ACR, deploys to dev Container App.
- T1 PR validation pipeline (ruff, mypy, pytest, coverage gate)
- T2 Container build + ACR push (multi-stage Dockerfile)
- T3 Deploy stage to Container Apps (dev) with revision strategy
- T4 Branch policies, required reviewers, build validation

**E0-S3 — Secrets & configuration management** · 5 SP · P0
- Acceptance: zero secrets in repo; app reads Workbench API key, DB creds from Key Vault via managed identity; local dev uses `.env` (gitignored).
- T1 Key Vault references in Container App env; T2 `config.py` precedence (env → Key Vault → default); T3 secret rotation runbook.

**E0-S4 — Environment strategy (dev/test/UAT/prod)** · 5 SP · P0
- Acceptance: four parameterised environments; promotion is config-only; data isolation enforced.

**E0-S5 — Repository, ADRs, coding standards** · 3 SP · P1
- Acceptance: repo scaffold, ADR template, CONTRIBUTING, pre-commit hooks.

**E0-S6 — Container App + ingress + SSO front door** · 8 SP · P0
- Acceptance: Container App hosting backend behind App Gateway/Front Door; Entra ID app registration created; health probe green.

**E0-S7 — Cost & capacity baseline** · 5 SP · P2
- Acceptance: cost estimate per environment; autoscale rules drafted; budget alerts set.

---

### E1 — Knowledge ingestion pipeline

**E1-S1 — Logic App: pull TOM assets from Global One Platform (SharePoint)** · 8 SP · P0
*so that* curated TOM files flow into the platform automatically after Knowledge-Manager upload.
- Acceptance: on new/changed file in the approved SharePoint library, Logic App copies it to a staging container; run history shows success; retries on transient failure.
- T1 SharePoint trigger (delta on approved library/folder)
- T2 Service principal / managed identity auth to SharePoint
- T3 Copy to `raw-staging` blob; t1 idempotency by content hash; t2 dead-letter on failure

**E1-S2 — Microsoft Defender malware scan gate** · 5 SP · P0
- Acceptance: every file is scanned before processing; infected/blocked files are quarantined and alerted; clean files advance to `raw` container.
- T1 Defender for Storage on staging; T2 quarantine container + alert; T3 promote-clean step.

**E1-S3 — Raw + processed blob zones** · 3 SP · P0
- Acceptance: `raw`, `processed`, `quarantine` containers with lifecycle + immutability (WORM) on raw; private endpoints only.

**E1-S4 — Excel → graph (nodes & edges) converter** · 13 SP · P0
*Port and harden the POC Python script.*
- Acceptance: given an ARIS-exported hierarchical Excel/CSV for Finance or any future function, produce validated node + edge artifacts covering L0→L4, including process-flow JSON attached to L1 nodes; every node carries sector/function/technology metadata; generated role/control identifiers are metadata-aware to avoid cross-vertical collisions; schema-validated; deterministic re-runs upsert (no duplicates).
- T1 Define canonical row schema + validation (pandas + pydantic)
- T2 Build hierarchy resolver L0→L4 (parent/child by code)
  - t1 Detect orphan/missing-parent rows; t2 cycle detection
- T3 Emit nodes (Process, Role, Control, Policy) + edges (HAS_SUB_PROCESS, PERFORMED_BY, HAS_CONTROL)
- T4 Attach process-flow JSON as L1 attribute (steps, role, next[])
- T5 Upsert loader (Gremlin prod / Neo4j dev) with `MERGE` semantics
- T6 Reconciliation report (counts per level, dropped rows, warnings)

**E1-S5 — Document → vector chunker & embedder** · 8 SP · P0
- Acceptance: supporting docs (policy, tech-agnostic/specific narratives) are chunked, assigned deterministic content-hash IDs, embedded via Workbench `text-embedding-ada-002` (1536-dim), and indexed in Azure AI Search with metadata (source, page, classification, sector, function, technology).
- T1 Loaders (docx/pdf/pptx/md); T2 semantic chunking + overlap; T3 embedding batch with retry/backoff; T4 index upload + metadata; T5 incremental re-index by content hash.

**E1-S6 — Databricks transform job (optional heavy transform)** · 8 SP · P1
- Acceptance: Databricks workspace job performs large-scale cleansing/normalisation between raw and processed for big uploads; parametrised by sector/function.

**E1-S7 — Pipeline orchestration & scheduling** · 5 SP · P1
- Acceptance: end-to-end run (SharePoint→Defender→Blob→graph+vector) is orchestrated, observable, and re-runnable; failure in any step alerts and does not corrupt indexes.

**E1-S8 — Ingestion eval & data-quality gate** · 5 SP · P1
- Acceptance: automated checks (referential integrity in graph, embedding coverage, no empty chunks) must pass before an upload is marked "live".

---

### E2 — Graph knowledge layer (Brain 1: Graph Navigator)

**E2-S1 — TOM ontology & graph schema (L0–L4)** · 8 SP · P0
- Acceptance: documented ontology (node labels, properties, edge types, constraints) covering Finance; uniqueness constraints on process code; reviewed by TOM SME.
- T1 Node/edge model + property dictionary; T2 constraints/indexes; T3 ontology doc + diagram.

**E2-S2 — Graph store abstraction (Neo4j dev ↔ Cosmos Gremlin prod)** · 13 SP · P0
- Acceptance: a single `GraphStore` interface; Neo4j backend for dev, Gremlin backend for Cosmos; switching is config-only; integration tests pass against both.
- T1 Interface (`query`, `upsert_nodes`, `upsert_edges`, `natural_language_query`)
- T2 Neo4j implementation (driver, sessions, retries)
- T3 Gremlin implementation (Cosmos partition strategy, RU budget)
- T4 In-memory fallback for offline dev/tests

**E2-S3 — Text-to-Cypher / Text-to-Gremlin generation** · 13 SP · P0
*Brain 1 core.*
- Acceptance: NL question → safe, parameterised query → executed → JSON; restricted to read-only; schema-aware prompting; rejects/repairs invalid queries; ≥ 90% execution success on eval set.
- T1 Schema-grounded prompt (inject labels/edges/props)
- T2 Query generation via Workbench LLM
- T3 Safety: read-only allow-list, depth/row caps, parameter binding (injection-safe)
- T4 Self-repair loop on syntax/execution error (max N retries)
- T5 Dialect adapter (Cypher↔Gremlin) behind store interface

**E2-S4 — Canonical graph query templates** · 5 SP · P1
- Acceptance: tested templates for "list Ln under X", "count sub-processes", "roles/controls for process", "process-flow JSON for L1" used as few-shot + fast-path.

**E2-S5 — Process-flow JSON extraction (`apoc.convert.fromJsonMap`)** · 5 SP · P0
- Acceptance: process-flow JSON stored as string on L1 nodes is parsed reliably (POC gotcha #1); equivalent handling for Gremlin; returns structured steps.

**E2-S6 — Graph synthesis (JSON → professional narrative)** · 5 SP · P0
- Acceptance: query JSON + question + history → narrative with bullet list; deterministic structure; no invented nodes.

---

### E3 — Vector knowledge layer (Brain 2: Knowledge Retriever)

**E3-S1 — Azure AI Search index design** · 5 SP · P0
- Acceptance: index with vector + text fields, deterministic `content_hash`, filterable metadata (classification, sector, function, technology), HNSW config; created via IaC.

**E3-S2 — Hybrid search (vector + BM25, RRF merge)** · 8 SP · P0
- Acceptance: query embedding + keyword (BM25) run together; results merged via RRF; top-K (default 5) returned with scores; matches POC flow.

**E3-S3 — Cross-encoder reranking + relevance threshold** · 8 SP · P0
*POC: +40% quality; threshold prevents hallucinations.*
- Acceptance: (query, doc) pairs reranked; below-threshold contexts dropped; eval shows ≥ +40% nDCG@5 vs no-rerank; empty-after-threshold path returns an honest "insufficient grounding" response.
- T1 Reranker interface; T2 semantic-ranker / cross-encoder backend; T3 threshold config + telemetry; T4 local lexical+vector fallback.

**E3-S4 — Citation-grounded answer synthesis** · 8 SP · P0
- Acceptance: synthesis cites retrieved chunks (source + locator); answers constrained to retrieved context; refuses when ungrounded; citations render in UI.

**E3-S5 — Embedding client (Workbench ada-002)** · 5 SP · P0
- Acceptance: batched embeddings via Workbench OpenAI endpoint; 1536-dim; retry/backoff; offline deterministic stub for tests.

**E3-S6 — Vector store abstraction + local fallback** · 5 SP · P1
- Acceptance: `VectorStore` interface; Azure AI Search backend + in-memory backend; switch is config-only.

---

### E4 — Router & orchestration (Brain 3: Intelligent Router)

**E4-S1 — Dual-layer query router (keyword + LLM fallback)** · 8 SP · P0
- Acceptance: fast keyword classifier handles obvious cases (`list/how many/Ln/under` → GRAPH; `what is/difference/why` → VECTOR); ambiguous → LLM classifier; returns one of GRAPH/VECTOR/MULTIHOP with confidence; ≥ 92% accuracy on eval set; latency for keyword path < 5 ms.

**E4-S2 — Multi-hop detection** · 5 SP · P0
- Acceptance: detect compound intent (conjunctions + mixed graph/vector signals) → MULTIHOP (POC example "List L2 Finance processes AND explain TOM").

**E4-S3 — Question decomposition (LLM)** · 8 SP · P0
- Acceptance: compound question → ordered sub-questions, each tagged with a route; validated JSON; degrades gracefully to single-route on failure.

**E4-S4 — Parallel sub-query execution** · 8 SP · P0
- Acceptance: sub-questions run concurrently (thread/async pool) with per-branch timeout; partial results handled; total latency ≈ slowest branch, not sum.

**E4-S5 — Result aggregation & unified synthesis** · 8 SP · P0
- Acceptance: merge branch results + metadata + history → single coherent answer addressing all parts; combined citations; route badge MULTIHOP.

**E4-S6 — Conversation memory (last 5 Q&A) + Cosmos/Redis** · 8 SP · P0
- Acceptance: per-session memory of last 5 Q&A pairs used for follow-ups; backed by Redis (cache) + Cosmos (durable); in-memory fallback for dev; TTL + size cap.

**E4-S7 — Suggested next questions** · 5 SP · P1
- Acceptance: after each answer, 2–4 relevant follow-ups generated from the **actual** data returned (not generic).

**E4-S8 — Orchestrator (single entry point)** · 8 SP · P0
- Acceptance: `Orchestrator.answer(question, session)` runs route → retrieve → synthesize → suggest → persist; emits route badge + timings; one well-typed response object.

---

### E5 — TOM asset generation & process visualizer

**E5-S1 — Process-flow layout engine (BFS + swimlanes + elbow routing)** · 13 SP · P0
*POC gotcha #2.*
- Acceptance: given process-flow JSON (steps with id/name/role/next[]), compute positions via BFS, assign swimlanes by role, route connectors with elbows; deterministic; handles branches/merges; no overlapping nodes.
- T1 Parse + validate flow JSON; T2 BFS rank/position; T3 swimlane assignment by role; T4 elbow connector routing; T5 render to SVG.

**E5-S2 — Diagram renderer (SVG, self-contained)** · 5 SP · P0
- Acceptance: clean SVG output, no external diagramming tools (POC: "no external tools needed"); embeddable in UI and exports.

**E5-S3 — Markdown intermediate + format renderers** · 8 SP · P0
*POC gotcha #3.*
- Acceptance: answer → Markdown intermediate → Word (.docx), PDF, PowerPoint (.pptx); each renders headings, bullets, tables, and the process diagram; consistent across formats.
- T1 Markdown assembler; T2 docx renderer (python-docx); T3 pptx renderer (python-pptx); T4 pdf renderer; T5 diagram embedding per format.

**E5-S4 — Prompt-templated TOM asset generation** · 8 SP · P1
- Acceptance: parametrised prompt templates produce new TOM assets (e.g., process narratives, RACI) grounded in graph/vector data; templates versioned.

**E5-S5 — Export API + download UX** · 5 SP · P0
- Acceptance: `/export` returns the requested artifact; UI export menu (Word/PDF/PPT) triggers download; large exports stream.

**E5-S6 — KPMG branding & document classification footer** · 3 SP · P1
- Acceptance: exports carry KPMG template styling and the mandated classification/footer text.

---

### E6 — Conversational web app (SPA)

**E6-S1 — SPA scaffold + design system** · 5 SP · P0
- Acceptance: SPA builds; tokenised theme; responsive to mobile; keyboard focus visible; reduced-motion respected.

**E6-S2 — Entra ID SSO (MSAL) + token to API** · 8 SP · P0
- Acceptance: user signs in with KPMG Entra ID; access token attached to API calls; silent refresh; sign-out; protected routes.

**E6-S3 — Chat experience** · 8 SP · P0
- Acceptance: streaming/typed answers, message history, copy, retry; markdown rendering; loading states; error states with recovery guidance.

**E6-S4 — Route badge + citations + sources panel** · 5 SP · P1
- Acceptance: each answer shows GRAPH/VECTOR/MULTIHOP badge and clickable citations; sources panel lists evidence.

**E6-S5 — Inline process diagram rendering** · 5 SP · P1
- Acceptance: SVG process diagrams render inline with pan/zoom on large flows.

**E6-S6 — Export menu + suggested questions** · 5 SP · P1
- Acceptance: export to Word/PDF/PPT from a message; suggested follow-ups are clickable and re-submit.

**E6-S7 — Accessibility & i18n baseline** · 5 SP · P2
- Acceptance: WCAG 2.1 AA checks pass on key flows; strings externalised.

**E6-S8 — Session/memory UX (new chat, history)** · 3 SP · P1
- Acceptance: start new chat, view recent sessions; memory window respected.

---

### E7 — API productization ("TOM-as-a-service")

**E7-S1 — Public-facing query API + OpenAPI spec** · 8 SP · P0
- Acceptance: documented, versioned REST API for query/export; OpenAPI published; backwards-compatibility policy.

**E7-S2 — Azure API Management + key/scoped access** · 8 SP · P0
- Acceptance: APIM front door; product/subscription keys; rate limits/quotas; per-consumer policies; matches L2 "Consumer Application API calls … (API Key)".

**E7-S3 — Consumer onboarding & RBAC scopes** · 5 SP · P1
- Acceptance: a consumer member firm app can be onboarded with scoped access; least-privilege; audit of consumer calls.

**E7-S4 — Usage metering & throttling** · 8 SP · P1
- Acceptance: per-consumer usage metered; throttling + 429 semantics; cost attribution.

---

### E8 — Security, compliance & governance (KPMG)

**E8-S1 — Data classification & handling** · 8 SP · P0
- Acceptance: every ingested artifact tagged (Public/Internal/Confidential/Highly Confidential); classification propagates to chunks, citations, and exports; Confidential+ excluded from non-entitled consumers.

**E8-S2 — Identity, RBAC & least privilege** · 8 SP · P0
- Acceptance: Entra ID groups → app roles; Azure RBAC on every resource; no standing admin; PIM for elevation; managed identities everywhere.

**E8-S3 — Responsible AI guardrails** · 8 SP · P0
- Acceptance: prompt-injection defences, grounding/refusal on low confidence, content safety on input/output, PII detection/redaction, "no advice beyond TOM scope" guard; documented model/use-case risk assessment.

**E8-S4 — Audit logging & data lineage** · 8 SP · P1
- Acceptance: immutable audit of who-asked-what-when, which sources answered, and every export; lineage from answer → chunk/node → source file.

**E8-S5 — DLP, network isolation & key management** · 8 SP · P1
- Acceptance: private endpoints, no public data egress, Defender gates, Key Vault-managed keys/rotation; egress allow-list.

**E8-S6 — Privacy, retention & right-to-erasure** · 4 SP · P2
- Acceptance: conversation retention policy; deletion workflow; DPIA recorded.

---

### E9 — Observability, performance & reliability

**E9-S1 — Telemetry (App Insights + OpenTelemetry traces)** · 8 SP · P0
- Acceptance: distributed traces across router→retrieval→synthesis→export; per-stage latency; correlation IDs; logs to Log Analytics.

**E9-S2 — Caching (Redis) for embeddings & hot answers** · 5 SP · P1
- Acceptance: embedding cache + recent-answer cache reduce p50 latency and Workbench token spend; cache hit-rate dashboarded.

**E9-S3 — SLOs, dashboards & alerting** · 8 SP · P1
- Acceptance: SLOs (latency, availability, groundedness) tracked on dashboards; alerts on breach; on-call runbook.

**E9-S4 — Load & latency testing** · 5 SP · P1
- Acceptance: load test to expected concurrency; meets latency targets in §1.2; autoscale validated.

**E9-S5 — Resilience (retries, timeouts, circuit breakers)** · 5 SP · P2
- Acceptance: every external call has timeout + retry/backoff + breaker; graceful degradation paths tested.

---

### E10 — QA, UAT & release

**E10-S1 — Test strategy & pyramid** · 5 SP · P0
- Acceptance: unit/integration/e2e split documented; coverage gates in CI; flaky-test policy.

**E10-S2 — RAG evaluation harness** · 13 SP · P0
- Acceptance: labelled eval set (routing labels, gold answers, gold citations) with automated scoring for routing accuracy, groundedness, citation faithfulness, hallucination rate, retrieval nDCG; runs in CI nightly and gates releases against §1.2 thresholds.

**E10-S3 — UAT with consultants** · 8 SP · P0
- Acceptance: UAT script across graph/vector/multihop + exports; consultant sign-off; defects triaged with buffer (per KT timeline).

**E10-S4 — Security review & pen test** · 5 SP · P0
- Acceptance: security review and pen test completed; criticals/highs remediated before go-live.

**E10-S5 — Go-live & hypercare** · 5 SP · P1
- Acceptance: production cutover runbook; rollback plan; 2-week hypercare with daily triage.

---

## 5. Release roadmap (sprints)

Two-week sprints. Timeline mirrors the KT phases — **Build → QA → UAT → Production**, with explicit buffers for bug-fixing and security reviews.

| Sprint | Theme | Primary epics | Exit criteria |
|---|---|---|---|
| **S1** | Foundations | E0, start E1 | IaC deploys dev; CI/CD green; repo scaffold; SharePoint→Blob skeleton |
| **S2** | Ingestion + graph base | E1, E2-S1/S2 | Finance Excel→graph upsert working; graph schema live; Defender gate |
| **S3** | Brain 1 + Brain 2 core | E2-S3..S6, E3-S1..S3 | Text-to-query executing; hybrid search + rerank returning grounded top-K |
| **S4** | Brain 3 + synthesis | E3-S4..S6, E4-S1..S5 | Single-hop graph + vector answers with citations & badges end-to-end |
| **S5** | Multi-hop + memory + visualizer | E4-S6..S8, E5-S1..S3 | Multi-hop answers; last-5 memory; SVG diagrams; Word/PDF/PPT export |
| **S6** | Web app | E6 | SSO chat app with badges, citations, diagrams, export, suggestions |
| **S7** | Productization + security/compliance | E7, E8 | TOM-as-a-service via APIM; data classification + RAI guardrails + audit |
| **S8 (QA)** | Hardening + observability | E9, E10-S1/S2 | SLO dashboards; RAG eval harness gating; load test passes; **bug buffer** |
| **S9 (UAT)** | UAT + security review | E10-S3/S4 | Consultant sign-off; pen-test remediation; **buffer for fixes** |
| **S10 (Prod)** | Go-live + hypercare | E10-S5 | Production cutover; rollback ready; hypercare underway |

---

## 6. RAID log (initial)

**Risks**
- R1 — Cosmos Gremlin lacks 1:1 Cypher feature parity (e.g., APOC). *Mitigation:* dialect adapter + canonical templates; validate parity tests early (E2-S2/S3).
- R2 — Workbench OpenAI rate limits / token cost. *Mitigation:* caching (E9-S2), batching, prompt size discipline.
- R3 — Data-integration complexity beyond Finance. *Mitigation:* ontology designed for extension; phase-1 slice de-risks.
- R4 — Hallucination/groundedness on edge queries. *Mitigation:* rerank threshold + refusal path + eval gate (E3-S3, E8-S3, E10-S2).
- R5 — SharePoint/Defender integration latency for large files. *Mitigation:* async pipeline + Databricks for heavy transforms.

**Assumptions**
- A1 — Workbench exposes OpenAI-compatible chat + embedding deployments (gpt-4-class + ada-002) reachable by API key.
- A2 — ARIS exports are available as hierarchical Excel/CSV per function.
- A3 — KPMG Entra ID tenant + Global Advisory Cloud (West Europe) subscription available.

**Issues**
- I1 — Final classification rules for consumer-firm data sharing to be confirmed with Risk.

**Dependencies**
- D1 — Knowledge Manager curates & approves SharePoint uploads (gates ingestion).
- D2 — TOM SME validates ontology and gold eval answers.
- D3 — Security team for pen test + RAI sign-off windows.

---

## 7. Non-functional requirements (NFRs)

- **Performance:** see §1.2 latency targets.
- **Availability:** ≥ 99.5% for the web app; graceful degradation if a single brain is unavailable.
- **Security:** private networking, managed identity, Key Vault, Defender, audit, classification; OWASP LLM Top-10 controls.
- **Compliance:** KPMG data-classification & confidentiality, regional data residency (West Europe), responsible-AI risk assessment, DPIA.
- **Maintainability:** clean interfaces (graph/vector/LLM abstractions), ≥ 80% coverage on core, ADRs for key decisions.
- **Extensibility:** add a new function/sector by uploading files + minimal ontology config — no code change to the query path.
- **Cost:** caching + autoscale-to-zero on non-prod; cost dashboard and budget alerts.
