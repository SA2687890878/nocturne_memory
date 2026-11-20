# Nocturne 测试执行记录（2026-11-19）

## 本轮结果

| 范围 | 结果 | 耗时 |
|---|---:|---:|
| MCP 定向回归：`backend/tests/mcp/test_mcp_tools.py` | 49 passed，1 warning | 14.80s |
| 后端全量：`backend/tests` | 277 passed，25 warnings | 103.57s |

## 执行方式与安全边界

- 通过已授权的 `myPrivateSpace` 项目执行范围，调用 Nocturne 项目现有 `.venv` 运行测试。
- 测试使用 `backend/tests/conftest.py` 的隔离 SQLite 测试库和 pytest 临时目录；未对真实工作库执行写入。
- 未修改业务源码、配置、NVIDIA 凭据或真实记忆数据。
- 临时测试启动脚本和结果文件已清理。
- 未提交 Git。

## Warning 说明

25 条 warning 中包含 anyio 对 pytest 内部 `CallSpec2` 别名的弃用提示，以及测试环境未设置 API_TOKEN 的提示。测试结果为通过；这些 warning 不应被误报为测试失败，也应在后续依赖升级/测试配置维护时处理。

## 关键词检索提示回归（19:34）

- 修改后再次运行 `backend/tests/mcp/test_mcp_tools.py`，JUnit结果：49 tests、0 failures、0 errors、0 skipped，17.368秒。
- 新增/强化的断言检查 `search_memory` 工具描述包含“2-5个有区分度的关键词/短语”及“不直接提交完整问题长句”。
- 结果文件：`.tmp/runtime/keyword-regression/junit.xml`；pytest日志：`.tmp/runtime/keyword-regression/pytest.log`。
- 这是定向回归，不替代此前全量测试277 passed的结果；本轮未重跑全量测试。

## Deva 关闭后的全量回归与 stdio 运行时验收（19:44～19:50）

- 全量 `backend/tests`：**277 passed，0 failures，0 errors，0 skipped，123.374秒**。JUnit：`.tmp/runtime/full-regression-20261119/junit.xml`；日志：`.tmp/runtime/full-regression-20261119/pytest.log`。
- 首次启动测试时，收集阶段因启动器未加入项目根路径而失败；修正 `sys.path` 后重新执行，最终全量通过。最终结果以JUnit汇总为准。
- Deva 已关闭后，使用与 Deva 配置一致的 stdio 启动参数（`D:\\Python\\python.exe backend/mcp_server.py`、`NOCTURNE_NO_UI=1`）创建一次性 MCP 客户端连接。
- 新进程暴露 **11 个 MCP 工具**；`search_memory` 工具描述已包含 2～5 个关键词压缩规则。
- 真实只读检索验证：关键词查询 `Nocturne 唯一记忆真源 旧插件退役` 在 `include_partial=false`、`include_snippets=false` 下命中预期 URI；响应 575 字符。
- 该验收证明**新 stdio 进程**已加载新规则；Deva 客户端本身当时关闭，尚未验证其重开后的首个会话行为。
- HTTP 8233 端口仍由旧 PID 19168 监听，宿主标记为 FOREIGN / 不可终止，故未强制重启，也未启动重复服务。Deva 的 stdio 配置已保存，下一次启动将读取当前源码。

## 对目标的意义

本轮证明当前代码与测试集整体保持回归通过，包含按需读取、索引导航、MCP工具描述等相关测试覆盖。

但自动化测试通过不等于真实客户端行为已验收。Deva 会话读取量、正文展开数量、真实模型 Token 仍需独立采集验证；此前 cl100k/o200k 仅为代理估算，不能替代真实 Token 统计。

## 2026-11-20 09:25 全量回归复测

- 本次执行入口：Nexus 受管 Python 脚本。宿主解释器为 `D:\Python\python.exe`；将项目 `.venv\Lib\site-packages` 加入 `sys.path`，并在 Nocturne 项目根目录调用 pytest 9.2.0。
- 重要限制：**不是直接由 `.venv\Scripts\python.exe` 启动**。因此这是“宿主解释器 + 项目 venv 依赖路径”的全量回归，不应描述为原生 venv 解释器测试。
- 单测 `backend/tests/unit/test_vector_index.py::test_index_upsert_search_health_and_delete`：**1 passed，1 warning，1.30s**。此前 SQLite/FTS5 fixture 错误在该次运行中未复现。
- 全量 `backend/tests`：**277 passed，25 warnings，114.11s，exit code 0**。
- 25 条 warning：AnyIO 对 pytest 内部 `CallSpec2` 别名的弃用提示，以及测试运行环境未设置 `API_TOKEN` 的提示。
- 本次没有测试失败；未修改业务源码、迁移 SQL、真实工作库、向量索引或 NVIDIA 凭据；临时解释器探针已删除；未提交 Git。
- 历史 SQLite 错误在本次运行未复现，但没有定位/修复其根因；需要原生 venv 解释器复验。
- Deva 客户端仍需正常启动后验收真实会话行为；没有关闭 SAFE 模式或绕过启动限制。
