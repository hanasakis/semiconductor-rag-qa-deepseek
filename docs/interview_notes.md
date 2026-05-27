# FabYield Insight — Interview Preparation Notes

## Elevator Pitch (60 seconds)

"FabYield Insight is a local, offline semiconductor yield analysis and
knowledge QA system. It combines anomaly detection on SECOM process data
with RAG-based SOP retrieval, all powered by DeepSeek-R1 running on
Ollama. No cloud APIs, no vector embedding model downloads — just
statistical analysis, FTS5 full-text search, and an LLM that understands
semiconductor manufacturing."

## Key Technical Highlights

### 1. Architecture Decision: FTS5 > Vector Embeddings

**Why**: Semiconductor SOPs are highly structured (numbered sections, precise
terminology, dense parameter tables). FTS5 with BM25 ranking handles this
better than semantic embeddings because engineers search with exact terms
("lockout/tagout", "SOP-CAL-007", "sensor calibration").

**Trade-off**: FTS5 can't handle synonyms well, but semiconductor terminology
is standardized enough that this matters less than in general-domain search.

### 2. Answer Guard: Safety for Manufacturing

Four rule-based checks run on every generated answer:
- No claiming physical identity of anonymized sensors
- Cite specific data values when data tools were used
- Reference SOP documents by name
- Include uncertainty/limitation statement

**Why this matters**: In manufacturing, a wrong answer costs money. If the
system says "Sensor_42 is the chamber pressure sensor" when it's actually
an RF power sensor, an engineer might recalibrate the wrong equipment.

### 3. LangGraph Orchestration

The graph routes questions to one of four handlers based on question type:
concept_qa, sample_analysis, cohort_analysis, report_generation.

**Why this matters**: Not every question needs to compute z-scores for 591
sensors. The router saves computation by only running the tools that are
relevant to each query type.

### 4. Data + Document Evidence Separation

Data evidence (z-scores, missingness) is collected independently from
document evidence (SOP retrieval). They're combined only at the LLM
generation step.

**Why this matters**: The LLM can cite both types of evidence separately.
An auditor can verify: was the z-score really +4.5? Does SOP-CAL-007
really say to check RF power? This traceability is essential for
manufacturing QA systems.

## Common Interview Questions

### L1 — Basic Understanding

**Q: What problem does FabYield Insight solve?**

A: Semiconductor yield engineers need to investigate why certain wafers fail.
They have SECOM sensor data (591 anonymized features) and SOP documents.
FabYield Insight automates the investigation: compute anomaly scores, find
relevant SOP procedures, and generate a structured report with cited evidence.

**Q: Why use local Ollama instead of a cloud API?**

A: Semiconductor fabs have strict data security requirements. Process data
and yield information cannot leave the fab network. Local Ollama ensures
all computation stays on-premises.

**Q: What is the data flow from question to answer?**

A: Question → Router (classify intent) → Handler (collect evidence) →
Evidence Assembly (data + SOPs) → DeepSeek-R1 Generation → Answer Guard
(validate) → Final Response.

### L2 — Architecture Decisions

**Q: Why separate the router from the handlers?**

A: The router is a single-purpose classifier that extracts structured
parameters (question_type, sample_id, feature_ids). Handlers are
purpose-built workflows. This separation means:
- The router can be swapped for a faster/smaller model without touching handlers.
- Each handler can be tested independently.
- New question types can be added without modifying existing handlers.

**Q: How do you handle the case where DeepSeek-R1 outputs malformed JSON?**

A: Three-tier repair pipeline:
1. Direct `json.loads()` — works for clean output.
2. Extract from markdown code fences — handles LLM formatting habits.
3. Repair common errors: trailing commas, unquoted keys, single quotes,
   Python True/False/None → JSON true/false/null.

If all three fail, raise a ValueError that the caller handles gracefully.

**Q: How would you scale this to 10TB of SECOM data?**

A: Three changes:
1. DuckDB → partitioned Parquet files with predicate pushdown.
2. FTS5 → add incremental indexing per document batch.
3. DeepSeek-R1 → consider a smaller student model for routing/reranking
   to reduce LLM call frequency on large datasets.

### L3 — System Design

**Q: Design a real-time yield monitoring version of this system.**

A:
- Stream SECOM data into a time-series database (InfluxDB/TimescaleDB).
- Maintain a sliding window of baseline statistics (30-day rolling mean/std).
- Trigger anomaly detection when a new sample's z-score exceeds threshold.
- Automatically retrieve relevant SOPs for the anomalous sensor group.
- Push a notification with pre-computed analysis to the engineer's dashboard.
- The engineer can then ask follow-up questions via the existing QA interface.

**Q: How do you evaluate whether the system's answers are correct?**

A: Five metrics:
1. Routing accuracy — is the right handler invoked?
2. Sample analysis success rate — does it produce valid structured output?
3. SOP source hit rate — does retrieval find relevant documents?
4. Unsupported claim rate — does it falsely claim to know sensor identities?
5. Refusal correctness — does it say "I don't know" when it should?

Note: "Fluency" is NOT a primary metric. A fluent but factually wrong answer
is worse than a slightly awkward but carefully qualified answer that cites
specific z-scores and SOP sections.

### Q: What was the hardest technical challenge?

The FTS5 integration. SQLite FTS5 has a column-filter query syntax that
interprets certain patterns (like `z-score`) as column references, causing
`no such column: score` errors. The fix required understanding FTS5's query
parser internals and implementing a query escaping layer that wraps
hyphenated terms in double quotes while preserving search semantics.

## STAR Narratives

### Situation: Semiconductor RAG System Architecture

**S**: A semiconductor yield engineering team needs a system that can analyze
SECOM process data and retrieve relevant SOP procedures — without sending
proprietary fab data to cloud APIs.

**T**: Build an offline RAG QA system that combines statistical anomaly
detection with document retrieval, using only local models.

**A**:
- Designed a modular architecture with 6 code modules and 9 specialized
  development agents.
- Chose FTS5 over vector embeddings for keyword-precise SOP search.
- Implemented a LangGraph workflow with conditional routing for 4 question types.
- Built an answer guard with rule-based checks for sensor anonymization compliance.
- Created 35 evaluation questions covering 5 types × 3 difficulty levels.

**R**: 185 tests passing, zero cloud dependencies, 5 measurable evaluation
metrics, Streamlit workbench for interactive demonstration.

### Situation: Anonymous Feature Handling

**S**: SECOM's 591 features are anonymized. The LLM tends to hallucinate
physical identities for sensor readings.

**T**: Prevent the system from making unsupported claims about sensor identity
while still providing useful statistical analysis.

**A**:
- Implemented `_claims_sensor_identity()` with regex patterns detecting
  "Sensor_N is the X sensor" type claims.
- Added guard rules that flag these claims and append disclaimers.
- Designed prompts that instruct the model to say "Sensor_42 shows elevated
  readings statistically associated with RF power anomalies in SOP-CAL-007"
  rather than "Sensor_42 is the RF power sensor."

**R**: Answer guard catches identity claims with regex patterns. All answers
include uncertainty statements about sensor anonymization.

## Semiconductor Domain Knowledge

### Key Manufacturing Process Flow

```
Wafer → Lithography → Etch → Deposition → CMP → Implant → Test → Package
```

### Common Failure Modes

| Process | Failure Mode | Typical Signature |
|---------|-------------|-------------------|
| Lithography | Misalignment, defocus | Stripe pattern on wafer map |
| Etch | Undercut, over-etch | Edge ring defects |
| CMP | Dishing, erosion | Center-heavy thickness variation |
| Deposition | Particles, non-uniformity | Random scatter defects |
| Implant | Channeling, dose error | Electrical test deviation |

### Key Metrics

| Metric | Formula | Use |
|--------|---------|-----|
| Yield | Good die / Total die | Overall fab health |
| z-score | (x - μ) / σ | Per-sample anomaly detection |
| Cohen's d | (μ₁ - μ₂) / σ_pooled | Feature discriminability |
| Missing rate | NaN count / Total samples | Sensor reliability |

### Important Terminology

- **SECOM**: SEmiconductor COnstruction/Manufacturing dataset
- **RTA**: Rapid Thermal Anneal
- **CVD**: Chemical Vapor Deposition
- **PVD**: Physical Vapor Deposition
- **CMP**: Chemical Mechanical Planarization
- **RIE**: Reactive Ion Etching
- **ALD**: Atomic Layer Deposition
- **BKM**: Best Known Method
- **SPC**: Statistical Process Control
- **PM**: Preventive Maintenance
- **MFC**: Mass Flow Controller
- **OES**: Optical Emission Spectroscopy
