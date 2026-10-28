# V3 上线部署与运行验证收据

时间：2026-10-28 18:20–19:15（Asia/Shanghai）
决定：按用户选择保留活动库现状（015 已在 2026-10-28 08:31:29 UTC 应用，36 节点全为 unspecified），不恢复旧备份；本轮不新增 DDL、不批量治理存量、不更新阅读插件。

## 备份（可回退）

目录：`E:/myPrivateSpace/nocturne_memory/backups/v3-rollout-1793181513551/`

| 资产 | 说明 |
| --- | --- |
| `active-before.sqlite` | 停服后 SQLite 在线备份，integrity_check = ok |
| `state-before.json` | 业务表指纹、迁移版本 15、源池 151 行 |
| `changeset-before.json` | 当前源待审池原样副本，sha256 `bc429680…a505d8` |
| `code-before/` | 19 个被覆盖源文件的原版本 |
| `mcp-connector.before.json` | 连接器配置原记录（含私有配置，不外传） |
| `memory-lifecycle.md.before-v3.md` | 全局写作规则改前版本 |
| `nocturne-memory-backend.vbs.bak` | 原开机自启脚本备份 |

## 部署

- 源工作树 `E:/myPrivateSpace/nocturne_memory`：19 个修改文件 + 12 个新增文件，逐个 sha256 与隔离 worktree 一致，0 mismatch。
- 前端生产构建：1799 modules，exit 0；产物含 `lifecycle_status`。
- 连接器 `json-nocturne_memory`：仅改 `SKIP_DB_INIT="1"`、`NOCTURNE_NO_UI=""`；URL、SNAPSHOT_DIR、NAMESPACE、命令与 cwd 全部保留。
- 开机自启 `nocturne-memory-backend.vbs` 改名为 `.disabled`，避免下次登录与 MCP 抢 8233 或重复初始化；备份在回退目录，可恢复。
- `start-local-dev.bat` 仅作开发入口（会抢占 8233/3000），已在 AGENTS 与全局规则注明。

## 运行验证（实际进程）

- 唯一入口：MCP 进程（随会话重启；部署期间 PID 27416 → 26084 → 19632），`127.0.0.1:8233` LISTEN；`/health` 200；内置 Web `/` 200 text/html。
- 连接器重连后 Host 注册 19 个工具，`connectionState=healthy`；`mcp_connector_health_check` 对这条手工 JSON 连接仍误报 not-configured，但实际工具调用正常。
- 独立开发的 Vite `127.0.0.1:3000` 在 19:00 前后退出（非本方案组件，不参与正式入口）；内置页面不依赖它。
- 数据未变：nodes 36 / memories 38 / edges 35 / paths 35 / glossary_keywords 8 / presets 1 / schema_migrations 15；业务指纹前后一致；源池仍 151 行、字节哈希不变。
- 功能：`read_memory("system://boot")` 正常且显示 `Lifecycle: unspecified`；`/api/browse/node` 返回 `lifecycle_status`，children 亦有该字段；`/api/review/groups` 仍 35 组。
- MCP 工具面：create/update 支持生命周期字段，检索默认 `include_obsolete=False`，只读验证未触发源池改写。
- 全局规则已激活 V3 写作约定（Node 状态字段、原生关键词约束、默认召回排除 obsolete）。

## 部署后修复：内置 UI 构建挂起

- 现象：内置页面停在 BUILDING（`npm run build` 由 MCP 子进程启动，继承了 stdio 的 JSON-RPC stdin，构建进程挂起不退出）。
- 修复：`backend/frontend_builder.py` 三处 `subprocess.run` 增加 `stdin=subprocess.DEVNULL`；重启 MCP 后自动 `npm install` + `npm run build` 完成，写入 `dist/.build_version=2.5.6`，`/api/build/status` 变为 ready。
- 副作用：`frontend/node_modules` 由 Junction 变为实体目录（npm install 行为），`package.json`/锁文件未变，构建产物文件名哈希一致。
- 回归：修复后后端 198 通过。

## 验收对照

T01–T25 逐条证据见 `acceptance-matrix.md`；后端 198、前端 17 全绿，T10/T17/T18 为部分覆盖，PostgreSQL 未执行。

## 存量状态迁移（用户授权后执行）

- 迁移前在线备份：`backups/v3-rollout-1793181513551/active-before-governance.sqlite`（integrity ok）。
- 依据：35 条有当前正文的节点，正文首行均为 `状态: 在用`；经人工 REST 端点（绕过 changeset）写入 `lifecycle_status=active`，未改正文。
- 结果：nodes 中 active 35、unspecified 1（虚拟 root）；memories 仍 38 条、当前版本 35 条，正文哈希前后一致（`f8db9a2f60dae179`），未产生内容版本。
- 待审池未动：仍是 151 行 / 35 组，字节哈希 `bc429680…`。

## 原生关键词为何没有批量填充

- 正文里共 106 个不同“检索词”，其中 13 个出现在 3 个节点（命中率 8.6%），超过 <5% 预算；其余 93 个只出现在 1 个节点内，绑定了也不会在别处触发。
- 按方案第 11/20 条（真实触发源、<5%、每词≤2 节点），106 个词中 0 个合格，因此未导入；原生 Keywords 仍是 8 个。要当“标签”用是另一种语义，需另立字段与授权。

## 事故与修复：8233 被开发用 uvicorn 抢占

- 19:14 有一个 `python -m uvicorn main:app --port 8233 --reload` 的 cmd 窗口启动，占住 8233；MCP 内置 Web 无法绑定，API/UI 实际由该 dev 进程提供，其默认快照目录指向仓库 `snapshots/`，导致 Review 显示 0 组（真实待审池仍在原目录，未损坏）。
- 处理：停止该 uvicorn 及其 reload 子进程，重启 MCP（当前唯一 PID 2588 占用 8233）；Review 恢复 35 组，源池字节哈希不变。
- 已确认 MCP 的 SNAPSHOT_DIR 实际生效（回退到原中文路径验证通过）；试验用的 ASCII junction 已删除。
- 教训：不要与 MCP 并行启动 `start-local-dev.bat` 或手动 uvicorn；端口被占时 MCP 不会报错，只会静默不提供 Web。

## 未覆盖与残余风险

- 视觉核对已用 Edge 无头截图完成：`screenshots/review-live.png`（35 组待审）、`memory-active-live.png`（节点显示“在用”）；未做交互点击自动化。
- PostgreSQL 路径未在本机真实库执行。
- 正文里的 `状态:` 与“检索词”行作为历史残留保留（方案选择不重写历史）；审计会提示残留，不回写字段。
- MCP 与 DSH 会话同生命周期：DSH 不运行则内置 Web 不在线。

## 明确未做

未提交/合并/推送，未恢复旧备份，未改写任何记忆正文、未绑定新关键词、未更新阅读插件、未新增数据库结构；仅把 35 个节点的状态从正文迁移到字段。