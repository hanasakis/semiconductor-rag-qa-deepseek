# CLAUDE.md — FabYield Insight

## Project Overview

**FabYield Insight** — 基于本地 Ollama DeepSeek-R1 的半导体制程异常知识问答系统。

良率/制程工程师通过自然语言提问，系统基于 SECOM 制程数据定位失败样本、分析异常传感器，并结合 SOP 文档 (RAG) 生成排查建议。

## Runtime Constraints (CRITICAL)

- **Runtime model**: 本地 Ollama DeepSeek-R1 (`deepseek-r1:8b`) — 绝不更改
- **No cloud models**: 无 DeepSeek API、OpenAI、Anthropic 或任何云端 LLM
- **No API keys**: 依赖安装后完全离线运行
- **Dev agents**: deepseek-v4-flash (仅代码生成/审查，非运行时)

## Architecture

```
SECOM 数据 ──▶ data_ops ──▶ workflow ──▶ app (LangGraph)
               (DuckDB)      (路由编排)     (CLI/UI)

SOP 文档 ────▶ docs_pipeline ──▶ llm (Ollama DeepSeek-R1)
               (Docling/chunk/FTS)  (prompt/生成/清洗)
```

### 模块职责

| 模块 | 目录 | 职责 |
|------|------|------|
| **app** | `src/app/` | LangGraph 入口、CLI 交互界面 |
| **llm** | `src/llm/` | Ollama DeepSeek-R1 调用、prompt 模板、输出清洗 |
| **data_ops** | `src/data_ops/` | SECOM 数据加载、DuckDB 查询、异常分析、缺失值分析 |
| **docs_pipeline** | `src/docs_pipeline/` | Docling/PyMuPDF4LLM 文档转换、chunk、嵌入、FTS 检索 |
| **workflow** | `src/workflow/` | LangGraph 路由、样本分析、报告生成、答案校验 |
| **eval** | `src/eval/` | 检索评估、答案评估、工作流评估 |

### 子 Agent 团队

| Agent | 负责模块 | 模型 |
|-------|---------|------|
| Data Agent | `src/data_ops/` | deepseek-v4-flash |
| Document Agent | `src/docs_pipeline/` | deepseek-v4-flash |
| RAG Agent | `src/llm/` | deepseek-v4-flash |
| Tool Agent | `src/data_ops/` (工具函数) | deepseek-v4-flash |
| Workflow Agent | `src/app/`, `src/workflow/` | deepseek-v4-flash |
| Test Agent | `tests/` | deepseek-v4-flash |
| Sandbox Guard Agent | 安全审查 (只读) | deepseek-v4-flash |
| Git Guard Agent | Git 审查 (只读) | deepseek-v4-flash |
| Tutor Agent | `docs/` (学习笔记) | deepseek-v4-flash |

## Key Commands

```bash
# Verify Ollama connectivity
python scripts/verify_ollama.py

# Ingest SECOM data into DuckDB
python scripts/ingest_secom.py --input data/sample/

# Ingest SOP documents into vector store
python scripts/ingest_docs.py --input docs/sop/

# Interactive QA
python -m src.app.cli

# Single question
python -m src.app.cli --query "Wafer 14 的 V1 传感器为什么异常？"

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing
```

## Environment

- `.env.example` 包含所有可配置参数
- 复制为 `.env` 后调整
- `OLLAMA_MODEL=deepseek-r1:8b` — 不可更改
