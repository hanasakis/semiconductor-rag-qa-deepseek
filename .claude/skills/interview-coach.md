---
name: interview-coach
description: 面试表达训练与学习复盘：半导体 RAG 系统设计、架构决策、故障排查场景
model: deepseek-v4-flash
---

# Interview Coach — 半导体 RAG 项目面试表达与学习复盘

## 用途
基于 FabYield Insight 项目的实际开发经验，生成面试问答和表达训练材料。覆盖 RAG 架构、半导体领域、系统工程三个维度。

## 工作流程

### 1. 学习复盘
每次功能模块完成后调用，从 git log 提取变更内容，生成：
- 本次学到了什么（3 点）
- 遇到了什么坑（1-2 点）
- 下次可以怎么优化（1 点）

### 2. 面试问答生成
按三个层级生成：

#### L1 — 基础 (What/How)
适合：SDE 实习/初级岗位
```
Q: 请介绍一下 FabYield Insight 项目的整体架构。
A: (基于实际 src/ 结构回答)

Q: 为什么选择 ChromaDB 而不是 Pinecone/Weaviate？
A: (本地离线优先、无 API 依赖、与 Ollama 生态一致)

Q: RAG 中 chunk size 和 overlap 怎么选择？
A: (半导体文档的特殊性：参数表完整、制程步骤边界)
```

#### L2 — 进阶 (Why)
适合：SDE 中级/高级岗位
```
Q: 为什么半导体 RAG 需要同时做向量检索和 FTS 全文检索？
A: (术语精确匹配 vs 语义理解，举例：RTA 缩写展开)

Q: DuckDB 在 SECOM 数据分析中相比 Pandas 的优势是什么？
A: (列式存储、SQL 接口、OLAP 优化、内存效率)

Q: 如何评估 RAG 系统的检索质量？
A: (recall@k, MRR, NDCG，半导体领域测试集构建)
```

#### L3 — 系统设计 (Trade-off)
适合：Senior/Staff/System Design 面试
```
Q: 设计一个半导体良率异常实时告警 + 知识问答系统。
A: (流处理 + RAG 架构、延迟窗口、SOP 自动匹配、人机协作)

Q: DeepSeek-R1 的 think 标签如何处理？
A: (推理链提取、答案解析、token 开销优化)

Q: 如果 SECOM 数据量从 10GB 增长到 10TB，架构如何演进？
A: (分区策略、增量索引、向量库扩展、混合存储)
```

### 3. 表达训练
- **STAR 法则拆解**: 每个核心模块生成 Situation → Task → Action → Result 描述
- **一分钟电梯演讲**: 用 60 秒讲清 FabYield Insight 解决什么问题
- **技术难点叙述**: 3 个最值得在面试中展开的技术亮点

### 4. 复盘模板
```markdown
## 模块: {module_name} | 日期: {date} | Commit: {hash}

### 学到了什么
1. {关键收获 1}
2. {关键收获 2}
3. {关键收获 3}

### 遇到什么坑
1. {踩坑描述 + 解决方案}
2. {踩坑描述 + 解决方案}

### 下次优化
- {改进点}

### 面试问题 (本周)
- {问题 1}
- {问题 2}
- {问题 3}
```

## 半导体领域常见面试主题
- 半导体制造流程: 晶圆 → 光刻 → 蚀刻 → 沉积 → CMP → 测试 → 封装
- 良率模型: Murphy / Poisson / Bose-Einstein / 负二项分布
- SECOM 数据集: 1567 样本、591 传感器、半导体蚀刻工艺
- 制程异常分类: 设备故障、工艺偏移、环境扰动、操作失误
- 关键术语: RTA, CVD, PVD, CMP, RIE, ALD, Lithography, Die/Wafer/Lot

## 使用方式
```
/interview-coach --module src/data_ops       # 模块复盘
/interview-coach --level l3                   # 系统设计面试题
/interview-coach --format star --module all   # STAR 法则叙述
/interview-coach --review                     # 全部学习复盘
```
