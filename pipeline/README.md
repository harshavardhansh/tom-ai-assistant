# Ingestion Pipeline

Curated TOM source material is split into the two stores the assistant queries:

- Graph: process hierarchy L0-L4, roles, controls, policies, and process-flow JSON.
- Vector index: supporting narratives, policies, decks, documents, and other reference material.

The Logic App template models the enterprise flow:

1. Pull approved TOM assets from SharePoint / Global One Platform.
2. Scan each asset with the enterprise Defender malware gate.
3. Land clean files in Blob raw storage or quarantine infected files.
4. Call the backend ingestion callbacks to process graph/vector assets.

## Graph Ingestion

Input: ARIS/TOM hierarchy export as CSV/XLSX with:

```text
code,name,level,parent_code,roles,controls
```

Roles and controls are semicolon-separated. Process flows are supplied as a JSON
sidecar keyed by L1 process code.

```bash
python excel_to_graph.py \
  --input sample_data/finance_tom_sample.csv \
  --flows sample_data/finance_flows.json \
  --output sample_data/finance_graph.generated.json \
  --sector Cross-sector \
  --function Finance \
  --technology Tech-agnostic
```

Add `--load` to upsert into the configured graph backend. Neo4j and Gremlin
loaders now create typed labels and typed relationships matching the query
schema (`HAS_SUB_PROCESS`, `PERFORMED_BY`, `HAS_CONTROL`, `GOVERNED_BY`).
Every generated node carries `sector`, `function`, and `technology` metadata;
generated role/control codes include a stable metadata-aware hash to avoid
collisions when additional functions are loaded.

## Vector Ingestion

Supported formats: `.txt`, `.md`, pre-segmented `.json`, `.pdf`, `.docx`,
`.pptx`, `.xlsx`, `.xlsm`, and `.csv`.

```bash
python document_to_vector.py \
  --input ./docs_in \
  --output sample_data/finance_vectors.generated.json \
  --sector Cross-sector \
  --function Finance \
  --technology Tech-agnostic
```

Add `--load` to embed through the Workbench embedding deployment and upsert into
the configured vector backend. Locators preserve page, slide, sheet, or chunk
context for citations. Chunk IDs are deterministic content hashes and chunks
carry `sector`, `function`, `technology`, and `classification` fields so Azure AI
Search can filter retrieval to the selected vertical.

## Data-Storage Rule

Process hierarchy is stored only in the graph. Supporting documents are stored
only in the vector index. Do not duplicate the same source into both stores
unless it has been explicitly split into structured hierarchy and narrative
supporting content.

Before loading a graph artifact, the ingestion API blocks promotion when
hierarchy validation warnings exist unless `fail_on_warnings=false` is supplied
deliberately for a non-live diagnostic run.
