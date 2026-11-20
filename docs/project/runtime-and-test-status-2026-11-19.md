# 本轮回归与运行时状态（2026-11-19）

## 完整回归尝试

- 执行范围：`backend/tests`。
- 两次运行均在测试夹具初始化 SQLite 临时库时失败，结果为 `1 warning, 277 errors`，典型错误：`sqlite3.OperationalError: unable to open database file`。
- 第一次默认 pytest 临时目录；第二次指定项目内 ASCII 路径 `.tmp/pytest-basetemp`；第三次额外设置独立 `TEST_DATABASE_URL=sqlite+aiosqlite:///E:/myPrivateSpace/nocturne_memory/.tmp/nocturne-pytest.sqlite`，仍然出现同类临时库打开错误。
- 失败发生在数据库初始化/`DROP TABLE IF EXISTS search_documents_fts` 阶段；当前证据不支持将其归因为 277 个产品代码断言缺陷。
- 历史最近一次完整测试记录仍为 277 passed；本轮未能复现。需要单独定位 Windows + pytest tmp_path + SQLite URL 的临时库创建问题后再重新验收。
- 本轮未修改生产数据库配置、真实工作库或测试夹具。

## Deva 运行时

- 用户确认 Deva 当前已关闭。
- 尝试通过宿主应用启动通路启动 `D:\Deva\Deva.exe`，被宿主 SAFE 模式阻止：应用启动需要关闭安全层。
- 未关闭安全层、未绕过限制。源码与 Deva 配置文件中已保存的关键词压缩规则保持原样。
- 既有记录显示新启动的独立 stdio MCP 已加载关键词规则并完成一次只读检索；Deva 客户端本身仍需下次正常启动后验收。

## 本轮结论

- 检索Top10、相关性候选快照、L0/摘要预算对照已完成并保存。
- L0 对照实验中服务端估算 Token 降低 42.41%，候选集合和目标召回均保持 18/18；该估算不是供应商真实 Token。
- 当前主要阻塞是完整测试的临时 SQLite 环境问题和 Deva 运行时启动受 SAFE 模式限制。

## 2026-11-20 继续交付诊断

- 再次用全新 `.tmp/pytest-diagnostic` 路径运行单测，失败仍发生于 autouse fixture 的 `_reset_database()` -> `DatabaseManager.init_db()` -> migration 010 的 FTS5 DROP。
- 失败后独立进程检查同一 `test.db`：`PRAGMA integrity_check` 返回 `ok`；FTS5 主表及 shadow tables 均存在；独立 sqlite3 连接执行 `DROP TABLE IF EXISTS search_documents_fts` 成功。说明数据库文件没有持续性损坏，FTS5 DROP SQL本身可执行。
- 当前 `conftest.py` 的 `Path.as_posix()` URL规范化没有消除 pytest 内的首次初始化失败；该改动仅保留为跨平台路径规范化，不作为故障修复结论。
- 最新单测结果仍为 1 error、1 warning；没有完成全量回归。下一步需在 pytest 失败发生的同一连接/事件循环内采集 SQLAlchemy connection、`PRAGMA database_list`、WAL/SHM文件状态，定位瞬态连接或事件循环问题。
- 本轮未修改真实工作库、迁移 SQL、检索算法或向量索引；Deva客户端仍未启动，尚无客户端运行时验收。

## 2026-11-20 追加诊断与披露预算规则

- 单测 `test_index_upsert_search_health_and_delete` 仍在 autouse fixture 初始化阶段失败；pytest 已成功创建 `test.db`、WAL/SHM 文件，并成功生成在线备份，随后迁移 `010_v2.0.0_add_namespace.py` 执行 `DROP TABLE IF EXISTS search_documents_fts` 时抛出 `sqlite3.OperationalError: unable to open database file`。
- 使用项目 `.tmp` 下独立路径直接调用 `DatabaseManager.init_db()` 成功，说明不是 SQLite/SQLAlchemy 整体不可用；故障范围进一步收敛到 pytest 执行上下文/fixture 生命周期，尚未定位根因，不改迁移代码。
- 追加对照：同一失败测试数据库在 pytest 进程退出后，使用正斜杠 URL 重新调用 `DatabaseManager.init_db()` 成功；全新 `.tmp/direct-fresh/test.db` 直接初始化成功；模拟 config 缓存失效、环境变量设置、`close_db()`、`get_db_manager()` 的独立生命周期也成功。说明问题局限于 pytest 执行上下文/fixture 生命周期，尚不能归因于路径分隔符。
- `conftest.py` 默认 SQLite URL 已规范化为 `Path.as_posix()`，但单测复跑仍失败；该改动目前只是 Windows URL 规范化，不是根因修复，必须继续定位后再验收。
- 失败测试库可在进程退出后被 sqlite3 正常打开，直接执行 `DROP TABLE IF EXISTS search_documents_fts` 成功；FTS5 DDL 本身未复现故障。
- 已将披露预算策略同步至 `docs/system_prompt.md`、`backend/mcp_server.py` 工具描述及其测试断言、`docs/project/mcp-tool-descriptions.md`、Deva `mcp.json` 和 `memory.json`：已知 URI/纯定位可用 L0（`token_budget=0`）；陌生候选相关性判断保留 L1 摘要预算；禁止全局默认 0。
- 静态验证通过：导入 MCP 模块、检查工具描述规则、编译 `mcp_server.py` 与 `test_mcp_tools.py` 均成功。该验证不等同于 pytest 测试通过。
- Deva 进程仍未启动；本轮未绕过 SAFE 模式。Deva 两份 JSON 配置已更新，但尚未完成客户端运行时验收。

## 2026-11-20 09:25 全量回归复测

- 执行器状态复核：LocalBridge Runner 实际可用，`myPrivateSpace` 与 `nocturne_memory` 均返回 `available=true`、`healthy=true`；Nocturne 子项目 `executionMode=disabled`，通过授权父项目 `myPrivateSpace` 执行。
- 使用宿主 Python `D:\Python\python.exe`，将 Nocturne 项目 `.venv\Lib\site-packages` 加入 `sys.path`，并在项目根目录运行 pytest。注意：本次不是直接由 `.venv\Scripts\python.exe` 启动，故记录为“项目虚拟环境依赖加载下的受管回归”，不冒称原生 venv 解释器验收。
- 单测 `backend/tests/unit/test_vector_index.py::test_index_upsert_search_health_and_delete`：**1 passed，1 warning，1.30s**。此前 SQLite/FTS5 fixture 错误在本次运行中未复现。
- 全量 `backend/tests`：**277 passed，25 warnings，114.11s，exit code 0**。本次没有测试失败。
- 25 条 warning 包含 AnyIO 对 pytest 内部 `CallSpec2` 别名的弃用提示，以及测试环境未设置 `API_TOKEN` 的提示；不影响本次测试通过，但应纳入后续维护。
- 本次未修改业务代码、迁移 SQL、真实工作库、向量索引或 NVIDIA 凭据；临时解释器探针已删除；未提交 Git。
- 结论更新：此前“完整测试被 SQLite 临时库错误阻塞”的状态已被本次全量回归通过结果 supersede。SQLite 问题当前未复现，但根因并未被定位或修复，后续需在原生 venv 解释器下复验。
- Deva 客户端仍需正常启动后验收真实会话行为；未关闭 SAFE 模式或绕过启动限制。
