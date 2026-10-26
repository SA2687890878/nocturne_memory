# 架构设计

## 概述
系统由 MCP 接入、FastAPI Web 应用、React 管理界面和关系数据库组成；MCP 与 Dashboard 共用后端数据层。

## 整体架构

```text
AI 客户端 ── MCP stdio / SSE / Streamable HTTP ──┐
                                                  ├─ 后端 Web 应用 ── SQLite / PostgreSQL
浏览器 ── React Dashboard ── REST API (/api) ────┘
```

后端同时提供 REST 路由和静态前端 SPA。Web 应用把 FastAPI 路由挂载在 `/api`，并把未命中后端前缀的浏览器请求交给前端 SPA。MCP 传输路由由统一服务入口按需加入。

## 组件职责

| 组件 | 主要职责 |
|---|---|
| MCP Server | 为 Agent 提供记忆读取、创建、更新、路径与搜索等工具；传输说明见 [MCP 工具参考](../TOOLS.md) |
| REST API | Dashboard 的浏览、编辑、审核、设置、维护与构建状态接口 |
| 数据访问层 | SQLAlchemy async engine/session、数据库初始化、迁移与图操作 |
| 搜索层 | 从活动记忆和可达路径生成派生搜索文档；SQLite 使用 FTS5，PostgreSQL 使用 GIN/全文查询 |
| Dashboard | React + Vite 管理界面，按功能组织组件并通过统一 API 客户端访问后端 |

## 记忆数据流

1. 记忆概念由 `Node` 的 UUID 标识；正文版本保存在 `Memory`，新版本不改变节点身份。
2. `Edge` 表示父子方向关系，并保存显示名、优先级和 disclosure。
3. `Path` 将 namespace、domain、URI path 映射到图关系，供 `domain://path` 路由使用；图结构以 `edges` 为准。
4. 搜索索引从活动记忆、可达路径和关键词生成；它是派生数据，可由实时图数据重建。

## 启动与依赖关系

- `backend/main.py` 创建 REST + Dashboard 应用。
- `backend/run_sse.py` 将 SSE 与 Streamable HTTP MCP 传输并入统一 Web 应用。
- 应用 lifespan 确保配置存在、初始化数据库并执行迁移、从配置晋升预设，并在后台检查前端构建状态。
- Dashboard 使用 REST API；API 与 MCP 都经数据库访问层读写记忆数据。

## 关键设计决策

- **身份与内容分离**：节点 UUID 稳定，正文以版本行保存，便于版本审查和回滚。
- **图结构与 URI 路由分离**：Edge 表达关系，Path 是便于按 URI 访问的路径映射。
- **Namespace 隔离**：数据库路径、搜索文档和访问日志带 namespace，以支持同实例中隔离多个人格/Agent。
- **搜索为派生索引**：搜索结果来自数据库中的派生文档与数据库原生全文检索，不是向量检索。

## 参考
- [统一 Web 应用](../../backend/web_app.py#L130-L196)
- [应用生命周期与中间件](../../backend/web_app.py#L37-L60)
- [主 Web 入口](../../backend/main.py#L17-L40)
- [MCP + Web 入口](../../backend/run_sse.py#L22-L74)
- [核心 ORM 模型](../../backend/db/models.py#L73-L271)
- [搜索索引实现](../../backend/db/search.py#L29-L40)
