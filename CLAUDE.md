# CLAUDE.md — Semiconductor RAG QA System

## Project Overview
A Retrieval-Augmented Generation (RAG) question-answering system for semiconductor domain knowledge. Uses local Ollama DeepSeek-R1 for both embeddings and generation.

## Runtime Constraints (CRITICAL)
- **Runtime model**: Local Ollama DeepSeek-R1 (`deepseek-r1:8b`) — NEVER change this
- **No cloud models**: No DeepSeek API, OpenAI, Anthropic, or any cloud LLM at runtime
- **No API keys**: The system runs fully offline after dependency installation
- **Development agents** (Data/Document/RAG/Tool/Workflow/Test/SandboxGuard/GitGuard/Tutor) use `deepseek-v4-flash` for code generation and review only — never for runtime

## Architecture

```
docs/ ──▶ Data Agent ──▶ Document Agent ──▶ RAG Agent ──▶ Workflow Agent ──▶ CLI
         (src/data/)     (src/documents/)    (src/rag/)     (src/workflow/)
                                                 │
                           Tool Agent ◀───────────┘
                           (src/tools/)
```

## Multi-Agent Team
- **Data Agent**: Data models, loaders → `src/data/`
- **Document Agent**: Parsing, chunking, metadata → `src/documents/`
- **RAG Agent**: Embeddings, vector DB, retrieval, generation → `src/rag/`, `src/embeddings/`, `src/vectordb/`
- **Tool Agent**: Semiconductor domain tools → `src/tools/`
- **Workflow Agent**: Pipeline orchestration, CLI → `src/ui/`, `src/workflow/`, `scripts/`
- **Test Agent**: All testing → `tests/`
- **Sandbox Guard Agent**: Security review (read-only + settings)
- **Git Guard Agent**: Git safety review (read-only)
- **Tutor Agent**: Learning materials → `docs/`

## Key Commands
```bash
# Verify Ollama connectivity
python scripts/verify_ollama.py

# Ingest documents into vector store
python scripts/ingest.py --input data/sample_docs/

# Interactive QA
python -m src.ui.cli

# Single question
python -m src.ui.cli --query "What is photolithography?"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing
```

## Environment
- `.env.example` contains all configurable parameters
- Copy to `.env` and adjust as needed
- `OLLAMA_MODEL=deepseek-r1:8b` — do not change runtime model
