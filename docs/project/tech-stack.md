# 技术栈

## 概述
项目采用 Python/FastAPI 后端、MCP 服务、React/Vite 前端，并通过 SQLAlchemy async 访问 SQLite 或 PostgreSQL。

## 后端技术

| 技术 | 版本/约束 | 用途 |
|---|---|---|
| Python | CI 覆盖 3.10、3.12；Docker 基础镜像为 Python 3.12 | 后端运行时 |
| FastAPI | `>=0.109.0` | REST API 与 OpenAPI |
| Uvicorn | `>=0.27.0` | ASGI 服务运行 |
| SQLAlchemy | `>=2.0.0` | ORM 与异步数据库会话 |
| SQLite | `aiosqlite>=0.19.0` | 本地默认数据库与 FTS5 |
| PostgreSQL | `asyncpg>=0.29.0` | PostgreSQL 异步驱动与全文检索 |
| MCP SDK | `mcp>=0.1.0` | MCP Server 与传输 |
| Pydantic | `>=2.5.3` | API 数据模型与配置校验 |

依赖约束来自 requirements 文件；`>=` 是最低版本，不代表仓库锁定了该版本。

## 前端技术

| 技术 | package.json 声明 | 用途 |
|---|---|---|
| React / React DOM | `^18.2.0` | 管理界面 |
| Vite | `^7.3.3` | 开发服务器与构建 |
| React Router DOM | `^6.30.3` | 前端路由 |
| Axios | `^1.16.1` | HTTP 客户端 |
| Tailwind CSS | `^3.3.0` | 样式工具链 |
| Vitest | `^4.1.7` | 前端测试 |

## 运行与质量工具

- 后端测试：pytest（开发依赖见 `backend/requirements-dev.txt`）；CI 包含 SQLite 测试和 PostgreSQL 集成测试。
- 前端测试：Vitest；构建命令为 `npm run build`。
- Docker：后端镜像基于 `python:3.12-slim`。

## 参考
- [后端运行依赖](../../backend/requirements.txt)
- [后端开发/测试依赖](../../backend/requirements-dev.txt)
- [前端依赖与脚本](../../frontend/package.json)
- [CI Python 版本与测试矩阵](../../.github/workflows/backend-tests.yml)
- [后端 Dockerfile](../../backend/Dockerfile)
