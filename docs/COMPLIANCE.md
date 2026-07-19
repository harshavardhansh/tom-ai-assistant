# Compliance And Security

Classification: KPMG Confidential - Internal Use Only

This document maps the TOM AI Knowledge Assistant controls to KPMG-style
enterprise expectations. Final approval remains with Risk, Security, and the
environment owner.

For the AI/LLM-specific threat model, see `docs/OWASP_LLM_COMPLIANCE.md`,
which maps every control to the OWASP Top 10 for LLM Applications (2025)
with per-item implementation evidence.

## Data Handling

- Every retrieved chunk and exported asset carries a classification, defaulting
  to `KPMG Confidential`.
- Process hierarchy is stored only in the graph database.
- Supporting narrative documents are stored only in the vector index.
- Entitlement filtering for consumer APIs is an API/product policy requirement
  for the APIM TOM-as-a-service surface.

## Identity And Access

- The SPA uses Microsoft Entra ID via MSAL.
- The backend validates bearer tokens against tenant JWKS, issuer, and audience.
- `AUTH_DISABLED=true` is allowed only for dev/test. UAT/prod startup fails if
  auth is disabled or Entra settings are missing.
- Admin ingestion routes require the `knowledge_manager` app role.
- Service-to-service access uses managed identity where Azure supports it; data
  plane keys are resolved from Key Vault when required by the SDK/service.

## Secrets

- Secrets are not committed.
- Key Vault is RBAC-enabled, soft-delete and purge-protection enabled, and public
  network access disabled.
- Required secrets: Workbench API key, Search key, Gremlin key, Cosmos memory
  key, and Redis URL.

## Network Isolation

- Core data services are provisioned with public network access disabled.
- `infra/main.bicep` declares VNet integration, private endpoints, and Private
  DNS for Key Vault, Blob, Azure AI Search, Cosmos Gremlin, Cosmos NoSQL memory,
  and Redis.
- The Container Apps environment is internal. External routing/front door and
  final DNS are tenant-specific handoff items.

## Responsible AI

- Vector answers are constrained to retrieved context.
- Relevance thresholding forces refusal when no passage is strong enough.
- Graph query generation is read-only guarded and blocks write/admin clauses.
- Retrieved content is treated as data, not instructions.
- Workbench/Azure content safety and PII redaction should be enabled as part of
  E8 security sign-off.

## Audit And Retention

- `core/telemetry.py` emits traces/metrics to Application Insights and Log
  Analytics.
- `clients/audit_store.py` writes durable Q&A audit records to Cosmos DB when
  configured.
- Redis/in-memory prompt memory stores only the rolling last-N Q&A window with a
  short TTL.
- Cosmos audit retention is controlled by the container TTL in IaC; final
  retention and right-to-erasure procedures require KPMG approval.

## OWASP LLM Top 10 Mapping

| Risk | Control |
|---|---|
| Prompt injection | Retrieved text treated as data; graph write denylist |
| Insecure output handling | Structured API output; server-generated export files |
| Training-data poisoning | Curated Knowledge-Manager ingestion flow |
| Model denial of service | APIM quotas, branch timeouts, cache layer |
| Supply chain | Pinned dependencies; CI scans still required |
| Sensitive disclosure | Classification, RBAC, entitlement policy |
| Insecure plugin design | No arbitrary tool execution |
| Excessive agency | Model path is read-only |
| Overreliance | Citations, route badge, confidence, refusal behavior |
| Model theft | Workbench-fronted models; no model artifacts in repo |

## Secure SDLC

Branch policies, SAST, dependency scan, secret scan, RAG eval gates, and
pre-go-live penetration testing are required before production release.
