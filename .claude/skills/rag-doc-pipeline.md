---
name: rag-doc-pipeline
description: 制程 SOP/技术文档的 RAG 文档管线：Docling 转换、智能分块、元数据提取、FTS + 向量混合检索
model: deepseek-v4-flash
---

# RAG Doc Pipeline — 半导体文档 RAG 管线

## 用途
将半导体制造 SOP 文档、设备手册、工艺规范转换为可检索的知识库，支持混合检索（FTS + 向量）。

## 工作流程

### 1. 文档转换 (Docling/PyMuPDF4LLM)
```
输入: .pdf / .docx / .md / .txt
  → Docling 解析为结构化 Document 对象
  → 提取: 标题层级、表格、图片引用、页眉页脚
  → PyMuPDF4LLM 作为 PDF 备选方案（处理扫描件/老旧文档）
```

**半导体文档特殊处理**:
- 识别制程步骤编号 (Step 1 → Step N, 或 OP-001 → OP-099)
- 保留温度/压力/功率参数表（标记为 TABLE 类型 block）
- 设备型号识别 (如 "AMAT Endura", "LAM Research 2300")
- BKM (Best Known Method) 标记为高权重段落

### 2. 智能分块
```
策略: 按 section 边界 + 语义完整性分块
chunk_size: 1000 tokens (可配置)
chunk_overlap: 200 tokens (可配置)

优先级:
  1. Section 标题边界（不截断章节）
  2. 制程步骤边界（Step 边界不截断）
  3. 表格完整性（单个表格不分块）
  4. Token 限制兜底
```

### 3. 元数据提取（必须保留）
每个 chunk 必须包含：
```yaml
source: "SOP-ETCH-042.pdf"
section: "3.2 腔体压力异常排查"
page: 12
content_type: "procedure" | "parameter_table" | "bkm" | "warning" | "glossary"
equipment: "Etch Chamber A"
process_step: "Step 5 - Pressure Stabilization"
doc_version: "v2.1"
last_updated: "2024-03-15"
```

### 4. 混合检索
- **向量检索** (ChromaDB): 语义相似度，用于开放式问题
- **FTS 检索** (SQLite FTS5): 关键词精确匹配，用于术语/编号查询
- **融合策略**: `score = 0.7 * vector_score + 0.3 * fts_score`
- **重排序**: 按 source 去重 → 按 section 聚合 → 保留 top_k

### 5. 输出产物
- `chroma_db/` — ChromaDB 向量索引
- `docs_pipeline/fts_index.db` — FTS5 全文索引
- `docs_pipeline/chunk_manifest.yaml` — 分块清单

## 半导体特定规则
- **安全警告优先**: content_type=warning 的 chunk 在检索时加权 1.5x
- **参数表完整性**: 包含参数表的 chunk 不允许被截断
- **版本追踪**: 同一 SOP 的多版本共存时，默认检索最新版本
- **术语词典联动**: 检索时自动展开术语缩写 (如 "RTA" → "Rapid Thermal Anneal")

## 使用方式
```
/rag-doc-pipeline --input docs/sop/ --mode ingest
/rag-doc-pipeline --input docs/sop/SOP-CVD-001.pdf --mode single
/rag-doc-pipeline --query "etch chamber pressure deviation" --mode search
```
