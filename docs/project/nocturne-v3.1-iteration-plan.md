# Nocturne V3.1 迭代计划

> 文档状态：持续迭代中；以下历史阶段记录保留建设过程，当前准确状态以文末“2026-11-19 总体验收与路线状态”为准。
> 当前部署数据库：SQLite（`config.json` 配置为 `sqlite+aiosqlite`）；PostgreSQL 仅作为项目兼容分支，不是本轮实际迁移目标。
> 当前阶段：真实工作库读写已验证；46/46 条唯一 Memory 摘要有效、48/48 个 URI 路径可用摘要；Boot 默认只交付 L0/L1；向量候选索引独立维护，不进入默认全文搜索。  
> 目标：围绕“按需加载、渐进式披露、精准召回、节省 Token”完成 V3.1 上下文交付能力。

## 一、迭代目标与边界

V3.1 只解决一件事：让 AI 先拿到少量、可靠的记忆摘要，需要时再读取完整正文，避免每次把大量记忆全文塞进上下文。

本版本交付：

- Memory 版本级摘要的保存与读取。
- 搜索索引能够检索摘要并返回摘要状态。
- 搜索结果保留 URI / Alias / Path 的入口语义。
- `read_memory` 继续支持明确 URI 的全文读取。
- `system://boot` 默认按摘要和索引交付，不再无条件加载配置记忆全文。
- 简单的结果条数、内容长度和 Token 估算控制。

本版本不交付：向量数据库、后台自动摘要、多 Agent、ContextPackage 持久化、BudgetLedger、复杂摘要状态机、企业级权限/审计/治理平台。

## 二、迭代阶段

### 阶段 0：开发准备与基线确认

状态：**部分完成：开发环境已核对；工作数据库基线受权限阻塞**

任务：

1. 确认 Memory 版本关系、SearchDocument 索引维护路径、MCP 搜索/读取工具和 Boot 加载路径。
2. 确认当前迁移最高编号为 015，计划使用 016；实际编码前再次核对，避免分支变化。
3. 确认测试数据库连接目标，禁止误连真实业务数据。
4. 建立最小基线：Boot 当前输出长度、配置记忆全文读取次数、典型任务搜索结果和 Token 消耗。
5. 项目测试环境已修复：建立 `.venv`、补齐开发依赖，并提供 `scripts/run-tests.bat` 一键执行入口。

完成标准：开发人员知道改哪些文件、如何迁移、如何验证，且有改造前对照数据。

### 阶段 1：摘要数据模型与版本写入

状态：**代码实现及 SQLite 完整测试通过；真实库迁移待执行**

已完成：

- `Memory` 增加可空 `summary_content`、`summary_updated_at`。
- `SearchDocument` 增加 `summary_content`。
- 新增 `016_add_memory_summary.py`，覆盖 SQLite / PostgreSQL，并对 SQLite FTS5、PostgreSQL GIN 索引进行重建。
- `GraphService.update_memory_summary(memory_id, summary_content)` 按版本 ID 写入，支持清空摘要；历史版本摘要不会覆盖活动版本搜索索引。
- 正文变更创建新版本时摘要默认为空。

待完成：当前 SQLite 工作库验证与迁移；PostgreSQL 不属于当前部署验收项。

原任务与验收：

1. `Memory` 增加可空 `summary_content`、`summary_updated_at`。
2. `SearchDocument` 增加摘要字段，保持它作为派生索引数据的定位。
3. 新增 `016_add_memory_summary.py`，覆盖 SQLite 和 PostgreSQL。
4. 增加按 `memory_id` 更新摘要的能力；校验目标版本存在。
5. 正文更新产生新 Memory 版本时摘要为空；旧版本摘要保留。
6. 摘要更新后刷新对应 Node 的所有相关搜索文档。

主要文件：

- `backend/db/models.py`
- `backend/db/migrations/016_add_memory_summary.py`
- `backend/db/graph.py`（或核实后的现有写服务）
- 对应数据库/服务测试

完成标准：摘要严格绑定 Memory 版本；更新历史版本不会污染活动版本；迁移不回填虚假摘要。

### 阶段 2：搜索索引支持摘要

状态：**当前 SQLite 路径代码实现及完整测试通过；PostgreSQL 仅保留兼容分支**

已完成：

- 搜索文档创建、单 Node 刷新、全量重建同步摘要。
- SQLite FTS5 新增摘要列，BM25 权重同步调整。
- PostgreSQL 匹配和 rank 表达式加入摘要，并由迁移重建 GIN 索引。
- 搜索结果区分 Summary / Snippet，返回 `summary_status`、`memory_id`、`expandable`。
- 同 Node 多个命中入口只交付一份正文，同时将其他匹配 URI 作为 `aliases` 附加，保留入口元数据。

待完成：当前 SQLite 工作库验证；如未来启用 PostgreSQL，再补对应集成测试。

原任务与验收：

1. 搜索文档创建、单 Node 刷新、全量重建全部同步摘要。
2. SQLite FTS5 表结构、写入/删除/重建 SQL 和 BM25 权重一起更新。
3. PostgreSQL 全文匹配表达式和 rank 表达式一起加入摘要字段；如 GIN 索引表达式变化，执行安全重建。
4. 搜索结果返回摘要和 `summary_status`；`snippet` 仍明确代表正文命中片段。
5. 摘要缺失时返回 L0 + `MISSING`，不自动展开全文。
6. 修正按 `node_uuid` 去重导致入口丢失的问题：不重复返回多份正文，但保留有效 URI 入口及其真实 Edge Priority/Disclosure。

主要文件：

- `backend/db/search.py`
- `backend/db/models.py`
- 数据库迁移和搜索测试

当前部署完成标准：SQLite 可通过摘要关键词召回；重建索引不丢摘要；不同入口元数据不被错误覆盖。PostgreSQL 兼容性不作为当前部署阻塞项。

### 阶段 3：MCP 搜索结果与按需读取

状态：**代码实现及完整后端测试通过**

已完成：

- 现有 `search_memory` 输出摘要、摘要状态、正文 Snippet 和全文读取入口。
- 新增 `update_memory_summary(memory_id, summary_content)` MCP 写工具，由 AI 生成摘要、Nocturne 负责保存。
- 摘要更新进入现有 Changeset 变更记录。
- 原有 `search_memory` 参数和 `read_memory(uri)` 全文读取方式保持不变。

待完成：无当前数据库类型相关的 MCP 阻塞项；MCP SQLite 回归已通过。

原任务与验收：

1. 增强现有 `search_memory` 输出，加入摘要、摘要状态和是否可展开等信息。
2. 不新增独立 `get_context` 工具，不破坏现有参数。
3. 保留 `read_memory(uri)` 的全文读取行为。
4. 输出中明确区分 Summary 和正文 Snippet。

主要文件：

- `backend/mcp_server.py`
- MCP 工具测试

完成标准：旧客户端调用方式保持兼容；AI 能从搜索摘要判断是否需要继续调用 `read_memory`。

### 阶段 4：Boot 渐进式披露

状态：**代码实现及完整后端测试通过；真实工作库验证待完成**

已完成：

- 新增 `GraphService.get_memory_summary_by_path`，只查询 URI、Memory ID、摘要、Priority、Disclosure、Lifecycle 等字段，不查询正文。
- `system://boot` 默认只交付 L0 + L1；摘要缺失时标记 `MISSING`，不自动读取正文。
- 保留 `read_memory(uri)` 的完整正文读取。
- recent 区块已核对只包含 URI、Priority、Disclosure 和时间，不包含正文，因此保留最近 5 条轻量索引信息。
- Boot 和显式读取的访问日志改为等待写入完成，避免后台任务在数据库关闭后报错。

待完成：真实工作库验证和 Token 基线对比。

原任务与验收：

1. `system://boot` 配置 URI 默认返回 L0 + L1。
2. 摘要缺失时返回 L0 + `MISSING`，不自动回退正文。
3. 明确 URI 直读仍返回完整正文。
4. recent 正文读取检查已完成：查询只投影 URI 所需元数据；保留最近 5 条轻量索引信息。
5. 兼容现有 Boot URI 列表配置，不急着增加复杂的逐条配置结构。

主要文件：

- `backend/system_views.py`
- 相关 Boot / URI 读取测试

完成标准：Boot 不再无条件加载所有配置记忆全文；摘要缺失不会触发全文回退；必要的近期信息仍可用。

### 阶段 5：预算控制、回归与效果评估

状态：**基础预算已实现；真实任务评估待完成**

已完成：

- `system://boot` 增加 `boot_summary_token_budget` 服务端默认配置，默认 2000 estimated tokens，可在 `config.json` 覆盖。
- 使用 UTF-8 字节数做轻量 Token 估算，不引入 tokenizer 依赖；超预算时截断摘要或标记省略，并保留 `read_memory(uri)` 展开入口。
- 搜索结果条数仍由调用方的 `limit` 控制，服务端不额外建设预算账本。

待完成：真实任务评估集、Recall@10 / Precision@10、全文读取次数和 Token 消耗对比。

原任务与验收：

1. 由客户端优先控制本轮预算；服务端提供简单可配置默认值。
2. 控制候选数量、摘要数量和输出长度；Token 数先采用估算，不建设账本。
3. 选取至少 15 个真实任务作为评估集，覆盖用户偏好、项目延续、技术方案、历史决策、URI 直读等场景。
4. 对比改造前后的 Recall@10、Precision@10、全文读取次数、Boot 输出长度和 Token 消耗。
5. 检查 namespace、domain、lifecycle_status、Priority、Disclosure 和旧 MCP 调用兼容性。

完成标准：召回质量不明显下降，全文读取次数和上下文 Token 有可测量下降；没有以牺牲关键事实为代价强行省 Token。

## 三、建议开发顺序与依赖

```text
阶段0 基线确认
   ↓
阶段1 摘要字段 / 迁移 / 版本写入
   ↓
阶段2 搜索索引 / 摘要召回 / 入口语义
   ↓
阶段3 MCP 搜索输出 / 保留全文直读
   ↓
阶段4 Boot 渐进式披露
   ↓
阶段5 简单预算 / 回归 / 效果评估
```

阶段 1 和阶段 2 是数据链路基础，未完成前不要先改 Boot。阶段 3 必须保持旧工具兼容。阶段 4 需在摘要读取链路稳定后进行。阶段 5 用真实任务验证是否真的节省 Token。

## 四、跨阶段验收清单

- [ ] 新建 Memory 默认摘要为空，状态为 `MISSING`。
- [ ] 摘要写入按 `memory_id` 定位，时间戳正确更新。
- [ ] 正文更新后新版本摘要为空，旧版本摘要保留。
- [ ] 摘要更新同步所有相关 SearchDocument。
- [ ] SQLite FTS5 支持摘要检索，BM25 权重已同步。
- [ ] （可选兼容项）PostgreSQL 全文检索和 rank 表达式包含摘要；当前 SQLite 部署不以此作为验收条件。
- [ ] 全量索引重建后摘要仍可检索。
- [ ] 搜索结果区分 Summary 和 Snippet。
- [ ] Alias / Path 入口不丢失，Edge 元数据不张冠李戴。
- [ ] 摘要缺失不自动加载全文。
- [ ] `read_memory(uri)` 仍可读取完整正文。
- [x] `system://boot` 默认摘要优先；recent 区块只投影元数据，不重新加载记忆正文。
- [ ] 原有 MCP 工具名称和参数保持兼容。
- [x] 当前使用的 SQLite 迁移、索引和查询通过隔离测试。
- [ ] （可选兼容项）PostgreSQL 迁移、索引和查询通过隔离测试；仅在决定继续维护 PostgreSQL 部署支持时执行。
- [ ] 真实任务评估显示召回质量可接受，全文读取次数和 Token 消耗下降。

## 五、风险与处理方式

| 风险 | 处理方式 |
|---|---|
| 只改 ORM，漏改 FTS5/PG 全文索引 | 将索引创建、更新、删除、重建列为同一任务验收 |
| 摘要写到 Node 而不是 Memory 版本 | 所有摘要写入必须带 `memory_id` |
| Alias 去重修复后重复返回大量正文 | 正文按实体复用，入口元数据独立保留 |
| Boot 摘要化但 recent 仍加载长正文 | 将 recent 区块单独测量和控制 |
| PostgreSQL 备份回退不完整 | 迁移前核对 `pg_dump` 能力和备份结果；JSON 导出不当作完整回滚保障 |
| 为节省 Token 导致漏掉关键事实 | 以真实任务 Recall/Precision 和人工核对共同验收 |
| 测试环境缺少依赖或误连真实库 | 使用项目脚本自动准备依赖；测试默认使用隔离 SQLite，真实库迁移必须单独确认连接和备份 |

## 六、当前状态与下一步

当前已完成：

- V3.1 产品范围、披露规则和迭代计划已沉淀。
- Memory / SearchDocument 摘要字段和 016 迁移脚本已实现。
- GraphService 版本级摘要写入接口已实现。
- SQLite / PostgreSQL 搜索表达式已加入摘要；SQLite FTS5 已加入摘要列和对应 BM25 权重。
- 搜索结果已支持摘要状态、全文展开标记和 Alias 入口信息。
- MCP 已增加 `update_memory_summary` 写工具，搜索输出区分摘要与正文 Snippet。
- 新增摘要迁移、搜索版本语义、Alias 和 MCP 输出测试用例。
- 隔离 SQLite 实测通过：迁移可重复执行、摘要可通过 FTS 命中、索引刷新生效、正文更新产生空摘要的新版本、旧版本摘要保留、Alias 入口元数据保留。
- 变更文件 Python 编译检查通过。

当前未完成：

- 当前部署使用 SQLite；PostgreSQL 仅保留兼容分支，不作为本轮部署验收阻塞项。
- 真实工作 SQLite 文件存在，但执行环境仍无读取权限；未读取、未备份、未迁移，真实任务基线无法建立。
- 合成评估和 hard-negative 诊断已完成一轮；它们只能暴露词面检索边界，不能替代真实任务集。
- Boot 预算目前是摘要部分的轻量估算，不代表整个 Boot 输出或模型实际 Token 数。
- Boot 的 `system://recent` 虽然只输出 URI/元数据，但底层 `get_recent_memories()` 原先使用 `select(Memory, ...)`，会把完整 `Memory.content` 一并从 SQLite 读取到进程内；本轮已改为只查询 `Memory.id/created_at`、Edge 元数据、Path 和 lifecycle 字段，避免 recent 区块隐式读取正文。
- 新增 SQL 级回归测试，捕获 `get_recent_memories()` 实际执行的 SELECT，并断言不包含 `memories.content` / `memories.*`。
- 本轮全量后端回归：214 passed、0 failed、25 warnings，100.97 秒；`git diff --check` 通过。均为隔离 SQLite。
- 本轮发现并修复召回诊断测试文件末尾误追加的非 Python 文档文本；同时将实验改为直接操作隔离库中的 SearchDocument/FTS 辅助索引，不再写入 GlossaryKeyword。此前基于 GlossaryKeyword 得出的 100% 召回结论已撤回；修正实验结果为基线 10%、辅助索引 20%，Partial 无额外收益。
- 修复后专项文件回归：`backend/tests/service/test_lifecycle_recall.py`，10 passed、1 warning（19.09 秒）。随后全量后端回归：213 passed、0 failed、25 warnings，93.73 秒。这些均为隔离 SQLite 测试，不代表真实工作库已验证。

**下一步：** 继续处理真实工作 SQLite 文件的 Windows ACL 访问问题；获得只读访问后先检查数据库版本、迁移状态和备份可用性，再决定是否执行迁移。Boot / recent / search 的 SQL 投影回归已覆盖。隔离 SQLite 测试不能替代真实库验收；PostgreSQL 集成测试继续作为可选兼容任务。

## 七、召回词机制评估（暂不开发）

当前诊断表明自然语言改写可能造成词面召回漏失，但现有 Glossary 不能承担搜索别名职责：`manage_triggers` 绑定的是记忆库中已经存在的触发词，用于 `read_memory` 展示关联链接。复用它存查询改写会改变既有功能语义并污染关联结果。

如后续真实任务评估证明确有必要，候选方案为：

- `recall_terms` 挂在 `Memory` 版本上，而不是 `Node`。正文更新产生新版本时默认清空，避免旧版本词条未经核对自动继承。
- 使用简单文本字段保存少量人工确认的词项/短语；不引入新表、不引入 JSON 结构、不把整句问题写进去。
- `SearchDocument` 是派生索引：重建时从当前活动 `Memory.recall_terms` 读取，并合并到现有 FTS `search_terms`；不把召回词混入 `summary_content`，也不改变 Glossary。
- 更新入口应是独立、职责清晰的召回词写操作；变更需纳入现有 Changeset，并刷新该 Node 的所有相关 SearchDocument。是否新增 MCP 工具，待确认现有写入工具的调用契约后再定，不复用 `manage_triggers`。
- 当前不实施字段、迁移或 MCP 工具。先收集真实任务样本，评估漏召回、误召回和人工维护成本；未证明收益前保持现有 FTS 策略。

该方案属于 V3.2 精准召回的候选，不改变 V3.1 上下文交付范围。

## 八、关联文档

- [V3.1 上下文交付方案](./nocturne-v3.1-context-delivery.md)：产品决策、源码事实、技术约束和测试用例。
- [项目文档中心](./README.md)：项目文档索引。


### V3.1 合成召回评估（2026-11-18）

- 新增 `docs/project/v3.1-recall-evaluation.json`：15 个不含个人数据的合成任务，覆盖 SQLite 迁移、摘要检索、按需展开、Token 预算、Alias/Path、生命周期、版本摘要、namespace、正文优先、索引刷新、Boot、URI 直读、召回排序、重复检查和 L3 关联披露。
- 新增隔离 SQLite 自动化评估：`backend/tests/service/test_lifecycle_recall.py::test_v31_synthetic_recall_and_summary_token_efficiency`。
- 本轮结果：Recall@10 = 100%；MRR = 1.000；P@10 = 0.100（每个任务只有 1 个相关目标，结果列表最多 10 条）；正文约 30,692 字符（约 7,673 个估算 token），摘要约 444 字符（约 111 个估算 token），字符/4 代理估算减少 98.6%。
- 重要限制：这是刻意构造的合成检索集，唯一关键词和摘要高度匹配，不能代表真实记忆的 Recall/Precision；Token 数使用字符数/4 粗估，不是模型 tokenizer 的精确值，也不证明真实会话节省 98.6%。后续需要在本地工作库可读后，构建脱敏真实任务集。
- 完整测试复测：208 passed，0 failed，25 warnings，66.25 秒；pytest 默认缓存插件正常启用。


### 本轮复核与评估修正（2026-11-18）

- 发现旧版合成评估存在方法问题：每次只创建一条记忆就立即搜索，未在完整候选集合中竞争，容易高估召回效果。已修正为先写入全部 15 条记忆，再运行全部 15 个查询。
- 修正后仍为 Recall@10 = 100%、MRR = 1.000、P@10 = 0.100；当前数据仍是关键词与摘要高度匹配的合成集，不能据此判断真实语义召回。
- 正文约 7,673 个字符/4 代理 Token，摘要约 111 个代理 Token，长度差异约 98.6%；这只是摘要与正文的长度比，不是实际上下文节省率。
- 修复 `scripts/run-tests.bat` 参数行为：无测试路径时默认跑全量 `backend/tests`；传入现存测试文件/目录时只执行指定目标。已实测指定迁移测试文件仅运行 1 项并通过。
- 最新全量复测：`208 passed`、`0 failed`、`25 warnings`；直接 pytest 76.21 秒，Windows BAT 端到端 74.73 秒。
- 当前未访问真实工作库、未执行真实库迁移、未提交 Git。


### 搜索宽松回退验证（2026-11-18）

- 追加 5 个不直接使用标题/URI 标识符的任务式查询。原 SQLite 查询将所有 jieba token 以 AND 连接，5/5 均无结果，暴露出自然语言查询夹带额外词语时过于严格的问题。
- 已调整 SQLite 搜索：先执行原 AND 精确查询；只有零结果时，才使用 OR 放宽候选，并继续按 FTS5 BM25、priority、path 排序。正常严格查询不变，避免无条件扩大结果集。
- 修正后 5/5 查询均命中目标，目标排名均为第 1；自动化评估加入 hard Recall@10 不低于 60% 的回归门槛。
- 此改动只针对当前实际使用的 SQLite 分支。PostgreSQL 分支尚未同步此回退策略，也未进行实库验证。
- 全量后端测试：208 passed、0 failed、25 warnings，78.28 秒。


### Boot 预算边界与按需展开回归（2026-11-18）

- 复核 `generate_boot_memory_view()`：配置的 `boot_summary_token_budget` 只约束 L1 摘要文本，不约束 URI、Memory ID、Priority、Lifecycle、Disclosure、展开指引、固定说明和 recent 元数据。因此不能把该值描述为整个 `system://boot` 的总 Token 上限。
- recent 区块只输出 URI、Priority、Disclosure、时间等索引元数据，不读取 Memory 正文；本轮没有扩大其披露范围。
- 新增两个隔离 SQLite 回归测试：一是摘要超预算时只截断摘要，Boot 不出现正文标记、不调用全文读取函数，而显式 `fetch_and_format_memory(uri)` 仍返回正文；二是摘要缺失时返回 `MISSING`，不展开正文。
- 新增测试同时验证摘要预算为 12 estimated tokens 时摘要用量达到 12，但整个 Boot 输出长度仍大于 36 UTF-8 字节，明确锁定“摘要预算≠整个 Boot 输出预算”的边界。
- 专项测试：`backend/tests/service/test_lifecycle_recall.py`，7 passed，1 warning，11.96 秒。
- 本轮未修改生产代码；先用测试固定现有披露契约，避免为追求一个总量数字而误截断必要 URI/元数据。后续若要限制整个 Boot 输出，应另行设计总输出预算并保留最小可用入口信息，不与摘要预算混为一谈。


- 加入 Boot 渐进披露回归后，最新完整后端测试：`210 passed`、`0 failed`、`25 warnings`，81.60 秒；`git diff --check` 退出码 0。


### AND 有结果但漏召回：干扰候选实验（2026-11-18）

- 新增隔离 SQLite 合成实验：29 条记忆（1 条目标、12 条包含全部查询词但语义无关的 hard negatives、15 条无关背景记忆），查询为 `postgres migration isolation guard`。
- 严格 AND：12 条候选，目标未召回，Recall@50=0%，Precision@50=0%。这说明“AND 有结果”不代表结果相关，也可能完全漏掉只包含部分关键术语的目标。
- OR：13 条候选，目标召回但排第 13；Recall@50=100%，Precision@50=7.69%。在 Top 10 交付时仍然漏掉目标。
- 结论：不能把 OR 作为“AND 有结果但数量不足”时的直接补充，也不能仅凭 BM25 词项匹配度把 OR 结果塞进 Top 10。该实验中的 12 条 hard negatives 对所有查询词都有词面命中，BM25 将它们排在目标之前。
- 本轮不修改生产搜索策略。现有“AND 零结果才 OR 回退”保持不变，避免无证据扩大召回造成精确率进一步下降。后续需要评估可解释的分层候选交付（保留 AND 与 partial-match 两组及命中词信息），由上层按任务决定是否展开，而不是后端伪装成已完成语义排序。
- 专项测试：`test_partial_match_fallback_precision_experiment`，1 passed，1 warning，3.04 秒。

- 最新全量复测（包含 AND/OR hard-negative 实验）：211 passed，0 failed，25 warnings，82.89 秒；`git diff --check` 通过。


### 可选分层候选交付（2026-11-18）

- 在现有 `search_memory` / `SearchIndexer.search()` 上增加可选参数 `include_partial`，默认 `false`，不新增 MCP 工具、数据库表或独立服务。
- 默认搜索路径完全保持原行为：严格 AND 优先；仅 AND 零结果时才 OR 回退；默认结果不增加 `match_type` 等字段，也不会额外执行 OR 查询。
- 显式开启 `include_partial=true` 且 AND 有结果时，额外查询 OR 候选；排除已经进入严格结果的 Node，再最多追加 5 条 partial 候选。严格结果始终排在前面，不会被 partial 候选挤掉。
- 可选结果标注 `match_type=strict/partial`。Partial 结果提供 `matched_terms` 和 `match_coverage`，用于解释词面命中情况；它们不是语义相关性评分，不能据此自动展开正文。
- AND 零结果触发原有 OR 回退时，开启诊断模式会将回退结果标记为 partial，避免误报为严格匹配。PostgreSQL 分支当前未实现该可选分层能力；当前部署为 SQLite。
- 新增回归测试验证：默认结果结构和排序不变、partial 结果仅在显式开启时出现、严格结果不被挤占、命中词和覆盖率标记正确。
- 专项测试：`test_lifecycle_recall.py`，9 passed。最新全量后端测试：212 passed，0 failed，25 warnings，93.84 秒。
- 当前仍未访问真实工作 SQLite 库、未执行真实库迁移、未提交 Git。

### 搜索结果避免加载完整正文（2026-11-18）

- 检查发现 `SearchIndexer.search()` 虽然只查 `SearchDocument`，没有读取 `Memory.content`，但仍把 `SearchDocument.content` 整段取入 Python，再由 `_format_search_snippet()` 截取片段。这仍然属于隐式全文加载。
- SQLite 改为使用 FTS5 `snippet()` 在数据库侧生成命中片段；没有命中正文（例如只命中摘要）时，仅回退读取正文前 240 个字符。PostgreSQL 分支改用 `ts_headline()` 生成有限片段。查询结果不再选择完整 `sd.content` 列。
- Partial 诊断的命中词覆盖率改为基于已交付片段计算，不再为了计算覆盖率把全文正文取回。该指标仍是片段内词面覆盖率，不代表语义相关性。
- 新增 SQL 监听回归：使用约 70KB 正文，查询位于正文尾部的标记，验证返回片段包含命中词且长度受限，同时 SQL 不投影完整 `sd.content`。搜索专项 5 passed；全量后端测试 216 passed、0 failed、25 warnings，85.59 秒。均为隔离 SQLite 测试。
- Boot 摘要查询 `get_memory_summary_by_path()` 已确认显式投影摘要和元数据字段，不读取正文；recent 查询此前已修复为显式元数据投影。
- 当前仍未访问真实工作库、未执行真实库迁移、未提交 Git。尝试对工作库文件授予当前执行账户只读权限时，`icacls` 返回拒绝访问（退出码 5），ACL 修改未成功；未尝试提权或取得所有权。


### 最新回归与真实库权限复查（2026-11-18）

- 复查 `system://boot`：核心记忆使用 `get_memory_summary_by_path()` 显式投影 L0/L1 字段；recent 使用已修复的元数据投影；访问日志仅记录 Node 访问，不展开正文。
- 复查 `SearchIndexer.search()`：SQLite 查询只返回摘要和数据库侧生成的有限 snippet，不选择完整 `SearchDocument.content`；已有 SQL 监听测试覆盖长正文尾部命中。
- 专项回归：56 passed，1 warning，35.08 秒。全量后端回归：216 passed，0 failed，25 warnings，92.69 秒；`git diff --check` 通过。全部使用隔离 SQLite。
- 真实工作库 `E:\\myPrivateSpace\\记忆系统数据库\\work\\work-memory.db` 仍无法打开。尝试对该文件授予当前执行账户只读权限，`icacls` 返回拒绝访问（退出码 5），未成功修改 ACL；没有读取、备份或迁移真实数据。
- 未提交 Git。


### 正式工作库 Migration 016 验收（2026-11-18）

- 已确认 `config.json` 实际指向 SQLite 工作库 `E:\myPrivateSpace\记忆系统数据库\work\work-memory.db`；本轮不做 PostgreSQL 迁移。
- 迁移前使用 SQLite Online Backup API 生成完整备份：`E:\myPrivateSpace\记忆系统数据库\work\work-memory.db.20261118_185546.13632-8a27c4f3.bak`。备份文件独立执行 `PRAGMA integrity_check`，结果为 `ok`。
- 先从正式库在线备份出隔离副本，使用项目实际 `db.migrations.runner.run_migrations()` 执行迁移；副本成功记录 `016_add_memory_summary.py`，字段和 FTS5 表结构正确，数据行数保持不变，完整性检查通过。
- 正式工作库迁移前检查确认已应用 15 个迁移，唯一待执行项为 `016_add_memory_summary.py`；随后通过同一项目迁移入口完成正式迁移。
- 正式库验收：`schema_migrations` 已记录 016；`memories` 含 `summary_content`、`summary_updated_at`；`search_documents` 含 `summary_content`；FTS5 重建完成；行数为 memories 105、search_documents 48、FTS5 48；`PRAGMA integrity_check=ok`。
- 迁移只增加可空摘要字段并重建派生全文索引，没有写入虚构摘要、删除记忆或改变记忆正文。当前摘要为空是预期状态，后续由 AI 根据正文按需生成。
- 正式库迁移完成；下一步在真实库上验证应用层搜索、摘要写入/读取与 Boot 交付。全量 216 项测试此前通过，但属于隔离 SQLite 测试，不冒充真实库应用验收。
- 未提交 Git。


### 正式库应用层冒烟与全量回归（2026-11-18）

- 通过项目 `DatabaseManager` 连接正式工作库，实际调用 `SearchIndexer.search()`：返回结构包含 `summary`、`summary_status`、`expandable`、`snippet`、`aliases` 等预期字段；当前已有记录均返回 `MISSING`，未读取或伪造摘要。
- 实际调用 `GraphService.get_memory_summary_by_path()`，成功返回 Boot 所需的 L0/L1 元数据字段，摘要状态为 `MISSING`；该验证只读，没有改写真实记忆内容。
- 再次执行完整后端测试：216 passed、0 failed、25 warnings，91.91 秒；`git diff --check` 通过。测试仍是隔离 SQLite，正式库应用层冒烟单独记录，不混为一谈。
- 当前警告主要为 AnyIO 对 pytest 内部别名的弃用提示，以及测试启动时 API_TOKEN 未设置的提醒；不是测试失败。后续应为本机服务配置 API_TOKEN。
- 真实库迁移、备份、完整性检查和应用层只读冒烟均完成。摘要生成与写入链路尚未在真实数据上执行，避免未经核对就批量生成摘要。
- 未提交 Git。


### 正式库核心记忆摘要试点（2026-11-18）

- 从正式库 `config.json` 读取当前 Boot 入口：`core://agent`（Memory 39）和 `core://my_user`（Memory 68）；两条记忆均为 active，原来没有摘要。
- 已基于两条正文分别生成简短 L1 摘要，并通过项目 `GraphService.update_memory_summary(memory_id, summary)` 写入正式 SQLite 工作库。只处理这 2 条 Boot 核心记忆，没有批量改写其余 44 条活动记忆。
- 写入后复查：两条摘要状态均为 `VALID`，长度分别为 113、94 字符；`get_memory_summary_by_path()` 可按 Boot URI 读取正确摘要。
- 正式库搜索验证：关键词“当前明确任务”命中 Memory 39，关键词“制造业工业软件”命中 Memory 68；搜索结果携带 `VALID` 摘要。
- 正式库 `PRAGMA integrity_check=ok`；活动记忆摘要数为 2。没有修改正文、版本、生命周期或关系。
- 另外在迁移前备份副本上完成摘要写入→SearchDocument 同步→FTS5 命中→Path 读取→SearchIndexer 召回→清空摘要的完整链路；清空后索引同步移除。该 E2E 试验未污染正式库。
- 针对摘要、搜索和 Boot 的专项测试：17 passed、0 failed，20.76 秒；`test_search_indexer.py`、`test_memory_summary_migration.py`、`test_lifecycle_recall.py` 全部通过。
- 正式库已有 2 条真实摘要；其余活动记忆继续按需生成，不进行无差别批量摘要。未提交 Git。

### 正式工作库 Boot 实际交付测量（2026-11-18）

- 通过项目实际 DatabaseManager、PresetService.get_boot_uris() 和 generate_boot_memory_view() 只读执行正式工作库 Boot；连接目标确认为 SQLite 工作库，namespace 为空。
- 当前生效 Boot URI 为 core://my_user（Memory 68）和 core://agent（Memory 39），两条摘要均为 VALID；加载结果为 2/2，未读取正文。
- 实际输出 1,970 字符、2,784 UTF-8 字节，按项目估算口径约 928 tokens；其中摘要预算使用 204/2000 estimated tokens。总输出包含固定说明、URI/优先级/生命周期/Disclosure、展开指引，以及最近 5 条记忆的索引元数据。
- 这次测量明确：boot_summary_token_budget 只限制 L1 摘要，不能代表整个 Boot 的 Token 上限；当前摘要本身只占总输出的一部分。928 tokens 不是模型 tokenizer 的精确计费值，而是项目统一的 UTF-8/3 估算口径。
- 本次仅执行读取和输出测量，没有修改正式数据。
- 下一步优化方向：评估 recent 区块的 Disclosure 是否需要在 Boot 常驻，保留 URI 入口和按需展开能力；若缩减，必须以测试验证不会损失记忆定位能力。暂不引入复杂的全局 Token 账本。

### Boot 输出结构拆分与摘要覆盖率（2026-11-18）

- 对正式 Boot 输出按区块拆分：核心记忆区 1,416 UTF-8 字节/约 472 estimated tokens；最近记忆区 1,340 字节/约 447 estimated tokens；合计 2,784 字节/约 928 estimated tokens。两区块分别约占总输出 51% 和 49%。
- 核心区中实际 L1 摘要只使用 204 estimated tokens；其余约 268 tokens 是 URI、优先级、生命周期、Disclosure、展开指引和固定说明。recent 区块本身约 447 tokens，是当前最值得评估的固定上下文开销。
- 正式库当前 46 条非 deprecated Memory 中，2 条已有摘要；38 条 lifecycle=active、8 条 lifecycle=unspecified。其余记忆不因缺少摘要就自动生成，先按召回需求和稳定性排序。
- 产品判断：先在隔离测试中比较 recent 保留完整 Disclosure、缩短 Disclosure、仅保留 URI/priority/time 三种输出；用任务定位成功率和 Token 估算共同决定，不直接削减正式 Boot 的信息。

### Boot 最近记忆区精简实验与实现（2026-11-18）

- 将 Boot 与主动访问 system://recent 的展示职责分离：generate_recent_memories_view 新增 include_disclosure 参数，默认 True，保持原 system://recent 行为；Boot 调用时传 False，仅保留最近记忆 URI、Priority 和修改时间。
- 正式工作库实测：最近 5 条详细视图 1,368 UTF-8 字节/约 456 estimated tokens；精简视图 569 字节/约 190 estimated tokens，减少 799 字节/约 267 estimated tokens（约 58.6%）。
- 修改后正式 Boot 实际输出从此前 2,784 字节/约 928 estimated tokens 降至 1,985 字节/约 662 estimated tokens，减少约 28.7%。核心摘要、Disclosure、URI 和展开入口保持不变；recent 仍保留 5 条 URI/priority/time 定位信息。
- 验证 system://recent 仍能显示完整 Disclosure；Boot 不再重复输出 recent Disclosure。没有修改正式数据库数据。
- 新增回归测试 test_boot_recent_index_is_compact_but_recent_view_keeps_disclosure；MCP 工具与 namespace 专项测试 52 passed。

## V3.2 真实召回评估与中文部分匹配优化（2026-11-18）

本轮使用正式工作库 `work-memory.db` 做只读检索，未修改任何记忆或索引。数据库快照：47 个节点、48 条路径、48 条搜索索引记录、1 个 namespace、0 条 obsolete、2 条带摘要的索引记录、2 组多路径别名。详细查询和候选标注见 `v3.2-recall-baseline.json`。

### Ground Truth 校正

- 评估集共 18 条查询：17 条正向查询、1 条负向查询。
- R09“摘要与渐进披露”原先误标为 `core://agent/dsh/context-output`。核对正文后确认它只描述 DSH 大输出工具，不是 Nocturne 摘要/渐进披露方案；正式库没有对应记忆，因此改为负向查询，期望返回空结果。
- 校正后原始基线：正向目标命中 16/17（94.12%），MRR 0.9020。R09 不纳入正向 Recall/MRR，单独统计误召回。
- 相关性候选标签采用单人保守初标，尚未进行第二位标注者复核；不宣称全库 Precision/Recall。

### 中文短语别名与降级策略

SQLite 原始 AND 查询无命中时，先尝试人工确认的短语别名（仍使用 AND）。若别名 AND 命中，则直接使用该精确候选，不再混入原始 OR 弱匹配。当前规则：

- `找回来` / `找回任务` → `恢复任务`
- `下一个会话要留下什么` / `切换会话前` → `交接保留`
- `恢复之前开发进度` → `恢复任务`
- `自动化测试用例` → `用例设计`

原始查询不被改写；没有全局停用词过滤。PostgreSQL 路径不变。

若原始 AND 和短语别名 AND 均无命中，才走 SQLite OR 降级：

- `MIN_PARTIAL_MATCH_COVERAGE = 0.26`，过滤低覆盖候选。
- `MAX_PARTIAL_FALLBACK_RESULTS = 3`，最多返回 3 条 OR 降级候选。
- 覆盖率按查询分词中实际出现在路径、URI、摘要、命中片段或 Disclosure 的词数计算。
- 原始 AND 和人工短语别名 AND 不受覆盖率及数量上限影响。

### 正式工作库只读复测

| 指标 | 覆盖率 0.26、OR 最多 10 条 | 覆盖率 0.26、OR 最多 3 条 |
|---|---:|---:|
| 正向目标命中 | 17/17 | 17/17 |
| 正向 MRR | 0.9314 | 0.9314 |
| Macro P@returned（非空查询） | 0.7294 | 0.8235 |
| Micro P@returned | 0.4375 | 0.7353 |
| 实际返回候选数 | 64 | 34 |
| R09 负向误召回 | 0 | 0 |

候选返回量再减少 46.9%，Macro P@returned 提升 9.4 个百分点，Micro P@returned 提升 29.8 个百分点；17 条正向目标命中和 MRR 不变。H08 目标仍在第 3 位，H03 目标在第 2 位。固定分母 Macro P@10 为 0.1389；因多数查询返回数少于 10，不能用它替代 P@returned。相关性标签为单人初标，指标仅代表当前小样本诊断集。

代码：`backend/db/search.py`、`backend/db/search_terms.py`；回归测试：`backend/tests/unit/test_search_terms.py`、`backend/tests/service/test_search_indexer.py`。全量测试 **221 passed / 0 failed**，25 条既有警告；`git diff --check` 通过。正式工作库只读，没有重建或修改索引。未提交 Git，也未重启或部署服务。

### 改写查询集诊断（非独立 Holdout）

另取 10 条自然语言改写查询做探索性诊断：新增别名前目标 Top10 命中 **7/10**、MRR **0.6000**；根据 X02“恢复之前开发进度”、X03“切换会话前交代信息”、X07“自动化测试用例设计”三条漏召回补充人工短语别名后，复测达到 **10/10**、MRR **0.8500**。因为该集合参与了规则调试，不再称为独立 Holdout。详细排名见 `v3.2-paraphrase-evaluation.json`。该集仅用于目标召回验证，不计算 Precision；样本少，不能当作生产流量表现。

### 独立改写查询诊断（规则冻结后）

另建 10 条未参与别名设计的查询，在规则冻结后只测不调：目标 Top10 命中 **5/10**，Recall@10 **50%**，MRR **0.3833**（仅命中样本的条件 MRR 为 0.7667）。漏召回集中在任务接续、Mock 耗尽、简洁回复偏好、记忆自动清理、配置实际加载验证五类表达。结果见 `v3.2-independent-evaluation.json`。这是小样本诊断，不代表生产流量；本轮不基于该集合继续调参，以保留它作为当前版本的独立检查集。

### 五类漏召回补充规则（2026-11-18）

根据目标记忆正文增加 5 条人工短语别名：开发任务接续→恢复任务、Mock 返回值不够→期望耗尽、回答尽量短→回复简洁精准、记忆不应自动清理→自动删除、配置确实加载→配置变更/同源解析。只在原始严格 AND 无命中时尝试，未命中时再按现有 OR 降级规则处理。

正式工作库只读验证这 5 条原始漏召回查询，目标均进入 Top10（5/5），MRR=0.9000；开发任务接续目标第 2，其余目标第 1。该结果属于规则开发验证，不是独立评估。

此前 `v3.2-independent-evaluation.json` 中 I01 与新增短语规则发生查询短语重合，因此该文件的 5/10 仅作为优化前历史诊断，不再作为当前版本独立指标。另建并冻结 `v3.2-fresh-paraphrase-diagnostic.json`：10 条新查询目标命中 3/10，MRR=0.2333（命中样本条件 MRR=0.7778）。结果说明：当前短语别名只解决了明确表达映射，跨表达泛化仍弱；不应继续靠堆同义词表冒充语义检索。

### Embedding 本地运行条件检查（只读）

本机已有 `onnxruntime` 与 `sqlite-vec` Python 包，但未安装 `sentence-transformers`、`fastembed`、PyTorch。Hugging Face 缓存中的 ModernBERT 只有 tokenizer/config 文件、架构为 `ModernBertForMaskedLM`，没有模型权重，不能直接作为句向量模型；另一个 kompress-v2 缓存目录为空。因此当前没有可直接验证的本地 embedding 模型。暂不为个人系统引入新依赖或下载模型。若下一轮进入语义召回 PoC，优先选择体积较小、中文效果明确、支持 ONNX CPU 推理的句向量模型，并先在隔离副本上比较 Recall/Precision、延迟和模型体积，再决定是否写入正式索引。

### 轻量语义模型候选（资料预研，不引入依赖）

结合本库中文为主、夹杂英文技术名词的特点，先保留两个 PoC 候选：

| 候选 | 适配点 | 成本/注意事项 |
|---|---|---|
| `intfloat/multilingual-e5-small` | 384 维，模型卡标注支持 94 种语言；适合中文与英文混合记忆。 | 检索时必须按规范分别添加 `query: ` 与 `passage: ` 前缀；模型卡说明长文本最多截断到 512 tokens。 |
| `BAAI/bge-small-zh-v1.5` | 中文专用，512 维；官方 C-MTEB 表中 Retrieval 分数为 61.77。 | 对英文技术内容的跨语言适配需用本项目样本验证；C-MTEB 分数不能直接等同于 Nocturne 的召回效果。 |

资料来源：E5 模型卡说明 94 种语言、384 维及 query/passage 前缀要求；BGE 官方模型卡给出 C-MTEB 检索分数及 MIT 许可。当前只做候选筛选，不下载模型、不安装依赖、不接入正式检索。

**PoC 进入门槛**：先在隔离 SQLite 副本里对同一批 query/记忆正文做离线向量计算；只把向量召回作为 FTS5 的补充候选，不替换现有严格检索；按 Recall@10、Precision@10、MRR、误召回数量、单次检索延迟、模型磁盘占用比较。只有在新冻结诊断集上稳定优于当前 FTS 基线，且收益足以抵消模型运行成本，才考虑进入 V3.2 正式实现。



## NVIDIA Embedding API 接入预备（2026-11-18）

- 本地配置使用 `config.json` 的 `embedding.api_key`，不要求环境变量；密钥不写入代码。
- 新增 `backend/embedding.py`：通过现有 `httpx` 调用 OpenAI-compatible Embeddings endpoint，支持批量输入、query/passage input_type、响应顺序校正、向量维度校验和错误处理。
- Settings GET 对 `embedding.api_key` 做脱敏，只返回 `has_api_key`，不向浏览器返回密钥。
- 已用配置中的 Key 对 NVIDIA API 发起合成文本请求：成功返回 2048 维向量；query 与 passage 两种 input_type 均通过。
- 合成样例“把之前的开发任务接着做”与“恢复之前的开发任务”余弦相似度 0.510660；与无关句子“今天的天气怎么样”为 0.110764。该结果仅证明接口和向量计算链路可用，不代表真实语料检索效果。
- 新增 `scripts/experiments/nvidia_embedding_smoke.py`，仅使用合成文本和内存 SQLite，验证 NVIDIA API、2048 维向量及 sqlite-vec TopK 检索，不访问记忆数据库。
- sqlite-vec 0.1.9 已在内存 SQLite 中验证可加载；需要先显式启用 SQLite extension loading，再加载扩展。向量 TopK 能将语义改写目标排在无关句子之前。
- 新增 4 项单元测试，全部通过。首次使用项目全局 pytest fixture 时遇到 Windows 临时 SQLite 路径问题；通过 `--confcutdir=backend/tests/unit` 隔离执行后 4/4 通过。
- 暂不启用 `embedding.enabled`，不写入向量表、不改正式数据库、不将真实记忆内容发送给 NVIDIA。下一阶段需先在隔离数据库副本上评估；真实个人记忆上传第三方 API 前需明确授权。
- 本轮完整回归：`scripts\run-tests.bat -q --basetemp=.tmp/pytest-final-nvidia`，225 passed、0 failed；`git diff --check` 通过。Settings GET 脱敏行为已单独验证。


## NVIDIA Embedding 真实语料召回评估（2026-11-18）

用户已明确授权将 Nocturne 真实记忆文本发送给 NVIDIA Embedding API。本轮按授权执行：

- 源库 `E:\myPrivateSpace\记忆系统数据库\work\work-memory.db` 全程只读；仅选取非 obsolete、非 deprecated 的 48 条 `search_documents`，包含 URI、Path、摘要、检索词和正文，总计约 84,393 字符。没有把访问日志、账号凭据或其他无关表发送给 API。
- 10 条查询来自已冻结的 `v3.2-independent-evaluation.json`，不根据这组查询调别名或修改正式检索代码。
- 48 条记忆文本以 `passage`、10 条查询以 `query` 调用 `nvidia/nemotron-3-embed-1b`；模型输出 2048 维向量。API 请求完成约 49.71 秒。
- 向量写入 `.tmp/nvidia_embedding_real_memory_eval.db` 的隔离 sqlite-vec 索引；评估明细写入 `.tmp/nvidia_embedding_real_memory_eval.json`。新增脚本 `scripts/experiments/nvidia_embedding_real_memory_eval.py`，并增加本地 embedding cache，避免相同文本重复请求产生额外费用。
- 在同一批冻结查询上，使用当前 SearchIndexer 的 SQLite FTS5 规则只读复现词法排序，并与向量 Top10 比较。结果：

| 方案 | Recall@1 | Recall@3 | Recall@10 | MRR |
|---|---:|---:|---:|---:|
| 当前 FTS5（同轮复测） | 70% | 100% | 100% | 0.8333 |
| NVIDIA 向量召回 | 80% | 100% | 100% | 0.8833 |
| FTS5 + 向量 RRF（k=60） | 80% | 100% | 100% | 0.9000 |

- RRF 的 k=10/20/40/60/100 在当前小样本上均得到 MRR 0.9000，没有证据支持继续调参。Hybrid 比 FTS5 的 MRR 高 0.0667，比纯向量高 0.0167；Top3 已全部命中，因此现阶段收益主要体现在前几位排序，不是 Top10 召回率提升。
- 历史 `v3.2-independent-evaluation.json` 中记录的 5/10、MRR 0.3833 是更早版本的历史快照；本轮代码已包含后续别名和部分匹配规则，直接复现当前 FTS5 后为 10/10、MRR 0.8333。两组结果不可混为同一版本基线。
- 由于只有 10 条查询、48 条记忆，且候选未逐条人工标注，不能计算 Precision，也不能宣称生产效果已证明。当前结论：NVIDIA Embedding 值得保留为混合召回候选，但暂不启用线上向量检索；先扩大冻结 Holdout，再评估误召回、延迟、API 成本和稳定性。
- 真实记忆内容已按授权发送给 NVIDIA；源数据库只读，未改正式数据、索引或配置，`embedding.enabled` 仍为 false。未提交 Git，未重启或部署服务。 全量测试再次执行：225 passed、0 failed、25 warnings（75.93 秒）；`git diff --check` 通过。Embedding 本地缓存通过 mock 自测，重复文本不会重复调用 API。


### 第二组冻结 Holdout：新鲜改写查询（2026-11-18）

继续使用此前已经冻结、未参与规则设计的 `v3.2-fresh-paraphrase-diagnostic.json`，仅将 10 条查询发送给 NVIDIA；48 条文档向量直接复用本地隔离索引，没有再次上传正文。没有根据这组结果调参。

| 方案 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
|---|---:|---:|---:|---:|---:|
| 当前 FTS5 | 20% | 30% | 30% | 30% | 0.2333 |
| NVIDIA 向量召回 | 80% | 80% | 90% | 90% | 0.8250 |
| FTS5 + 向量 RRF（k=60） | 50% | 60% | 80% | 90% | 0.6167 |

本轮结果很明确：这组真正未参与规则调试的新查询上，向量召回明显优于当前 FTS5；但简单 RRF 融合反而拉低了向量排序质量，说明不能想当然地把 FTS 和向量分数混在一起。当前不调整融合权重，避免污染这组 Holdout；下一步应另建新的开发集研究“向量优先 + 词法补充”的融合策略，再用全新 Holdout 验证。

详细结果：`.tmp/nvidia_embedding_fresh_holdout_eval.json`；可复跑脚本：`scripts/experiments/nvidia_embedding_fresh_holdout_eval.py`。本轮只请求 10 条 query embedding，复用既有文档向量；评估耗时约 7.08 秒。Precision 暂不计算，因为候选没有逐条人工标注。样本量仍只有 10 条，不能直接外推到生产流量。


### 负向查询与拒绝召回诊断（2026-11-19）

本轮补充 20 条冻结的合成负向查询（天气、旅行、菜谱、电影、运动、税务、翻译等明显不属于当前 48 条记忆库主题的请求）。仅将 20 条查询文本发送给 NVIDIA；复用既有 48 条文档向量，不再次上传真实记忆正文。

- 20 条负向查询全部会从向量索引返回一个 Top1 记忆候选，说明“向量 TopK 总能返回结果”，不能等同于“用户请求一定有相关记忆”。
- 10 条正向基准查询的目标文档 L2 距离范围为 1.0298～1.2757；20 条负向查询的最近邻 L2 距离范围为 1.2693～1.3719，存在明显重叠。
- 阈值诊断：在修正文档字段分隔符并重建向量后复测，正向目标距离范围为 1.0304～1.2748，负向最近邻距离范围为 1.2687～1.3729；阈值 1.269 时正向接受 9/10、负向误接受 1/20（5%），阈值 1.275 时正向接受 10/10、负向仍误接受 1/20（5%）。两类距离直接重叠，拒绝阈值无法同时保证正向召回与负向拒绝。
- 结论：目前没有足够稳健的单一 L2 阈值可用于线上自动拒绝召回。1.269 与最近负样本 1.2693 的间隔只有约 0.0003，样本规模也只有 10 正向 + 20 合成负向，不能将其写入正式配置。
- 这批负向查询是合成 OOD 诊断，不是人工标注的真实用户误召回数据；不据此计算 Precision。

### 检索融合策略复核（2026-11-19）

离线复算两组冻结正向集：

- 修正文档字段分隔符并重建向量后，简单 RRF(k=60) 在新鲜改写集 MRR 为 0.6143，低于纯向量 0.8200。
- “向量前 N 条优先，FTS 只补充剩余候选”策略在 N=5、7 时与纯向量持平（Recall@10 90%、MRR 0.8200）；N=3 时 Recall@10 从 90% 降至 80%。
- 因此当前最稳妥的工程方向不是混合重排，而是：**向量检索作为语义召回主通道；FTS5 保留为独立词法通道/Embedding 不可用时的降级通道；精确 URI/Path 仍走原有精确入口；不对两个通道的原始距离和 BM25 分数做未经校准的混合排序。**
- 尚未改正式 `SearchService`、未开启 `embedding.enabled`。正式接入前仍需扩大正负样本、人工标注候选相关性，并评估 API 延迟、费用、失败降级与增量向量同步。

新增文件：
- `docs/project/nvidia-embedding-negative-query-diagnostic.json`：冻结负向查询集。
- `scripts/experiments/nvidia_embedding_negative_query_eval.py`：负向查询距离和拒绝阈值诊断。
- `scripts/experiments/nvidia_embedding_strategy_eval.py`：仅使用已有报告离线比较检索融合策略，不调用 API。
- `.tmp/nvidia_embedding_negative_query_eval.json`、`.tmp/nvidia_embedding_strategy_eval.json`：实验结果。


### 独立向量索引增量同步 PoC（2026-11-19）

新增 `scripts/experiments/nvidia_embedding_incremental_sync.py`，在独立 `.tmp/nvidia_embedding_incremental.db` 中验证增量同步机制：

- 以 URI 作为稳定文档键，以规范化输入文本 SHA-256 识别变化。
- 新增或正文/摘要/检索词变化时才重新生成 passage embedding；未变化文档不调用 API。
- 源库始终只读；向量和 URI 元数据只写入隔离索引。
- 先完成所有待更新向量生成，再开启 SQLite 写事务；API 失败不会先删掉旧向量。
- 处理新增、变更、源端删除三种差异；每次同步校验元数据行数与向量行数一致。

实测：首次同步 48 条文档，48 条元数据与 48 条向量一致；第二次同步 0 条新增/变更、48 条未变化，耗时约 0.06 秒，未触发 Embedding API。使用已缓存的冻结查询向量对隔离增量索引执行 TopK，排序与此前评估报告一致。

该脚本仍是 PoC，不连接线上 SearchService，不修改正式数据库。已完成隔离故障注入：初始插入 2 条成功；随后更新 1 条、删除 1 条、新增 1 条后索引仍为 2/2 一致；模拟 Embedding API 失败时，旧索引 URI 与内容哈希完全不变（未开始数据库写事务）。故障注入使用临时 SQLite 和 mock 向量，未调用真实 API、未改源库。


### 增量索引可靠性加固与评估输入修正（2026-11-19）

本轮代码复核发现两个实验脚本问题，并已修正：

- 文档向量输入原先用字面量 `\\n` 连接字段，而不是实际换行符。已统一改为真实换行，字段边界更清晰；因此重新生成 48 条 passage 向量，并重跑两组正向评估和负向诊断，避免新旧输入格式混用。
- 全语料评估脚本在结果落盘后还访问不存在的 `baseline_fts` 字段，导致脚本最终退出失败。已移除这条陈旧日志输出；报告生成和脚本退出现已正常。
- 融合策略脚本引用了旧版报告结构中的 `fts5_current` / `vector_current`，当前报告已改为嵌套结构。已按当前 Holdout 报告格式重写，明确只评估有完整 FTS 与向量候选列表的新鲜 Holdout，不再伪造缺失的全语料 FTS 排名。

增量同步 PoC 加固：

- URI 为空或重复时，在调用 API 前直接失败，防止字典覆盖或唯一键冲突。
- 将 `memory_id` 变化也纳入增量更新条件，避免 URI 相同但底层记忆记录已替换时继续保留旧映射。
- 对 Embedding 数量、2048 维度、数值类型和 NaN/Infinity 做严格校验；所有向量通过校验后才开启目标库事务。
- 元数据/向量数量一致性校验前移到事务提交之前；校验失败回滚，避免把不完整索引提交到磁盘。
- 新增单元及隔离集成测试，覆盖换行格式、重复/空 URI、向量数量和维度、非有限数值，以及模拟 API 故障时旧索引不变。

复测结果：48 条真实记忆在隔离索引中重新生成 48 个 2048 维向量，元数据与向量均为 48 条；第二次同步 48 条全部未变化，耗时约 0.07 秒，没有触发 API。模拟 API 故障测试通过，旧 URI、哈希和向量数量保持不变。真实工作库仍只读，所有写入仍限定在 `.tmp` 隔离索引。

修正输入格式后的评估：全语料 10 条冻结查询向量 Recall@1 80%、Recall@3/5/10 均 100%、MRR 0.8833；新鲜 Holdout 10 条查询向量 Recall@10 90%、MRR 0.8200；RRF MRR 0.6143；向量优先 N=5/7 与纯向量持平，N=3 Recall@10 降至 80%。负向诊断 20 条中，阈值 1.269 已误接受 1 条（5%），进一步确认当前距离阈值不适合线上自动拒绝。

验证：增量同步专项测试 6 passed；Embedding 客户端 + 索引专项测试 9 passed。最终全量回归：`scripts\run-tests.bat -q --basetemp=.tmp/pytest-final-embedding-hardening`，231 passed、0 failed、25 warnings，耗时 79.74 秒；7 个实验脚本全部通过 py_compile；`git diff --check` exit 0（仅有既有 LF/CRLF 提示）。确认 `embedding.enabled=false`、API Key 仍配置但不输出；隔离向量索引 48/48；真实工作库只读可打开且 eligible 文档仍为 48 条。未提交 Git，未重启或部署服务。未开启 `embedding.enabled`，未修改正式 SearchService，未提交 Git，未重启或部署服务。


### NVIDIA Embedding 增量索引边界复核（2026-11-19）

- 复跑真实工作库只读同步：48 条文档，新增/更新 0、删除 0、未变化 48；元数据与向量均为 48，耗时约 0.09 秒。
- 补充隔离测试：URI 改名按旧 URI 删除 + 新 URI 重建处理；节点转为 obsolete 后从索引移除；deprecated memory 不进入索引。
- Embedding API 响应校验补强：拒绝 NaN/Infinity 和 bool，避免异常数值进入向量索引。
- 以上均为隔离实验/单元测试；真实工作库只读，正式 SearchService 未接入，embedding.enabled 仍保持关闭。


### 第二组独立语义检索诊断（2026-11-19）

- 新建并冻结 20 条合成自然语言查询，覆盖任务恢复、调试、设计、开发、测试、工具选择、环境核验、数据库和前端规则等不同记忆入口；查询并非用户真实日志，目标 URI 在检索前预先标注。
- 在 48 条真实记忆文档的只读语料上评估，文档向量复用本地缓存；仅新增调用 NVIDIA 生成 20 条 query embedding。
- FTS5：Recall@1 80%、Recall@3/5/10 100%，MRR 0.8917。纯向量：Recall@1 90%、Recall@3 95%、Recall@5/10 100%，MRR 0.9292。RRF(k=60)：Recall@1 95%、Recall@3/5/10 100%，MRR 0.9750。
- 这组结果支持继续研究轻量 RRF 融合，但不能据此宣布生产效果：样本为人工合成、目标单标签、语料仅 48 条，且未标注非目标候选，不能计算 Precision。尤其上一组 10 条新鲜诊断中，纯向量 MRR 0.8250，高于 RRF 的 0.6167；本组 RRF 领先，说明融合收益对查询集构成敏感，当前不能把 RRF 定为默认排序策略，也不能将两组不同构造方式的集合直接合并统计。
- 诊断集文件：`docs/project/v3.2-second-independent-synthetic-diagnostic.json`；结果仅写入 `.tmp/nvidia_embedding_second_independent_eval.json`。


### 本轮最终验证（2026-11-19）

- 全量测试：`scripts\run-tests.bat -q --basetemp=.tmp/pytest-final-nvidia-20case`，236 passed、0 failed、25 warnings，84.12 秒。
- Embedding 与增量同步专项：15 passed；实验脚本与 Embedding 模块 py_compile 通过；`git diff --check` 通过（仅有现存 LF/CRLF 提示）。
- 再次只读同步工作库：48/48 一致，0 新增/更新、0 删除，0.07 秒。
- 配置安全状态：NVIDIA provider 已配置且 API Key 存在；正式开关 `embedding.enabled=false`。未提交 Git，未重启/部署服务，未改真实工作库。


### 检索拒绝召回信号诊断（2026-11-19）

- 新增 `scripts/experiments/nvidia_embedding_abstention_eval.py`，复用冻结的 20 条正向/负向合成集与已缓存向量；源工作库只读，不调用 NVIDIA API。
- 20 条负向查询中，FTS5 仍有候选的为 10/20；向量 Top1 与 FTS 候选一致仅 1/20；向量 Top3/Top5 与 FTS 候选存在交集分别为 3/20、4/20。
- 正向集合中，FTS 与向量双路均命中目标：旧基准 10/10、第二组合成集 20/20，但新鲜改写集仅 3/10（FTS 3/10、向量 9/10）。因此“必须两路一致”会明显损害语义改写召回；只看 FTS 是否有候选又不能有效拒绝所有 OOD 查询。
- 结论：当前证据不足以形成稳定的自动拒绝规则。不能把 FTS/向量一致性设为硬门槛，也不能单靠向量距离阈值拒绝。生产接入必须保留“无把握时返回候选但标记低置信/提示补充条件”或由上层策略决定；置信标记本身仍需更多人工标注验证。
- 本轮不改 `SearchIndexer.search()`，不改变线上搜索行为；只完成独立诊断。


### 本轮验证结果（2026-11-19）

- 全量测试：236 passed，0 failed，25 warnings，83.14 秒。
- 实验脚本与 Embedding 模块共 10 个 Python 文件 `py_compile` 通过。
- `git diff --check` 通过；仅有仓库既存文件的 LF/CRLF 提示。
- 新增拒绝召回诊断脚本只读取真实工作库和已有隔离向量索引；未调用 NVIDIA API、未修改工作库、未修改正式搜索逻辑。
- 正式开关仍为 `embedding.enabled=false`；没有重启服务、部署或提交 Git。


### 向量增量索引版本兼容性加固（2026-11-19）

- 增量索引新增 `index_state`，记录 Embedding 模型名、向量维度和文档序列化版本。模型或文档格式变化时，先生成并校验全量新向量，再在同一事务中替换索引内容；不会把旧模型向量误判为未变化。
- 向量维度变化时明确拒绝原地修改，要求创建新的隔离索引，避免 sqlite-vec 虚拟表维度与数据不一致。
- 兼容没有 `index_state` 的旧实验索引：只要旧索引已有数据，就触发完整重建；空索引则正常首次构建。
- 文档向量输入增加 lifecycle 状态，保证 active/completed/unspecified 等状态变化也会改变内容哈希；obsolete 仍按原规则从索引中剔除。
- `backend/config.py` 中 Embedding 配置说明修正为 `config.json`，与实际密钥读取方式一致（密钥仍不输出、不返回给 Settings API）。
- 新增索引兼容性单元测试，覆盖模型变化、文档格式变化、维度变化、旧索引迁移和无变化增量路径。
- 专项测试 14 passed；全量测试 **242 passed / 0 failed**，25 条既有 warning；实验脚本编译通过；`git diff --check` 通过。
- 本轮没有执行真实工作库向量重建，没有调用 NVIDIA API，没有修改真实工作库；隔离索引 `.tmp/nvidia_embedding_incremental.db` 未被本轮写入。`embedding.enabled` 仍为 false，未重启、未部署、未提交 Git。


### VectorIndex 最小模块与隔离性能验证（2026-11-19）

- 新增 `backend/vector_index.py`，独立封装 sqlite-vec 的初始化/关闭、模型与维度兼容校验、批量 upsert、按 URI 删除、TopK 查询、namespace/domain 元数据过滤和健康检查。它不依赖 `SearchIndexer`，暂不接入正式搜索。
- 索引元数据包含 memory_id、URI、内容哈希、namespace、domain、path、lifecycle_status；向量与元数据写入使用同一事务，输入向量先完成维度/数值校验。
- 特别修复 TopK 过滤陷阱：sqlite-vec 的 `k` 先截断候选，普通元数据过滤后执行会漏掉较远但符合 namespace/domain 的结果。当前实现按需逐步扩大候选集，直到过滤后满足 TopK 或遍历完整索引；回归测试覆盖“最近邻不符合过滤条件、第二近邻符合”的情况。
- 新增 `backend/tests/unit/test_vector_index.py`，覆盖初始化、检索、过滤、upsert 覆盖、删除、健康检查、异常向量、模型/维度不匹配和未初始化访问。
- 新增 `scripts/experiments/nvidia_vector_index_benchmark.py`，从既有隔离实验向量库读取 48 条向量，写入新的独立 benchmark 库；没有调用 NVIDIA API，也没有写入源工作库或正式库。
- 48 条、2048维的隔离基准：索引文件 8.066 MiB；初始化及建表约 0.046 秒；批量写入约 0.080 秒；30 次查询中位数 8.103 ms、P95 8.844 ms；Top1 自匹配通过；48 条元数据与48条向量一致。该结果仅是当前 48 条语料的小规模基准，不能外推为大规模性能结论。
- 专项测试 6 passed；全量测试 **248 passed / 0 failed**，25 条既有 warning；新增模块/测试/基准脚本编译通过；`git diff --check` 通过。
- 当前 `VectorIndex` 是可复用的底层模块，但同步脚本尚未迁移到该模块，正式 `SearchIndexer` 也未接入。Embedding 开关仍关闭；无真实工作库写入、无服务重启/部署、无 Git 提交。


## 2026-11-19：VectorIndex 增量同步收敛

- 新增 `backend/vector_index_sync.py`：按 URI + SHA-256 正文哈希 + memory_id + namespace/domain/path/lifecycle 元数据识别新增、变更、删除；仅对变化文档生成 passage embedding。
- `VectorIndex` 新增 `list_documents()`、`apply_changes()`；upsert 与删除在单一 SQLite 事务内完成，向量维度/数值在事务前校验，写入中异常回滚。原 `upsert_many()` / `delete_uris()` 保留为兼容包装。
- 增量同步实验脚本改为复用 VectorIndex 与同步服务，目标切换到全新隔离库 `.tmp/vector_index_sync_migration.db`，旧 PoC 库 `.tmp/nvidia_embedding_incremental.db` 保持不动。源工作库只读，obsolete/deprecated 继续排除。
- 专项测试：11 passed。覆盖新增/修改/删除/无变化、API失败保留旧索引、生命周期变化触发重嵌入、非法向量与事务写入异常回滚。
- 真实只读语料验证：48 条首次同步 48/48，元数据与向量均为 48；二次同步 48 条全部 unchanged，未调用 Embedding API，耗时 0.07 秒。首次同步耗时 23.07 秒。
- 本轮真实记忆正文按既有授权发送 NVIDIA Embedding API；只读源库没有写入，正式 SearchIndexer 未接入，embedding.enabled 仍关闭。
- 全量回归：`scripts/run-tests.bat -q --basetemp=.tmp/pytest-final-vector-sync2`，253 passed、0 failed、25 warnings；`git diff --check` 通过（仅有既有 LF/CRLF 提示）。


## 2026-11-19：个人记忆系统本机接通

- Claude 用户级 MCP `memory` 已切换为 Nocturne stdio 入口；原 `@modelcontextprotocol/server-memory` 配置备份并保留为 `memory-legacy`。配置备份文件名：`.claude.json.nocturne-backup-20261119-095543`。需要重启 Claude Code 刷新连接。
- 新增 `.vscode/mcp.json`，供 VS Code / GitHub Copilot 使用；需要 Reload Window 并刷新 MCP server。
- 新增 `scripts/start-nocturne-mcp.bat`（stdio，读取 config.json，禁用重复 UI / npm 安装）和根目录 `start-nocturne.bat`（Dashboard + REST + MCP HTTP 一体启动）。
- 本机整合服务当前运行于 `127.0.0.1:8233`，`/api/health` 返回 `status=ok, database=connected`；Dashboard 首页 HTTP 200。
- MCP 端到端验证：8 个工具成功注册；真实工作库 `core://agent` 读取成功、`search_memory` 搜索成功。隔离数据库 CRUD 流程 create/read/update/search/delete 全部成功。
- 发现 access log 更新在 MCP stdio 子进程中偶发 SQLite readonly 错误；已调整为 best-effort，日志失败不再阻断正文读取。此项统计写入问题仍待根因排查。
- SQLite changeset 默认目录改为用户数据库同目录 `.nocturne-snapshots`，避免依赖源码 checkout ACL。当前工作库原有 29KB changeset（80 条待处理变更）已复制到新位置，旧文件保留，未覆盖或删除。
- 全量后端：256 passed，0 failed；前端：17 passed；前端 production build 成功；`git diff --check` 通过。Vitest 需设置进程级 `NODE_ENV=test`，当前宿主默认 `NODE_ENV=production` 会导致 React act 测试错误。
- `embedding.enabled` 仍为 false，正式搜索尚未接入向量召回。
- 写入验收补充：MCP 子进程在当前自动化执行沙箱中对工作库目录被限制为只读（同一 URL 的宿主 Python 进程可写，子进程不可写）；隔离副本 CRUD 全流程通过。未修改真实库 ACL，也未迁移真实数据库。需在 Claude Code 本机宿主进程重启后完成真实库写入验收。


## 2026-11-19 本轮落地：语义检索与权限诊断

### 已完成
- 将真实工作库 48 条有效记忆同步到独立 `work-memory-vectors.db`，源数据库只读。模型 `nvidia/nemotron-3-embed-1b`，2048 维，向量与元数据均为 48 条且健康检查通过。
- 再次运行增量同步为 0 upsert / 0 delete / 48 unchanged，确认同步幂等。新增正式入口 `scripts/sync-nocturne-vectors.py`。
- 新增 `semantic_search_memory` MCP 工具，作为显式语义候选通道；`search_memory` 保持全文搜索默认行为不变。距离不作为置信度，暂不自动融合排序。
- 新增 `sync_semantic_index` MCP 工具，与 CLI 共用增量同步服务，便于在记忆写入后显式刷新向量索引。
- `VectorIndex` 增加只读打开模式，语义查询不会尝试修改向量库。
- 新增 `diagnose_memory_backend` MCP 工具，在当前 MCP 进程内检测数据库读写权限；写探测使用临时 DDL 事务并回滚。
- 当前宿主执行进程诊断结果：SQLite readable=true、writable=true，探测已回滚。该结果不能替代 Claude Code 实际 MCP 子进程验收。
- 专项测试 62 passed；全量测试随后执行验收。

### 当前边界
- `embedding.enabled` 保持 false；默认全文检索不变，语义检索需要显式调用。
- Claude Code / VS Code 需重载 MCP 配置后才能看到新增工具。应在 Claude Code 实际会话调用 `diagnose_memory_backend`，确认该进程的真实库写权限，再进行真实库 CRUD 验收。


---

## 2026-11-19 最新部署验收（覆盖前文历史状态）

### 已完成

- 真实工作库：`work-memory.db` 已通过 MCP HTTP 与 stdio 两种进程的读写诊断；写入探测事务回滚。stdio 入口已执行临时记忆 create → read → update → read → delete，测试记录已确认删除且无残留。
- MCP 工具：HTTP 与 stdio 均暴露 11 个工具；Claude Code 的用户级 `memory` server 指向项目 stdio launcher，旧 `memory-legacy` 保留。
- 摘要覆盖：当前可检索范围 48 个 URI 路径、46 条唯一 Memory；46/46 条摘要状态 VALID，48/48 路径可使用摘要。摘要由 AI 基于正文生成，保存到对应 Memory 版本。
- Boot：`system://boot` 只交付 2 条核心记忆摘要，当前约 204 estimated tokens；不自动展开正文。
- 向量候选：sidecar `work-memory-vectors.db` 已有 48/48 条元数据和向量。摘要更新后增量同步结果为 46 upsert、0 delete、2 unchanged，`integrity_ok=true`。语义检索为显式候选通道，默认 `search_memory` 仍使用 FTS。
- 运行入口：`start-nocturne.bat` 与 `scripts/start-nocturne-mcp.bat` 统一使用项目虚拟环境记录的基础解释器 `D:\Python\python.exe`。当前宿主上 `.venv` 解释器访问中文路径外部工作库失败，使用基础解释器后 HTTP/stdio 读写均通过。
- Agent 集成：用户级 `~/.claude/CLAUDE.md` 已引入 `rules/nocturne-memory.md`，包含启动读取、摘要优先、按需展开、查重、冲突保留和禁止未授权删除规则。Claude Code 仍需重启以加载本次用户级规则与 MCP 配置。
- 文档：`docs/project/personal-memory-quickstart.md` 已更新为当前真实状态。
- 测试：完整后端测试 `266 passed, 25 warnings`；`git diff --check` 通过；未提交 Git。

### 仍待完成

- Claude Code 本体重启后，在它自己的会话中调用 `diagnose_memory_backend` 做最后一次宿主验收；当前已用相同 stdio launcher 和 MCP 客户端完成独立验收。
- 建立至少 15 个真实任务评估样本，测 Recall@10、Precision@10（只对有人工标注的候选计算）、全文展开次数和实际上下文长度；不使用合成数据冒充真实效果。
- 根据真实评估决定是否调整全文/语义候选路由；向量距离没有可靠拒绝阈值，当前不得自动把最近邻当成相关记忆。

### 当前配置原则

- `embedding.enabled=false` 保持不变；向量检索只通过 `semantic_search_memory` 显式调用。
- `sync_semantic_index` 显式执行，只有新增或变化文档才请求 passage embedding；语义查询会请求 query embedding。
- 真实工作库是唯一活动数据源；向量索引是独立 sidecar，不写入原始工作库。
- 不启用旧记忆插件，不接回旧库，不自动删除、合并或覆盖冲突记忆。


## 2026-11-19 检索交付优化与真实任务评估

### 检索交付优化

- `search_memory` 新增 `token_budget`（0～20000，默认服务端 1200 estimated tokens）与 `include_snippets`（默认 false）。
- 默认只返回 L0 元数据与 L1 摘要，不再把正文片段重复塞进每次搜索；调用方只有需要原文线索时才传 `include_snippets=true`。
- 摘要缺失时明确返回 MISSING，不自动读取正文；只有 `read_memory(uri)` 才展开全文。
- 预算只约束 L1 摘要总量，元数据和 URI 不计入该近似预算；估算采用 UTF-8 字节启发式，不宣称是精确 tokenizer 结果。
- 已通过实际 MCP HTTP 验证默认模式、显式片段模式和 10-token 截断模式。

### 用户任务检索评估

评估数据：`docs/project/real-task-retrieval-eval-2026-11-19.json`。样本来自用户真实保存主题和重复任务类型，20 个场景，其中 1 个启动场景直接走 `system://boot`，不计入搜索指标。

- 19 个检索任务，全文检索 Recall@10：18/19（94.7%）。
- MRR：0.912。
- 1 个词法漏召回任务通过显式 `semantic_search_memory` 在 Top-1 找回，样本内组合覆盖 19/19。
- Precision@10 未计算：只标注了每个任务的正向目标，没有把未判定候选误当成负例。
- 该样本规模较小，只代表当前用户记忆库的定向回归，不代表通用性能或线上长期指标。

### 测试与运行

- 完整测试：269 passed，25 warnings，106.95s。
- 服务已重启加载本轮 MCP 工具签名；健康检查 HTTP 200。
- 不把语义向量距离作为置信度；不将语义结果自动混入默认全文搜索。


## 2026-11-19 项目长期记忆沉淀与最终状态更新

- 新增稳定项目记忆 `core://agent/nocturne-memory`（Memory ID 110，Priority 1），仅记录产品定位、L0～L3 披露原则、版本路线、检索/预算策略和数据维护边界；动态进度仍保留在项目文档。
- 摘要已生成并回读核对；向量 sidecar 增量同步 `upserted=1, deleted=0, unchanged=48, integrity_ok=true`。
- 当前真实工作库（2026-11-19 最新只读审计）：50 个 URI 路径、48 条当前有效 Memory；48/48 当前摘要有效，50/50 SearchDocument 与路径一致。
- 当前向量 sidecar：49/49 元数据与向量，完整性检查通过。
- 最新 stdio 验收：11 个工具；`search_memory` 暴露 `token_budget` 与 `include_snippets`；真实工作库读写诊断通过；默认检索无正文片段。
- 最后一次完整测试在本轮主要代码改动后通过：269 passed、25 warnings；随后对默认预算零值处理做了一个边界修正，MCP 工具专项测试 45 passed。


## 2026-11-19 总体验收与路线状态（当前权威状态）

### 当前结论

个人记忆系统已具备可日常使用的核心能力，真实工作库、摘要交付、全文检索、显式语义候选、MCP 客户端接入和基础质量保护均已落地；但尚未完成全部长期路线，不能标记为“最终建设完成”。

### 分版本状态

| 版本 | 状态 | 已完成 | 尚未完成 |
|---|---|---|---|
| V3.1 上下文交付 | **核心完成** | 版本级摘要、摘要检索、L0～L3 按需披露、Boot 摘要化、预算控制、真实工作库接入、MCP 双入口 | 更大规模真实任务下持续验证 Token 节省与召回稳定性 |
| V3.2 精准召回 | **核心检索能力完成，质量评估继续** | FTS5 召回优化、49 条语义向量 sidecar 对账、显式语义候选；原始任务集 Recall@10=94.74%；新增 18 条自然语言改写集 Recall@10=100%、MRR=0.9352 | 扩大独立查询集；逐条人工标注 Top10 后评估 Precision；验证不同主题和负向查询下的噪声水平 |
| V3.3 记忆质量 | **设计已确定，工程未完成** | 已明确重复识别、生命周期、冲突处理、摘要质量的产品规则 | 把规则落实到新建前查重提示、冲突/重复识别辅助和质量回归；不自动合并或删除 |
| V4.0 智能调度 | **基础规则已落地，自动化未完成** | System Prompt 已明确任务判断、按需检索、摘要优先、按需展开、写入查重和停止规则 | 真实任务验证工具选择准确率、全文展开率、重复读取率和 Token 消耗；再决定是否增加自动调度代码 |

### 已验证的部署事实

- 活动数据源为 SQLite 个人工作库；PostgreSQL 只是兼容分支，不是当前部署。
- 当前向量 sidecar 对账为 49/49，missing、stale、hash mismatch 均为 0。
- MCP 提供 11 个工具；工具描述已精简；用户已确认客户端可以正常使用记忆系统。
- 最近一次全量测试：273 passed、0 failed、0 errors，25 warnings；真实召回评估是小样本离线评估，不等于线上长期指标。
- `docs/system_prompt.md` 已整理为统一的 Nocturne Agent 调度指令，解决检索、披露、写入和删除规则之间的冲突。

### 接下来按此顺序推进

1. **V3.3 质量闭环**：只读扫描结果见 memory-quality-audit-2026-11-19.md；新增 scripts/audit-memory-quality.py 可重复执行。最新结果已将 Memory ID 111 摘要补齐并验证；当前摘要缺失 0，近似重复候选、摘要/索引不一致、孤立 SearchDocument 均为 0。生命周期建议见 memory-lifecycle-review-2026-11-19.md；10 个 unspecified 节点（含根占位符）均未自动修改。
2. **V3.2 召回验证**：从真实任务中补充自然语言改写和负向案例，人工标注 Top10；在证据充分前维持 FTS 默认、语义显式调用。
3. **V4.0 调度评估**：用任务集检查是否正确决定“不检索/关键词检索/语义候选/读取全文/写入记忆”，量化无效工具调用与上下文开销。
4. **运行安全**：保持 localhost 暴露范围；在需要远程访问前配置 API_TOKEN，不把 API Key 写入文档或日志。

当前不引入新的数据库、向量平台、后台自动摘要、多 Agent 或复杂治理系统。优先把现有能力用准、验证好。


### 2026-11-19 自然语言改写召回专项

- 真实工作库只读评估新增 docs/project/real-task-paraphrase-eval-2026-11-19.json，18 条自然语言改写查询全部在 Top10 找到目标，Recall@10=100%，MRR=0.9352（Top1 16、Top2 1、Top3 1）。
- 发现并修复短语别名只在原始严格检索完全无结果时执行的问题：当泛化严格结果存在时，也评估审核过的别名；保留原始第一条严格结果，将别名候选放在其后、泛化严格候选之前；若别名目标已在严格候选中但排名靠后，则提升该目标，避免同一 Node 重复。
- 新增短语触发映射，覆盖上下文大输出、故障排查、复用现有实现、需求澄清、任务恢复和 Codex bridge。替代查询使用可验证的 AND 词组，不使用宽泛 OR。
- 负向抽查 5 条：3 条无结果；2 条各返回 3 条明显无关候选。说明搜索噪声仍需治理，独立问题应由 Agent 调度规则直接判定不检索。
- Precision@10 仍未计算，未标注候选不视为负例；向量仍为显式候选，不进入默认搜索。
- 本轮工作库只读；检索改动只涉及 SQLite 当前部署分支。全量测试结果以本轮最终验收记录为准。


### 2026-11-19 本轮最终回归与部署提示

- 全量后端测试：273 passed、0 failed、0 errors，25 warnings，110.93 秒。
- 检索专项：9 passed；覆盖 6 类自然语言短语别名，以及“原始严格命中仍保留第一位、别名目标提升到后续候选”的排序约束。
- 真实工作库以 SQLite mode=ro 执行 18 条自然语言改写查询，按 Node 身份核对目标：Recall@10=18/18，MRR=0.9352；未写入工作库。
- 质量审计复跑：48 条当前有效 Memory，摘要缺失 0，近似重复候选 0，摘要/搜索索引不一致 0；50 个 URI 路径与 50 条 SearchDocument 对齐。
- Python AST 检查通过；git diff --check 通过（仅有既存 LF/CRLF 提示）。
- Dashboard/API 已重启为新进程并通过 HTTP MCP 实际调用验证短语别名召回；Claude/Deva 管理的既有 stdio 子进程仍需由各客户端重载后才会加载新代码。
- 未修改真实工作库、向量 sidecar、快照或 API Key；未调用 NVIDIA API；未提交 Git。


### 2026-11-19 HTTP 服务重载与质量复核

- 已重启 Dashboard/API 进程（原 PID 19916，新 PID 20580）；/api/health 返回 HTTP 200、database=connected。
- 通过真实 MCP Streamable HTTP 客户端重新 initialize，服务端版本 1.30.0，11 个工具完整可见；实际调用 search_memory 查询自然语言改写，正确返回 core://agent/dsh/context-output，摘要优先且没有正文片段。
- Claude/Deva 管理的 stdio 子进程没有被强制终止，避免破坏客户端会话；它们需要随客户端重载重新启动后才会载入最新代码。
- 最新只读质量审计：111 个 Memory 版本、48 个当前有效版本、50 个 URI 路径/50 个 SearchDocument；当前摘要缺失 1 条（Memory ID 111），近似重复候选 0，摘要索引不一致 0；生命周期 unspecified 10（含系统根节点占位符）。
- 新增 memory-lifecycle-review-2026-11-19.md，给出 9 条业务 Memory 的 lifecycle 候选及 ID 111 摘要草案；不自动更新真实 Memory、摘要或生命周期。


### 2026-11-19 MCP 双传输重载验收与 V4.0 评估集

- HTTP 服务已重启，PID 20580；健康检查 200。
- MCP HTTP Streamable 客户端 initialize/list_tools：服务端 1.30.0，11 个工具；真实调用 search_memory 成功返回正确目标摘要。
- 新进程 stdio launcher 独立验收：initialize/list_tools 11 个工具；同一自然语言查询成功返回正确目标摘要。Claude/Deva 已有会话管理的旧 stdio 子进程未强制终止，客户端重载后自然替换。
- Memory 111 已通过 MCP update_memory_summary 补齐摘要，并通过 search_memory 回读确认 VALID；正文与 lifecycle_status 未修改。
- 最新只读质量审计：111 个版本、48 个当前有效 Memory、50 个 URI 路径/50 条 SearchDocument；摘要缺失 0、近似重复候选 0、摘要索引不一致 0；unspecified 10（含系统根节点）。
- 新增 memory-lifecycle-review-2026-11-19.md 与 agent-dispatch-evaluation-2026-11-19.md。生命周期只给出候选，不自动改状态；V4.0 的 12 条任务矩阵待真实客户端工具轨迹验收。
- 检索专项 9 passed；全量回归最近结果仍为 273 passed、25 warnings。此次仅更新注释和文档，并补齐一条摘要，因此未重复运行全量测试。
