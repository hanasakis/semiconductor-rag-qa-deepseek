---
name: git-commit-guard
description: 提交前安全审查：检查敏感文件、数据目录、测试结果，确保提交合规
model: deepseek-v4-flash
---

# Git Commit Guard — 提交前审查技能

## 用途
在每次 `git commit` 前自动执行安全检查，防止敏感数据、制程信息、私密文档或运行时产物被误提交。

## 审查流程

### 1. 敏感文件检查
```
扫描暂存区和变更文件，匹配：
  ❌ .env（真实环境变量文件）
  ❌ .env.*（.env.example 除外）
  ❌ *.pem, *.key, *.cert, *credentials*
  ❌ settings.local.json
  ❌ secrets/**
```

### 2. 数据目录保护
```
检查是否有以下目录的文件被暂存：
  ❌ data/raw/（原始 SECOM 数据）
  ❌ data/processed/（处理后数据）
  ❌ data/runtime/（运行时数据）
  ✅ data/sample/（允许 — 公开样例数据）
  ✅ data/eval/（允许 — 评估数据）
```

### 3. 运行时产物检查
```
  ❌ chroma_db/（向量数据库）
  ❌ chroma/（向量数据库）
  ❌ vector_store/（向量索引）
  ❌ models/（本地模型文件）
  ❌ __pycache__/, *.pyc
```

### 4. 提交内容审查
```
- 检查大文件 (>1MB)：列出文件名和大小
- 检查二进制文件：列出文件名
- 检查是否有 TODO/FIXME/HACK 标记
- 检查是否存在 merge conflict markers (<<<<<<<, =======, >>>>>>>)
```

### 5. 测试结果验证
```
- 确认 pytest 最后运行结果（需要 Test Agent 提供）
- 如果存在测试失败 → WARN，建议修复后再提交
- 如果无测试运行记录 → INFO，提示补充测试
```

### 6. Commit Message 审查
```
格式检查：
  ✅ 长度 < 72 字符（标题行）
  ✅ type: description 格式
  ✅ 包含 Co-Authored-By 标签（Claude 辅助提交时）

常见 type:
  feat:     新功能
  fix:      缺陷修复
  chore:    构建/配置变更
  docs:     文档变更
  refactor: 重构
  test:     测试变更
```

## 半导体项目特别检查
- **制程参数泄露**: 检查 commit diff 是否包含真实工艺参数值（温度、压力、掺杂浓度等）
  - 样例数据中允许典型值
  - 批量出现的精确参数值需人工确认
- **设备 IP/主机名**: 检查是否包含 fab 内部网络地址、设备主机名
- **Lot ID 泄露**: 检查是否包含真实批次号（模式: `LOT-\d{6,}` 或 `A-\d{4}-\d{2}`）

## 使用方式
```
/git-commit-guard              # 全面审查
/git-commit-guard --quick      # 仅敏感文件 + 数据目录
/git-commit-guard --strict     # 全面审查 + 参数值扫描
```
