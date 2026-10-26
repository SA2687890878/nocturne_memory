# 部署与运行

## 概述
支持 Windows 本地开发、MCP stdio 客户端启动，以及 Docker Compose 部署。远程暴露服务时必须启用认证；不在文档或配置示例中填写真实令牌和密码。

## 本地开发（Windows）

1. 安装 Python、Node.js/npm。
2. 安装后端依赖：`python -m pip install -r backend/requirements.txt`。
3. 安装前端依赖：`cd frontend && npm install`。
4. 回到项目根目录运行 `start-local-dev.bat`。

脚本把后端绑定到 `127.0.0.1:8233`、Vite 绑定到 `127.0.0.1:3000`。脚本会终止旧窗口及占用这两个端口的监听进程；确认可停止后再运行。

## MCP 服务运行模式

- **stdio**：MCP 客户端直接以 Python 启动 `backend/mcp_server.py`；客户端配置示例见根目录 README。
- **SSE + Streamable HTTP + REST + Dashboard**：运行 `python backend/run_sse.py`，默认 Web 端口由实例配置提供，MCP 传输端点为 `/sse` 与 `/mcp`，管理界面为根路径，REST 文档为 `/api/docs`。
- **仅 REST + Dashboard**：后端 Web 入口为 `backend/main.py`。本地开发脚本会用 Uvicorn 启动它。

## Docker Compose

仓库根目录提供 `docker-compose.yml`。按根目录 README 的 Docker 部署步骤执行：先运行 `python scripts/setup_docker.py` 生成本机配置，再运行 `docker compose up -d --build`。容器首次启动会初始化数据库并运行迁移。部署细节和常用操作以根目录 README 与 compose 文件为准。

## 网络与认证边界

- 本地开发脚本绑定 loopback 地址，不对局域网开放。
- 代码在绑定非本机地址前执行网络认证检查；远程部署先配置 API Token，再开放监听地址，并限制网络入口。
- 不要把 Token、数据库连接密码或生成后的配置文件写入文档、示例或版本库。
- 如需检查服务状态，可调用健康端点 `/health`；健康检查不代表 MCP 客户端配置或读写链路已验证。

## 测试与构建

```powershell
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
python -m pytest
cd ..\frontend
npm run test:run
npm run build
```

## 参考
- [本地开发启动脚本](../../start-local-dev.bat)
- [MCP/Web 组合入口](../../backend/run_sse.py#L22-L74)
- [网络认证检查](../../backend/main.py#L17-L37)
- [Docker Compose 文件](../../docker-compose.yml)
- [根目录安装与部署说明](../../README.md)
- [CI 后端测试工作流](../../.github/workflows/backend-tests.yml)
