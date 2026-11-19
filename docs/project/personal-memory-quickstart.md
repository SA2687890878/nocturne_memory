# Nocturne 个人记忆系统：本机使用说明

## 当前运行状态（2026-11-19，客户端已确认可用）

- 唯一活动数据源：项目 `config.json` 指向的个人 SQLite 工作库 `work-memory.db`。不要把旧库接回配置。
- 可检索记忆：50 个 URI 路径，对应 48 条当前有效 Memory；48/48 当前有效 Memory 均有 L1 摘要；Memory ID 111 的摘要已补齐并验证。50/50 SearchDocument 与 URI 路径对齐。
- 向量索引：独立 sidecar `work-memory-vectors.db`，49 条元数据、49 条向量，完整性检查通过。模型 `nvidia/nemotron-3-embed-1b`，2048 维。
- 默认 `search_memory` 仍走全文检索；语义检索由 `semantic_search_memory` 显式触发，不自动混入默认结果。
- `search_memory` 默认只返回 L0 元数据与 L1 摘要，不返回正文片段；默认摘要预算 1200 estimated tokens，可由调用方传 `token_budget` 覆盖。需要原文线索时显式传 `include_snippets=true`。
- 2026-11-19 用户任务样本评估：19 个检索任务的全文 Recall@10 为 18/19（94.7%），MRR 0.912；其中 1 个词法漏召回由显式语义检索在 Top-1 找回。另有 1 个启动任务走 `system://boot` 直接入口，不计入搜索指标。未计算 Precision，因未人工标注其余候选是否无关。
- 新增自然语言改写专项：18 条改写查询 Recall@10 为 18/18（100%），MRR 0.9352；使用同一 Memory Node 身份核对。样本较小，Precision@10 仍未计算，详见 retrieval-paraphrase-eval-2026-11-19.md。
- 变更快照位于工作库同目录 `.nocturne-snapshots`，与源码目录分离。

## 启动 Dashboard / REST / MCP HTTP

双击项目根目录 `start-nocturne.bat`，启动 Dashboard、REST API 和 MCP HTTP：

- Dashboard：`http://127.0.0.1:8233/`
- API 文档：`http://127.0.0.1:8233/api/docs`
- 健康检查：`http://127.0.0.1:8233/api/health`
- MCP HTTP：`http://127.0.0.1:8233/mcp`

当前启动脚本使用 `D:\Python\python.exe`（来自项目虚拟环境记录的基础解释器），并将 `TMP/TEMP` 指向项目 `.tmp/runtime`。本机验证发现直接使用 `.venv` 解释器访问外部中文目录中的 SQLite 工作库会失败，因此 HTTP 与 stdio 统一使用该基础解释器。

## Claude Code

- 用户级 `~/.claude.json` 中的 `memory` MCP 已指向 `scripts/start-nocturne-mcp.bat`。原官方示例服务保留为 `memory-legacy`，没有删除。
- 用户级 `~/.claude/CLAUDE.md` 已引入 `~/.claude/rules/nocturne-memory.md`，定义启动读取、摘要优先、按需展开、写入查重和冲突处理规则。
- stdio 已通过实际 MCP 客户端验收：11 个工具可见；真实工作库诊断读写通过；临时记忆 create/read/update/delete 全流程通过，探测记录已删除。用户已确认客户端能够正常使用 Nocturne 记忆系统。
- **重启 Claude Code** 后加载最新 MCP 配置和全局规则。新会话启动时读取 `read_memory("system://boot")`；该 Boot 当前只交付 2 条核心摘要，约 204 estimated tokens，不自动展开正文。

## Deva

- 用户级配置：`%USERPROFILE%\.deva\mcp.json`，服务名 `nocturne-memory`。
- 传输方式：stdio；命令 `D:\Python\python.exe`；入口 `E:\myPrivateSpace\nocturne_memory\backend\mcp_server.py`。
- 客户端已由用户确认可以正常使用 Nocturne MCP。修改 MCP 工具描述或配置后，重新加载该 MCP 服务以获取最新信息。

## VS Code / GitHub Copilot

项目已添加 `.vscode/mcp.json`，服务器名为 `nocturne`。在 VS Code 中 Reload Window 并刷新 MCP Server 后使用。

## Nocturne 项目长期记忆

- 稳定产品定位与决策已沉淀到 `core://agent/nocturne-memory`；动态进度仍以项目文档为准。

## 检索和披露规则

1. 不知道 URI 时先用 `search_memory`，不要猜 URI。 SQLite FTS 会尝试少量人工审核的短语别名，但这不等于通用语义理解。
2. 默认 `search_memory` 只返回 L0 元数据和 L1 摘要，不返回正文片段；摘要足够就停止。
3. 服务端默认每次搜索最多交付 1200 estimated tokens 的摘要，可由调用方传 `token_budget` 覆盖（0～20000）。这是近似预算，不是精确 tokenizer 计量。
4. 只有需要原文线索时才传 `include_snippets=true`；只有需要原文、代码、接口、参数、证据或核对冲突时，才调用 `read_memory(uri)` 展开正文。摘要缺失不等于允许自动展开。
5. 语义改写导致全文检索漏召回时，再使用 `semantic_search_memory`。向量距离不是置信度，命中后仍需读取并核验候选。
6. 默认只跟进直接关联，不递归加载整棵子树；满足任务需要后立即停止。

## 向量同步与诊断

- `search_memory` 不自动请求 Embeddings API。
- `semantic_search_memory` 会为当前查询生成 query embedding；`sync_semantic_index` 仅对新增或变化的记忆生成 passage embedding。用户已授权这些记忆文本用于 NVIDIA Embeddings。
- 可通过 MCP 调用 `sync_semantic_index`，或运行 `python scripts\sync-nocturne-vectors.py`。同步先完成全部向量生成，再原子更新 sidecar；原始工作库不被写入向量数据。
- `embedding.enabled=false` 保持不变：这表示不把向量自动融合进默认全文搜索，不影响显式语义检索。
- `diagnose_memory_backend` 检查当前 MCP 进程的数据库读写权限；写探测在事务中创建临时表后回滚，不留下业务数据。HTTP 与 stdio 两种进程均已验证通过。

## 安全边界

- 服务只绑定 `127.0.0.1`，不对局域网或公网开放；当前没有配置 API_TOKEN，不要将服务暴露到外网。
- API Key 只保存在本机 `config.json`，不要打印、复制到文档或提交到版本库。
- 新建记忆前先搜索查重；更新前先读取目标正文。
- 不调用 `delete_memory` 删除现有记忆，除非用户对具体记录明确授权；不要把删除当作归档。冲突先核实，不确定时保留。
- Claude Code 需重启以加载全局规则和 stdio 配置；VS Code 需 Reload Window 并刷新 MCP Server。
- 检索代码更新后需重启 Dashboard/API 服务，并重载已启动的 MCP stdio 客户端进程，才会应用最新短语别名策略。


## 建设完成度

当前系统已达到日常可用：V3.1 核心上下文交付已完成，V3.2 精准召回仍在验证，V3.3 记忆质量工程化和 V4.0 智能调度评估尚未全部完成。具体状态以 `nocturne-v3.1-iteration-plan.md` 文末“总体验收与路线状态”为准。


## 记忆质量检查

运行 D:\Python\python.exe scripts\audit-memory-quality.py 可对当前工作库执行只读质量检查，不会修改或删除任何记忆。结果检查摘要缺失、重复 Memory、索引一致性、Disclosure 和孤立搜索文档。

- 生命周期复核清单：docs/project/memory-lifecycle-review-2026-11-19.md（只读建议，不自动修改真实记忆）。
