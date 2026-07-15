# API Reference

Base path: `/api/v1`. In production all endpoints require an Entra ID bearer
token. In dev (`AUTH_DISABLED=true`) the backend returns a local synthetic
principal.

## POST /api/v1/chat

Routes a question to GRAPH, VECTOR, or MULTIHOP.

```json
{
  "question": "List all L2 processes under Finance",
  "session_id": "web-abc123",
  "persona": "professional",
  "sector": "Cross-sector",
  "function": "Finance",
  "technology": "Tech-agnostic"
}
```

The response includes `answer`, `route`, `confidence`, `persona`, `citations`,
`suggested_questions`, optional `process_diagram_svg`, optional `process_flow`,
and `timings_ms`. `sector`, `function`, and `technology` are optional, but should
be supplied by applications that know the user's selected vertical so graph and
vector retrieval can be filtered consistently.

`persona` selects the chat persona from the approved L2 architecture:
`professional` (default — engagement-ready consultant voice) or
`knowledge_manager` (adds provenance and content-gap detail for TOM curators).
Unknown values fall back to `professional`; the resolved persona is echoed in
the response.

## POST /api/v1/export

Renders Markdown plus optional process-flow JSON to `docx`, `pptx`, or `pdf`.

```json
{
  "answer_markdown": "# Record to Report\n\nThe period-end close process...",
  "title": "TOM AI Assistant - Response",
  "fmt": "docx",
  "process_flow": null
}
```

## POST /api/v1/ingest/graph

Role: `knowledge_manager`.

Processes an ARIS/TOM hierarchy file under `INGESTION_RAW_DIR`, emits a graph
artifact under `INGESTION_PROCESSED_DIR`, and optionally loads the configured
graph backend.

```json
{
  "input_path": "finance_tom_sample.csv",
  "flows_path": "finance_flows.json",
  "output_path": "finance_graph.generated.json",
  "sector": "Cross-sector",
  "function": "Finance",
  "technology": "Tech-agnostic",
  "fail_on_warnings": true,
  "load": true
}
```

When `fail_on_warnings` is true, the artifact is still written, but it is not
loaded into the graph if hierarchy validation finds missing parents, level jumps,
duplicates, cycles, or unknown flow references.

## POST /api/v1/ingest/vector

Role: `knowledge_manager`.

Chunks and optionally indexes supporting TOM documents under `INGESTION_RAW_DIR`.
Supported formats: `.txt`, `.md`, pre-segmented `.json`, `.pdf`, `.docx`,
`.pptx`, `.xlsx`, `.xlsm`, and `.csv`.

```json
{
  "input_path": "supporting-docs",
  "output_path": "finance_vectors.generated.json",
  "sector": "Cross-sector",
  "function": "Finance",
  "technology": "Tech-agnostic",
  "classification": "KPMG Confidential",
  "load": true
}
```

## POST /api/v1/ingest/scan

Role: `knowledge_manager`.

Logic App callback. For UAT/prod this forwards bytes to `DEFENDER_SCAN_ENDPOINT`.
Dev uses a small signature check only.

Response:

```json
{ "verdict": "clean", "engine": "defender", "detail": "" }
```

## POST /api/v1/ingest/process

Role: `knowledge_manager`.

Logic App callback after a clean scan. CSV/XLSX files route to graph ingestion;
other supported files route to vector ingestion.

```json
{
  "blobName": "finance_tom_sample.csv",
  "flowsBlobName": "finance_flows.json",
  "sector": "Cross-sector",
  "function": "Finance",
  "technology": "Tech-agnostic"
}
```

## POST /api/v1/ingest/alert

Role: `knowledge_manager`.

Records ingestion security alerts from the Logic App.

## GET /healthz and /readyz

Liveness and readiness endpoints. `/readyz` reports configured backends,
LLM/embedding availability, and whether auth is disabled.
