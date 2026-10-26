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

## 相关现有文档

- [MCP 工具参考](../TOOLS.md)
- [后端测试说明](../testing.md)
- [推荐 System Prompt](../system_prompt.md)

## 参考
- 项目入口：[README.md](../../README.md)
- 技术与目录事实以当前源码和依赖清单为准；具体来源列在各主题文档末尾。
