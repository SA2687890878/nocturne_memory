# Nocturne Memory 项目文档中心

## 概述
Nocturne Memory 是通过 MCP 为 AI Agent 提供长期记忆读写能力的服务，包含 FastAPI 后端、React 管理界面和 SQLite/PostgreSQL 持久化。

## 快速开始

Windows 本地开发环境需要 Python、Node.js/npm，并安装前后端依赖：

```powershell
python -m pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
.\start-local-dev.bat
```

启动脚本默认将后端绑定到 `127.0.0.1:8233`、前端绑定到 `127.0.0.1:3000`。它会先尝试停止占用这两个端口的旧进程，运行前请确认端口上的进程可停止。

测试命令：

```powershell
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
python -m pytest
cd ..\frontend
npm run test:run
npm run build
```

## 项目结构

| 路径 | 用途 |
|---|---|
| `backend/main.py` | REST API 与 Dashboard 的 Web 入口 |
| `backend/mcp_server.py` | MCP stdio 入口 |
| `backend/run_sse.py` | MCP HTTP、REST 与 Dashboard 组合入口 |
| `backend/web_app.py` | 共享 Web 应用、路由和中间件组装 |
| `backend/api/` | FastAPI REST 路由 |
| `backend/db/` | SQLAlchemy 模型、数据库连接、图操作与搜索 |
| `backend/db/migrations/` | 数据库结构迁移 |
| `backend/tests/` | 后端 API、服务、MCP 与单元测试 |
| `frontend/src/features/` | React 按功能划分的管理界面 |
| `frontend/src/lib/api.js` | 前端 API 客户端 |
| `scripts/` | 部署配置和维护脚本 |
| `start-local-dev.bat` | Windows 本地开发启动脚本 |
| `docker-compose.yml` | Docker Compose 部署入口 |
| `docs/` | 用户说明、MCP 工具参考、测试说明与项目文档 |

## 文档导航

| 文档 | 内容 |
|---|---|
| [架构设计](./architecture.md) | 组件边界、启动链路与记忆图数据流 |
| [API 参考](./api.md) | REST 基础路径、路由分组、认证与 OpenAPI 入口 |
| [数据库设计](./database.md) | 核心表、关系、索引与迁移方式 |
| [部署与运行](./deployment.md) | 本地开发、MCP 服务、Docker 与安全边界 |
| [技术栈](./tech-stack.md) | 框架、运行时、依赖与测试工具 |
| [开发约定](./conventions.md) | 目录约定、测试命令与文档维护规则 |
| [记忆系统建设指南](./memory-system-guide.md) | 协议边界、社区实践与建设检查表 |
| [交接文档 2026-10-22](./handoff-2026-10-22.md) | 记忆系统重建的结论、踩坑与待办（新会话先读这篇） |
| [Agent 接入指南](./agent-integration.md) | 通用 MCP 与 DSH 接入、验证 |
| [个人记忆系统本机使用说明](./personal-memory-quickstart.md) | 本机服务启动、Claude Code / VS Code MCP 接入和当前能力边界 |
| [Nocturne V3.1 上下文交付方案](./nocturne-v3.1-context-delivery.md) | 摘要优先、渐进式披露、搜索索引同步和 Token 控制的已确认方案 |
| [Nocturne V3.1 迭代计划](./nocturne-v3.1-iteration-plan.md) | 阶段安排、任务依赖、验收清单、风险和当前进度 |
| [MCP 工具描述规范](./mcp-tool-descriptions.md) | 11 个 MCP 工具的简明描述与调用边界 |
| [分层读取与召回保持验收（2026-11-20）](./progressive-disclosure-2026-11-20.md) | 按 URI 取摘要、正文行段、SQL 片段按需生成、295 项全量回归与真实工作库快照对照 |
| [核心链路可用验收（2026-11-20 后续）](./memory-core-ready-2026-11-20.md) | 310 项回归、59/59 索引修复、语义当前版本校验与摘要交付、真实 stdio/NVIDIA Top1 验证 |
| [真实任务检索与加载成本验收（2026-11-20）](./real-task-eval-2026-11-20.md) | 通用记忆写入后的全文/语义 Top-1、Boot 成本与摘要压缩对照 |
| [记忆质量审计](./memory-quality-audit-2026-11-19.md) | 当前工作库只读质量检查结果与复核事项 |

## 相关现有文档

- [MCP 工具参考](../TOOLS.md)
- [后端测试说明](../testing.md)
- [推荐 System Prompt](../system_prompt.md)

## 参考
- 项目入口：[README.md](../../README.md)
- 技术与目录事实以当前源码和依赖清单为准；具体来源列在各主题文档末尾。

- [记忆质量只读审计](memory-quality-audit-2026-11-19.md)

- [自然语言改写召回评估](retrieval-paraphrase-eval-2026-11-19.md)

- [生命周期与摘要待复核清单](memory-lifecycle-review-2026-11-19.md)

- [V4.0 Agent 记忆调度验收集](agent-dispatch-evaluation-2026-11-19.md)

- [词法检索负向查询评估](lexical-negative-query-eval-2026-11-19.md)
