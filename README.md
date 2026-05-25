# FabYield Insight

基于本地 Ollama DeepSeek-R1 的半导体制程异常知识问答系统。

## 业务场景

良率/制程工程师面对 SECOM 制程数据时需要：
1. **快速定位** — 哪个 Wafer/Die 的哪个传感器出现异常？
2. **根因分析** — 异常传感器之间的关联关系是什么？
3. **SOP 排查** — 根据 SOP 文档生成排查步骤建议

FabYield Insight 通过 **RAG (检索增强生成)** 将 SECOM 数据分析与 SOP 文档知识结合，用自然语言回答工程问题。

## 架构

```
SECOM 数据 ---> data_ops (DuckDB) ---> workflow (LangGraph) ---> app (CLI)
SOP 文档  ---> docs_pipeline (RAG) ---> llm (DeepSeek-R1)
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env

# 3. 确保 Ollama 运行并拉取模型
ollama serve
ollama pull deepseek-r1:8b

# 4. 验证环境
python scripts/verify_ollama.py

# 5. 摄入文档
python scripts/ingest_docs.py --input docs/sop/

# 6. 启动问答
python -m src.app.cli
```

## 开发

```bash
# 运行测试
pytest tests/ -v

# 编译检查
python -m compileall src
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API 地址 |
| `OLLAMA_MODEL` | `deepseek-r1:8b` | 运行时模型（不可改为云端模型） |
| `APP_ENV` | `dev` | 运行环境 |

## License

MIT
