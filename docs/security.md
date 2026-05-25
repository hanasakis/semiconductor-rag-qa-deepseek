# Security Configuration — Semiconductor RAG QA System

## 1. Permission Mode

本项目使用 Claude Code 的 **`default`** 权限模式。

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `default` | 每个危险操作前弹窗确认 | 本项目 — 涉及 SECOM 制程数据和私密文档 |
| `acceptEdits` | 自动批准文件编辑，Bash 仍需确认 | 纯前端/文档类项目 |
| `bypassPermissions` | 跳过所有权限检查 | CI/CD 自动化（本项目禁止使用） |

## 2. Sandbox 策略

### 当前状态
Windows 11 原生 PowerShell 环境。Claude Code sandbox 功能已启用。
Sandbox 限制：
- **网络白名单**: localhost:11434 (Ollama), pypi.org, files.pythonhosted.org, github.com
- **文件系统**: 仅允许读写白名单目录
- **进程隔离**: `autoAllowBashIfSandboxed` 设为 false，维持人工审批

### Windows 环境降级策略
Windows 原生 sandbox 能力有限。推荐替代方案：

1. **WSL2 + Ubuntu**（推荐）
   - 提供真正的 Linux 命名空间隔离
   - `docker` 和 `podman` 完整支持
   - Ollama 可在 WSL2 中运行或通过 localhost 访问 Windows 宿主机

2. **Dev Container** (VS Code)
   - `.devcontainer/devcontainer.json` 定义隔离环境
   - 限制挂载卷，只映射 `src/`, `tests/`, `docs/`, `data/sample/`
   - 使用 `ghcr.io` 或内部镜像源

3. **当前 Windows 原生的缓解措施**（在 sandbox 不可用时）
   - `.gitignore` 阻止 `data/raw/`, `data/processed/`, `.env` 提交
   - `settings.json` deny 规则阻止敏感目录读写
   - Git Guard Agent 在每次 commit 前扫描

## 3. 读写边界

### 只读（允许读取但禁止写入）
| 路径 | 原因 |
|------|------|
| `data/raw/**` | SECOM 原始制程数据，不可篡改 |
| `data/processed/**` | 处理后数据，由 Data Agent 单独管理 |
| `data/runtime/**` | 运行时生成，不可手动修改 |
| `.env` | 含本地密钥/配置，禁止查看 |
| `.env.*` | 所有环境变量备份 |

### 读写（允许）
| 路径 | 用途 |
|------|------|
| `src/**` | 业务代码 |
| `tests/**` | 测试代码 |
| `docs/**` | 文档、SOP、学习笔记 |
| `data/sample/**` | 公开样例数据（可提交到 git） |
| `data/eval/**` | 评估数据集 |
| `.claude/**` | Agent 定义和配置 |

### 禁止写入 + 禁止读取
| 路径 | 原因 |
|------|------|
| `models/**` | 本地模型文件（Ollama 管理） |
| `vector_store/**` | 向量索引（由 ChromaDB 管理） |
| `chroma_db/**` | ChromaDB 持久化 |
| `chroma/**` | ChromaDB 持久化 |

## 4. 网络安全

| 目标 | 策略 | 原因 |
|------|------|------|
| `localhost:11434` | 允许 | Ollama API |
| `pypi.org` | 允许 | Python 包下载 |
| `github.com` | 允许 | Git push/pull |
| 其他所有外网 | 禁止 | 防止数据泄露 |
| `curl`, `wget`, `Invoke-WebRequest` | 完全禁止 | 防止绕过网络策略 |

## 5. 高危险操作（必须手动审批）

- `git commit` / `git push` — 防止误提交敏感数据
- `pip install` — 防止供应链攻击
- `docker *` — 防止容器逃逸
- `ollama pull` / `ollama run` — 防止未授权模型下载

## 6. 禁止操作（完全拒绝）

- `git reset --hard` — 不可逆数据丢失
- `git clean` — 不可逆删除未跟踪文件
- `rm -rf` — 不可逆批量删除
- `curl` / `wget` — 防止数据外泄

## 7. Agent 角色与安全

| Agent | 安全职责 |
|-------|---------|
| **Sandbox Guard Agent** | 每阶段开始前审查权限边界；每阶段结束后扫描敏感文件 |
| **Git Guard Agent** | commit 前审查 diff、测试结果、commit message；检查 .env/data 不被暂存 |
| **Data Agent** | 禁止提交 `data/raw/` 和 `data/processed/` |
| 所有 Agent | 严禁引入云端 API key；运行时仅使用本地 Ollama |

## 8. settings.local.json 使用方式

`settings.local.json` 用于本地开发者的个人偏好，**不提交到 git**：

```json
{
  "permissions": {
    "allow": [
      // 个人常用的只读命令，缩短审批流程
      // 例如: "Bash(ollama list)"
    ]
  }
}
```

规则优先级：`deny` > `ask` > `allow`
- `settings.json` (项目级) 和 `settings.local.json` (本地) 合并
- `deny` 始终生效，无论本地配置如何
- `settings.local.json` 只能收紧权限，不能放松项目级限制

## 9. 为什么半导体项目更要严格隔离

1. **制程数据商业价值极高** — SECOM 数据含良率、缺陷密度、工艺窗口，泄露可推断整条产线能力
2. **SOP 文档含工艺 know-how** — 异常排查步骤是多年经验的沉淀
3. **原始数据不可篡改** — `data/raw` 是唯一真实来源 (source of truth)，任何修改都会导致分析偏差
4. **合规要求** — 半导体行业通常受 ITAR/EAR 或客户 NDA 约束
