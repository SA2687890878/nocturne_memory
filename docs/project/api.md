# API 参考

## 概述
REST API 由 FastAPI 提供，统一前缀为 `/api`；MCP 的 stdio、SSE 与 Streamable HTTP 接口另见部署说明和 [MCP 工具参考](../TOOLS.md)。

## 基础信息

| 项目 | 说明 |
|---|---|
| REST 基础路径 | `/api` |
| Swagger UI | `/api/docs` |
| OpenAPI JSON | `/api/openapi.json` |
| 健康检查 | `/health`、`/api/health` |
| 认证 | Bearer Token 中间件；部署远程服务前需配置认证 |

当前中间件显式排除健康检查和构建状态查询：`/api/health`、`/health`、`/api/build-status`、`/api/build/status`。其他 API 按认证中间件策略处理。不要将真实令牌写入文档或提交到仓库。

## 路由分组

| 路由 | 主要用途 | 代表性操作 |
|---|---|---|
| `/api/browse` | Namespace/domain、节点树、别名、重命名、Glossary 与搜索 | `GET/POST/PUT/DELETE /node`、`GET /search` |
| `/api/review` | 变更分组、差异查看、回滚和已废弃记忆管理 | `GET /groups`、`GET /groups/{node_uuid}/diff`、`POST /groups/{node_uuid}/rollback` |
| `/api/maintenance` | 孤儿记录检查/恢复/清理、访问日志统计与清理 | `GET /orphans`、`POST /orphans/{memory_id}/restore` |
| `/api/settings` | 应用设置、Boot URIs、数据库状态与操作 | `GET/PUT /`、`GET/PUT /boot-uris`、`POST /database/test` |
| `/api/presets` | 启动 URI 预设的增删改查、激活与复制 | `GET/POST /`、`POST /{preset_id}/activate` |
| 构建状态 | Dashboard 构建状态与重试，包含兼容别名 | `GET /api/build-status`、`GET /api/build/status`、`POST /api/build-retry`、`POST /api/build/retry` |

上表是路由分组和入口示例，不替代运行时 OpenAPI 对参数、请求体和响应模型的定义。

## 请求示例

在本地服务运行并完成认证后，使用浏览器访问 `http://127.0.0.1:8233/api/docs` 查看交互式 API 文档。具体主机、端口和认证配置以实例配置为准。

## MCP 接口

Web 模式由 MCP Server 提供 `/sse` 和 `/mcp` 传输端点；stdio 模式直接启动 MCP 进程。工具名称、参数和使用示例见 [MCP 工具参考](../TOOLS.md)。

## 参考
- [路由注册与 API 前缀](../../backend/web_app.py#L139-L168)
- [认证豁免路径](../../backend/web_app.py#L174-L185)
- [路由注册模块](../../backend/api/__init__.py)
- [浏览路由](../../backend/api/browse.py)
- [审核路由](../../backend/api/review.py)
- [维护路由](../../backend/api/maintenance.py)
- [设置路由](../../backend/api/settings.py)
- [预设路由](../../backend/api/presets.py)
- [构建路由](../../backend/api/build.py)
