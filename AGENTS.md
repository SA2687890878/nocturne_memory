# Nocturne Memory

## 技术栈
- 后端：Python、FastAPI、Uvicorn、SQLAlchemy；默认 SQLite，也包含 PostgreSQL 驱动。
- 前端：React、Vite。

## 命令
- 构建前端：`cd frontend && npm run build`
- 前端测试：`cd frontend && npm run test:run`
- 后端测试：`cd backend && python -m pytest`
- 正式入口：Nocturne MCP 进程（stdio 供 DSH，内置 Web UI `127.0.0.1:8233`），由 DSH 连接器启动；不要再单独启动 uvicorn，否则端口冲突。
- 开发入口：双击根目录 `start-local-dev.bat` 会抢占 `8233/3000`，仅限开发机使用。

## 结构
- `backend/`：API、数据库与服务端入口。
- `frontend/`：React 管理界面及 Vite 开发服务器。

## 约定与红线
- 本地开发服务默认只绑定 `127.0.0.1`；不要改为对局域网开放，除非先配置并验证 API Token。
- 首次启动可能从 `.env` 生成根目录 `config.json`，数据库初始化会执行迁移；手动改库前先备份。

## 待确认
- 无。
