# Document Processing Pipeline — Design Rationale

## Why Structured Document Conversion

Semiconductor SOP documents are not generic prose. They contain structured
information that must be preserved through the ingestion pipeline:

| Element | Why It Matters | Example |
|---------|---------------|---------|
| **Tables** | Process parameter tables must not be split across chunks | "Step 3: Pressure 5±0.5 mTorr" — if the table header is in chunk A and the value in chunk B, retrieval fails |
| **Sections** | Engineers navigate by section number | "Per SOP-CAL-007 Section 3.2..." — section metadata enables precise retrieval |
| **Pages** | Page numbers are cross-references in other SOPs | "See page 12 for calibration setup" — page metadata enables citation |
| **Warnings** | Safety-critical content must be surfaced first | "CAUTION: Chamber must be vented before sensor removal" — warning type gets retrieval boost |
| **Content Type** | Different queries need different content types | A "how do I fix this?" query needs procedures, not report templates |

## Architecture: Ingest-Time vs Query-Time

### Why Doc Parsing Happens at Ingest Time, Not Query Time

```
┌──────────────────────────────────────────────────────────┐
│  INGEST (once per document)           QUERY (per user)   │
│                                                          │
│  PDF → Docling → DocumentElement[]    "Sensor_42 +3σ?"   │
│         │                                    │            │
│         │ section/page/type metadata         │            │
│         ▼                                    ▼            │
│  ┌───────────┐                        ┌────────────┐     │
│  │  ChromaDB │  ◀──── vector search ── │  Retriever │     │
│  └───────────┘                        └────────────┘     │
│                                                          │
│  Heavy work done ONCE                  Light work per Q  │
└──────────────────────────────────────────────────────────┘
```

If we parsed documents at query time:
- Every query would re-parse every PDF (unacceptable latency)
- Table extraction, section parsing repeated unnecessarily
- No way to do metadata-filtered search without pre-indexed metadata

By parsing at ingest time:
- Each document is parsed once, stored with full metadata
- Queries can filter by section, content_type, page
- Latency is only retrieval + generation, not parsing

## Docling vs Traditional PDF Parsers

Traditional PDF parsers (pypdf, pdfminer) extract text streams with no
understanding of document structure:

| Capability | pypdf | Docling |
|-----------|-------|---------|
| Text extraction | ✓ | ✓ |
| Reading order | ✗ (depends on PDF internals) | ✓ (layout-aware) |
| Table detection | ✗ | ✓ |
| Heading hierarchy | ✗ | ✓ |
| Figure/table separation | ✗ | ✓ |
| Multi-column layout | ✗ | ✓ |

For a semiconductor SOP PDF with:
- Two-column layout (procedure on left, notes on right)
- Multiple parameter tables
- Embedded equipment diagrams

...pypdf might merge columns into gibberish, lose table structure entirely,
and scatter figure captions. Docling produces structured output preserving
all of these.

## The Fallback Chain

```
Path → Docling → PyMuPDF4LLM → pypdf → error
         ↓           ↓            ↓
    (best)      (good)       (basic)
```

- **Docling**: Full structure. Use when available (pip install docling).
- **PyMuPDF4LLM**: Good text extraction with LLM-friendly markdown output.
  Use when Docling not available.
- **pypdf**: Basic text per page. Always works. Last resort.
- **Markdown**: Direct read → section split by `##` → paragraph split.

## Content Type Inference

For Markdown documents, content type is inferred from heading text and body
patterns (heuristic, not ML):

```python
"WARNING: Do not..."          → content_type = "warning"
"| Step | Pressure | ..."     → content_type = "parameter_table"
"Step 1 — Confirm Signal..."  → content_type = "procedure"
"BKM: When RF power..."       → content_type = "bkm"
"## 2. Report Structure"      → content_type = "report_template"
```

For PDF documents processed through Docling, richer structure metadata
(if available) would replace these heuristics.

## DocumentElement Schema

Every chunk in the pipeline carries these metadata fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | str | Always | The actual content |
| `source` | str | Always | Source filename |
| `section` | str | Always | Section heading |
| `page` | int | Always | Page number (0 for MD) |
| `content_type` | str | Always | One of: procedure, parameter_table, warning, bkm, glossary, report_template, general |
| `element_id` | str | Always | SHA256 hash of source+section+text[:200] |

These fields are mandatory per the Document Agent specification:
"必须保留 source、section、page、content_type metadata"
