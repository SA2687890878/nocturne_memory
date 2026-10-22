# Nocturne Memory

## 技术栈
- 后端：Python、FastAPI、Uvicorn、SQLAlchemy；默认 SQLite，也包含 PostgreSQL 驱动。
- 前端：React、Vite。

## 命令
- 构建前端：`cd frontend && npm run build`
- 前端测试：`cd frontend && npm run test:run`
- 后端测试：`cd backend && python -m pytest`
- 本地运行：双击根目录 `start-local-dev.bat`；前端 `127.0.0.1:3000`，后端 `127.0.0.1:8233`。

## 结构
- `backend/`：API、数据库与服务端入口。
- `frontend/`：React 管理界面及 Vite 开发服务器。

## 约定与红线
- 本地开发服务默认只绑定 `127.0.0.1`；不要改为对局域网开放，除非先配置并验证 API Token。
- 首次启动可能从 `.env` 生成根目录 `config.json`，数据库初始化会执行迁移；手动改库前先备份。

## 待确认
- 无。
