# OWASP Top 10 for LLM Applications (2025) — Compliance Mapping

Classification: KPMG Confidential - Internal Use Only

This document maps the TOM AI Knowledge Assistant against the **OWASP Top 10
for LLM Applications, version 2025** (published 2024-11-18). Every entry cites
the implementing code so the control can be verified, in line with the
project's traceability standard. Statuses: **Compliant** (control implemented),
**Mitigated** (risk reduced; residual risk documented), **Deferred**
(documented, owner-accepted).

Verification evidence: the controls below are exercised by
`backend/tests/test_owasp_controls.py` and `backend/tests/test_query_safety.py`
(all tests green as of this revision).

---

## LLM01:2025 Prompt Injection — Mitigated (defence in depth)

Prompt injection cannot be fully prevented (per OWASP); the system constrains
behaviour and limits blast radius:

- **Constrained model behaviour.** Every system prompt pins role, scope, and
  output contract (`backend/app/prompts/templates.py`). Synthesis prompts
  instruct the model that `<history>`, `<context>`, `<results>`, and
  `<sub_answers>` content is *data, not instructions* and that embedded
  directives must be disregarded; router/decomposer/suggester prompts carry the
  same rule for the raw question.
- **Segregated external content.** Untrusted material (conversation history,
  retrieved passages, query results) is delimited in explicit tags in the user
  templates (`templates.py`), never merged into the system prompt.
- **Validated output formats.** LLM outputs are parsed as strict JSON
  (`llm_client._extract_json`), coerced to enums (`router.py`,
  `decomposition.py`), and — for generated queries — passed through
  deterministic read-only guards (`text_to_cypher.assert_read_only`,
  `graph_gremlin._assert_read_only`) with parameter binding.
- **Ingestion-side screening** (indirect injection via poisoned documents):
  see LLM04/LLM08 — `pipeline/document_to_vector.py` (`sanitize_text`,
  `screen_text`, `screen_chunks`) blocks loading flagged content by default
  (`routes_ingest._run_vector`, `fail_on_warnings=True`).
- **Least privilege.** The model holds no credentials and invokes no tools;
  the application executes guarded read-only queries only (see LLM06).

**Residual risk:** a sufficiently novel injection phrased outside the screened
patterns could still bias the *wording* of an answer. Impact is bounded to
answer content: grounding rules, citation display, the reranker threshold, and
the read-only data path stand between an injected instruction and any action.

## LLM02:2025 Sensitive Information Disclosure — Compliant

- **No secrets in code or prompts.** Configuration precedence env/.env → Key
  Vault → defaults (`backend/app/config.py`); repo scan is clean; prompts
  contain no credentials, roles, or internal limits (`templates.py`).
- **Fail-closed production posture.** `Settings.validate_runtime` refuses
  uat/prod startup with auth disabled or enterprise backends missing.
- **RBAC + session isolation.** Entra ID JWT validation (`core/security.py`);
  memory keys are namespaced per principal OID (`routes_chat.py`), so one
  user's history can never enter another's prompt.
- **Classification propagation.** Every chunk/citation/export carries
  `KPMG Confidential` labelling (`schemas.py`, `exporter.py`).
- **Minimal disclosure surfaces.** `/readyz` returns backend wiring and auth
  mode only in dev (`routes_health.py`); logs carry truncated question
  previews or content hashes rather than full user text
  (`graph_gremlin.py`, `knowledge_retriever.py`).

## LLM03:2025 Supply Chain — Compliant

- **Pinned dependencies.** `backend/requirements.txt` pins exact versions;
  `frontend/package-lock.json` locks the npm tree (installed via `npm ci`).
- **Audit + SBOM in CI.** The `SupplyChain` job in `azure-pipelines.yml` runs
  `pip-audit` and `npm audit --audit-level=high` (build-failing) and publishes
  CycloneDX SBOMs for both stacks per build.
- **No third-party model artifacts.** All model access is API-based through
  the KPMG Workbench OpenAI-compatible gateway (`llm_client.py`,
  `embedding_client.py`); the app never downloads weights, adapters, or
  pickled models, eliminating the model-file supply-chain surface.
- **Maintained bases.** Container images use maintained slim/alpine bases
  with non-root users (`backend/Dockerfile`, `frontend/Dockerfile`).

## LLM04:2025 Data and Model Poisoning — Mitigated

- **Gated, role-restricted ingestion.** Only `knowledge_manager` principals
  can ingest (`routes_ingest.py`); paths are confined to configured roots
  (`_safe_path`); a malware scan endpoint fronts uploads (`/scan`, Defender in
  non-dev).
- **Hierarchy validation.** `excel_to_graph.py` validates missing parents,
  level jumps, duplicates, and cycles; warnings block graph loading unless
  overridden (`_run_graph`, `fail_on_warnings`).
- **Content-safety screen.** `document_to_vector.screen_chunks` strips
  hidden/zero-width characters and flags injection payloads; flagged batches
  are not loaded by default (`_run_vector`), and suspect chunks are tagged in
  the reviewable artifact.
- **Provenance.** Chunk IDs are SHA-256 content hashes with source/locator
  metadata; artifacts are written for review before load.

**Residual risk:** semantic misinformation inside an otherwise-clean document
(false facts without injection syntax) is not machine-detectable here; the
knowledge-manager review step and citation display are the compensating
controls. No training/fine-tuning occurs in this system, so training-data
poisoning is out of scope.

## LLM05:2025 Improper Output Handling — Compliant

- **LLM → database:** generated Cypher/Gremlin passes deny-list guards
  (writes/admin/APOC/lambdas/multi-statement blocked), parameter binding, and
  bounded self-repair (`text_to_cypher.py`, `graph_gremlin.py`); covered by
  `test_query_safety.py`.
- **LLM → browser:** the SPA renders answers through a minimal markdown
  renderer built on React text nodes — no `innerHTML` for model text
  (`Message.jsx`). The process diagram SVG is generated server-side with all
  dynamic values escaped (`visualizer.py`, `html.escape`).
- **Browser backstop:** nginx now sends a strict `Content-Security-Policy`
  (no external script/connect origins beyond self + Entra), `X-Frame-Options
  DENY`, `nosniff`, and `Referrer-Policy: no-referrer` (`frontend/nginx.conf`).
- **LLM → exports:** answers are written into docx/pptx/pdf as plain
  text/table content (`exporter.py`); no HTML/script contexts exist; filenames
  are slug-sanitized.
- **No dynamic execution:** the codebase contains no `eval`/`exec`/shell
  invocation on any path an LLM output can reach.

## LLM06:2025 Excessive Agency — Compliant

- **No extensions/tools.** The LLM can only return text/JSON; it cannot call
  functions, browse, or trigger actions. All side-effecting operations
  (ingestion) are deterministic code behind RBAC.
- **Minimal functionality per endpoint.** Ingestion endpoints accept only
  files under configured roots; no arbitrary command or path execution
  (`routes_ingest.py`).
- **Least-privilege data access.** The LLM-influenced query path is enforced
  read-only in code, and — when `GREMLIN_READONLY_KEY` is configured — uses a
  Cosmos account-level read-only credential, so writes are impossible even if
  an application guard failed (`graph_gremlin.py`, `config.py`).
- **Human-in-the-loop.** Poisoning/validation warnings stop loads until a
  knowledge manager explicitly overrides after review (LLM04).

## LLM07:2025 System Prompt Leakage — Compliant

- Prompts contain **no secrets, credentials, role structures, or internal
  limits** (`templates.py`) — they are versioned in the repository and safe to
  disclose by design, per OWASP's guidance that prompts must not be treated as
  secrets.
- **Controls are enforced outside the LLM:** authentication/authorization
  (FastAPI dependencies), query safety (regex deny-lists), refusal thresholds
  (reranker), and rate limits are all deterministic code; nothing
  security-relevant depends on the model honouring its instructions.

## LLM08:2025 Vector and Embedding Weaknesses — Mitigated

- **Access control.** The retrieval API sits behind Entra auth; the index is
  reachable only via API-key from the backend (Azure AI Search;
  `vector_azure_search.py`), with metadata scope filters (sector / function /
  technology) applied server-side on every query.
- **Data validation for the corpus.** All content entering the index passes
  the LLM04 screening + review gate; chunks carry provenance metadata and
  content hashes.
- **Retrieval logging.** Every retrieval logs question hash, scope,
  candidate/kept counts, and (source, locator, score) tuples
  (`knowledge_retriever.py`); each audited exchange durably records the
  citations that grounded the answer (`audit_store.py`, Cosmos).
- **Single-tenant partitioning.** One internal corpus; user separation is at
  the session/memory layer (LLM02). Cross-tenant embedding leakage does not
  apply to this deployment shape; if TOM-as-a-service multi-tenancy arrives
  (APIM surface), per-tenant index partitioning becomes a requirement.

**Residual risk:** embedding-inversion attacks require index read access;
mitigation is key custody + network isolation (private endpoints per
`infra/main.bicep`).

## LLM09:2025 Misinformation — Compliant

- **Grounded generation.** Vector answers are synthesized only from retrieved
  passages with inline `[n]` citations; graph answers only from query rows
  (`templates.py`, `synthesis.py`).
- **Refusal over fabrication.** The reranker drops passages under the
  relevance threshold; when nothing survives, the assistant states it has
  insufficient grounding instead of guessing (`reranker.py`,
  `synthesis.vector_answer`); empty graph results produce an honest "not
  found" (`synthesis.graph_answer`).
- **Deterministic low-temperature inference** (`temperature=0.1`,
  `config.py`) and offline fallbacks that never invent content.
- **User-facing risk communication.** Every assistant message is labelled
  "AI-generated · verify before client use" with explanatory tooltip
  (`Message.jsx`); citations with classification are rendered under each
  grounded answer; the route badge exposes confidence.

## LLM10:2025 Unbounded Consumption — Compliant

- **Input bounds.** Question ≤ 4000 chars, session/persona/scope fields all
  length-capped (`schemas.py`).
- **Output bounds.** `llm_max_tokens=1500`; answers truncated to 500 chars in
  the memory window (`memory.py`).
- **Per-principal rate limiting.** `RATE_LIMIT_PER_MINUTE` (default 60) on
  `/chat` and `/export`, enforced via shared cache (Redis-atomic in prod) with
  `429 + Retry-After` (`core/ratelimit.py`, `cache.incr`).
- **Fan-out caps and timeouts.** Multi-hop decomposition capped at
  `MAX_SUB_QUESTIONS=5` (`decomposition.py`); branch pool ≤ 4 workers with
  per-branch timeout (`orchestrator.py`); Cypher self-repair bounded at 2
  retries; generated queries LIMIT ≤ 200.
- **No logprobs/logit exposure.** API responses expose answer text and
  metadata only (`schemas.py`).
- **Infrastructure layer.** Application Gateway WAF (OWASP 3.2 ruleset) and
  container autoscaling per `infra/main.bicep`; Azure Monitor telemetry for
  consumption anomalies (`core/telemetry.py`).

---

## Deferred items (owner-accepted, tracked)

| Item | OWASP ref | Rationale |
| --- | --- | --- |
| Semantic (ML-based) injection classifier in front of ingestion | LLM01/04 | Deterministic screen + human review gate in place; evaluate Azure AI Content Safety Prompt Shields when Workbench exposes it |
| Adversarial red-team exercise | LLM01 #7 | Requires deployed environment + security team engagement; recommended pre-UAT |
| Per-tenant vector partitioning | LLM08 | Applies only if TOM-as-a-service multi-tenant surface ships |
| Output watermarking | LLM10 #8 | Low value for an internal, authenticated tool; revisit for external exposure |
