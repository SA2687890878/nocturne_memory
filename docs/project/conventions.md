# 开发约定

## 概述
本文件区分已在仓库中确认的结构/命令与本项目文档中心新确立的维护规则；未从源码或项目说明确认的约定不作推断。

## 目录与实现约定

- REST 路由按领域模块放在 `backend/api/`，通过 APIRouter 注册到统一 Web 应用。
- 数据库模型和连接管理位于 `backend/db/`；表结构变化放在 `backend/db/migrations/`。
- 前端界面按功能组织在 `frontend/src/features/`；请求统一通过 `frontend/src/lib/api.js`。
- 后端测试位于 `backend/tests/`；前端测试使用 Vitest。

## 日常验证命令

```powershell
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
python -m pytest
cd ..\frontend
npm run test:run
npm run build
```

新增 API、表或搜索字段时，至少同步对应测试和本项目文档；对数据库结构的修改必须走迁移，不应只改 ORM 模型。

## 文档维护规则

- 项目级文档集中在 `docs/project/`，本目录 README 作为导航入口。
- 功能级说明按功能名维护在 `docs/features/{name}/`；问题排查记录维护在 `docs/issues/`。目录尚无文档时，不创建空链接。
- 只写有代码、配置或项目说明支撑的事实；版本号需注明是锁定版本、最低版本还是范围。
- 不把真实 Token、密码、个人数据或生产连接信息写入文档。
- 更新路由、表结构、启动方式或命令时，同步修订本中心对应页面。

## Git 约定
项目说明中没有确认统一的分支命名或提交信息格式；本文件不虚构一套新规则。按当前协作任务或仓库另行明确的要求执行。

## 参考
- [后端与前端结构](../../AGENTS.md)
- [路由模块注册](../../backend/api/__init__.py)
- [统一前端 API 客户端](../../frontend/src/lib/api.js)
- [前端测试脚本](../../frontend/package.json)
