# Nocturne V3.1：上下文交付建设方案

> 状态：V3.1 核心能力已部署到个人 SQLite 工作库。2026-11-19 验收：全量测试 271 passed；真实向量索引 49/49 对账一致；API 健康检查与 Dashboard 均 HTTP 200。Claude Code 客户端侧仍需启动后确认 MCP 配置已加载。详细结果见 `acceptance-2026-11-19.md`。  
> 当前部署配置使用 SQLite（`sqlite+aiosqlite`）；PostgreSQL 是代码兼容分支，不是当前个人部署的数据库。
> 范围：个人自用记忆系统；本阶段只解决按需加载、渐进式披露和 Token 消耗，不建设企业级平台能力。  
> 本文保留为 V3.1 建设前的初始方案与历史基线；其中“当前代码现状”和实施清单不代表最新实现状态。最新实际状态以 `acceptance-2026-11-19.md` 和当前代码为准。

## 1. 目标

Nocturne 的核心目标：

1. 按需加载：只取当前任务真正需要的记忆。
2. 渐进式披露：先给摘要，需要时再读正文。
3. 精准召回：找到正确记忆，并保留正确的 URI、Alias、Path、Priority 和 Disclosure 入口语义。
4. 节省 Token：减少无关正文和重复内容进入上下文。

判断一个改动是否值得做，只看它是否让记忆找得更准、让 AI 读得更少、减少错误或重复，且对个人实际使用有帮助。

## 2. 已确认的产品决策

### 2.1 L0～L3 是灵活披露层级，不是固定流水线

| 层级 | 交付内容 | 使用原则 |
|---|---|---|
| L0 | URI、路径/显示名、关键词及必要元数据 | 让 AI 知道有哪些相关记忆 |
| L1 | 核心摘要 | 默认优先交付，帮助判断是否需要展开 |
| L2 | 完整正文 | 任务确实需要细节时再读取 |
| L3 | 关联信息 | 默认只给直接关联，不递归展开关联正文 |

- `SUMMARY_PREFERRED`：优先摘要；摘要缺失时返回 L0 和 `MISSING`，不自动展开正文。
- `DETAIL_ALLOWED`：表示允许展开，不表示必须展开。
- 用户/调用方明确指定 URI 直接读取时，仍按现有 `read_memory` 语义读取正文，不受摘要缺失影响。
- L0～L3 按任务和披露偏好灵活组合，不强制每次走完四层。

### 2.2 Token Budget

- 客户端优先决定本次任务预算；服务端提供可配置默认值。
- 第一阶段只做简单的条数和内容长度控制，不做预算账本、复杂并发扣减或持久化计费系统。
- 候选数、摘要数和 Token 数的初始建议值必须通过真实任务验证，不作为不可突破的硬限制。

### 2.3 摘要规则

- 摘要属于具体 Memory 正文版本，不属于 Node。
- 优先在现有 `memories` 表增加摘要字段，不新增摘要业务表。
- 正文更新创建新 Memory 版本时，新版本摘要为空；旧版本摘要保留。
- 摘要由 AI 根据正文生成并提交；Nocturne 负责保存、检索和交付，不在后台自动生成摘要。
- 摘要必须忠于正文；正文是事实源，摘要与正文不一致时以正文为准。
- 暂不建设复杂摘要状态机；有摘要视为 `VALID`，无摘要视为 `MISSING`。

## 3. 建设前代码现状（历史基线）

| 位置 | 当前实现 | 对 V3.1 的影响 |
|---|---|---|
| `backend/db/models.py` 的 `Memory` | 只有正文、版本链和创建时间，没有摘要字段 | 需要增加版本级摘要字段 |
| `backend/db/models.py` 的 `SearchDocument` | 保存 URI、正文、Disclosure、Search Terms、Priority 等派生字段 | 需要同步摘要，避免搜索时回查大量正文 |
| `backend/db/search.py` | 负责派生搜索文档维护；SQLite FTS5、PostgreSQL 全文检索 | 摘要字段、FTS 列、PostgreSQL 查询和重建逻辑必须一起调整 |
| `backend/mcp_server.py` 的 `search_memory` | 返回 URI、Priority、Disclosure 和正文 Snippet | 需要增加摘要和摘要状态；Snippet 继续明确标识为命中片段 |
| `backend/mcp_server.py` 的 `read_memory` | 普通 URI 通过 `fetch_and_format_memory` 读取完整内容 | 保留兼容；按需读取由搜索结果引导，不破坏明确 URI 直读 |
| `backend/system_views.py` | `fetch_and_format_memory` 同时服务普通读取和 Boot；Boot 当前逐个读取完整记忆 | Boot 是 Token 优化的重点入口，需要单独设计摘要/正文披露方式 |
| `backend/db/graph.py` | `create_memory`、`update_memory` 管理正文版本；正文变更创建新版本 | 需要增加明确的摘要写入入口，并保证版本隔离 |
| `backend/db/migrations/` | 当前最高迁移编号为 015 | 下一迁移编号可用 016，具体文件名按现有迁移约定确定 |

搜索索引是派生数据，不是事实源。摘要增加后必须保证新建、更新、版本切换、索引重建都能同步摘要。SQLite FTS5 和 PostgreSQL 全文检索两条路径都要覆盖。

## 4. V3.1 实施范围

### P0：摘要数据和版本管理

1. 在 `Memory` 增加 `summary_content`、`summary_updated_at`。
2. 在 `SearchDocument` 增加摘要派生字段，字段名与 ORM、迁移、索引保持一致。
3. 新增迁移 `016`：为现有数据增加可空字段；不回填虚构摘要，不改动旧正文。
4. 增加摘要更新方法，按 Memory 版本 ID 或明确 URI 定位，避免只按 Node 更新而误改历史版本。
5. 正文更新创建新版本时，新版本摘要为空；不能复制旧版本摘要。

### P0：搜索索引和搜索结果

1. `SearchIndexer._build_search_documents_for_node` 从当前活动 Memory 同步摘要。
2. SQLite FTS5 的虚拟表定义、INSERT、DELETE/重建和 BM25 列权重同步更新。
3. PostgreSQL 全文查询同步加入摘要字段，并明确摘要与正文的权重关系。
4. `search_memory` 在现有返回中增加 `summary`、`summary_status`、`expandable` 等必要信息。
5. `snippet` 继续表示正文命中片段，不能将其当作摘要。
6. 摘要缺失时返回 `MISSING`，不自动塞入全文。
7. 保留 namespace、domain、lifecycle、Priority、Disclosure 等现有约束。

### P0：Alias / Path 入口语义

同一个 Node 可以通过多个 Path/Alias 被找到。不能只按 `node_uuid` 去重后丢掉其他入口的 Priority、Disclosure 或 URI。

建议结果按“记忆实体 + 有意义的入口”组织：正文/摘要可以共享，入口元数据必须保留。完全相同的入口可以去重；不同披露策略的入口不能被错误合并。具体返回结构在编码前结合现有调用方确定。

### P1：按需读取与 Boot

1. 保留普通 `read_memory(uri)` 的完整正文读取行为，保证现有 MCP 客户端兼容。
2. 增加轻量摘要读取/格式化能力，优先复用现有 `system_views.py` 和 URI 解析，不另建一套复杂服务。
3. 检查 `system://boot`：当前实现会对配置中的每个 URI 调用完整读取。V3.1 应按已确认披露偏好决定返回 L0/L1 或允许的正文，不因摘要缺失自动展开。
4. `system://index/<domain>` 当前是 Node-centric 索引并折叠 Alias。调整时需保留可识别的入口信息，不应为了摘要交付破坏现有索引用途。
5. L3 默认只返回直接关联标识/摘要，不递归读取关联正文。

### P1：简单预算

先由客户端控制本轮预算；服务端提供可配置默认条数/字符长度限制。先统计真实输出长度或 Token 估算，不建设 BudgetLedger。

## 5. 暂不做的事

- 不新增 `MemorySummary`、`ContextPackage`、`Expansion`、`BudgetLedger` 等表或业务模型。
- 不新增独立 `get_context` 工具；优先增强现有 `search_memory`。
- 不建设后台自动摘要任务。
- 不引入向量数据库或多 Agent 协作，除非后续真实任务证明现有 FTS 召回不足。
- 不建设复杂 Token 预算账本、权限系统、状态机或企业级治理流程。
- 不改变明确 URI 直读的现有语义。

## 6. 实施顺序

1. 先完成模型、迁移和摘要版本写入能力。
2. 再完成 SearchDocument、SQLite FTS5、PostgreSQL 全文索引同步。
3. 再增强 `search_memory` 响应，保留入口语义。
4. 再处理轻量读取和 `system://boot`，保证旧 `read_memory` 兼容。
5. 最后补齐测试、运行双数据库验证和真实任务评估。

## 7. 验收标准

- 新建记忆可写入摘要；不提供摘要时状态为 `MISSING`。
- 更新正文产生新版本，新版本摘要为空，旧版本摘要不变。
- 摘要更新只影响目标 Memory 版本，并能同步刷新所有相关 SearchDocument。
- SQLite 与 PostgreSQL 均可按摘要召回；索引重建后摘要不丢失。
- 搜索结果清楚区分摘要和正文 Snippet。
- 摘要缺失时只返回 L0 + `MISSING`，不自动返回全文。
- 明确 URI 调用 `read_memory` 仍能读取完整正文。
- Alias/Path 的 Priority、Disclosure 和 namespace 隔离不丢失。
- Boot 不再无条件加载所有配置记忆的完整正文；行为遵循披露偏好。
- 对比改造前后真实任务的 Recall@10、Precision@10、全文读取次数和 Token 消耗。

## 8. 当前未解决/需验证事项

1. MCP `update_memory_summary(memory_id, summary_content)` 已实现；REST 管理界面本期不额外增加摘要编辑入口，避免重复建设写入路径。
2. `system://boot` 已兼容原 URI 列表配置并统一采用 L0 + L1；逐 URI 独立披露配置暂不纳入 V3.1。
3. Migration 016 已实现 SQLite FTS5 和 PostgreSQL GIN 更新；SQLite 已通过隔离验证，PostgreSQL 仍需在真实测试实例验证。
4. Alias 去重已实现为“单实体一份正文 + 其他命中 URI 作为 aliases”，共享 Edge 的 Priority/Disclosure 按现有数据模型保持一致；后续通过完整测试和真实任务评估。
5. 测试环境必须明确 SQLite 和 PostgreSQL 的实际连接目标；当前工作数据库文件访问受限，不能误连或擅自迁移真实数据。

## 9. 代码参考

- `backend/db/models.py`：`Memory`、`SearchDocument`
- `backend/db/search.py`：`SearchIndexer`、派生文档同步、SQLite FTS5 / PostgreSQL 查询
- `backend/db/graph.py`：`create_memory`、`update_memory`
- `backend/mcp_server.py`：`search_memory`、`read_memory`
- `backend/system_views.py`：`fetch_and_format_memory`、`generate_boot_memory_view`、`generate_memory_index_view`
- `backend/db/migrations/`：当前最高迁移为 015


## 10. 进一步源码核对后的实现任务清单

本节是基于本轮继续只读核对补充的工程拆分。它细化实施顺序，不改变前面的产品决策。

### 10.1 已确认的代码事实

1. `Memory` 以 `id` 区分正文版本，同一概念实体共享 `node_uuid`。`update_memory` 在正文变化时通过 `_insert_memory` 创建新行，再将旧版本标记 deprecated 并建立 `migrated_to` 链。因此摘要应跟随 `Memory.id`，新版本自然保持空摘要，不能放在 `Node` 上。
2. `Edge` 的 `(parent_uuid, child_uuid)` 有唯一约束；`Path` 可以复用同一个 `edge_id`。因此多个 Alias 路径可能共享同一条 Edge，Priority/Disclosure 也会共享；不能假设每个 Alias 都拥有独立元数据。搜索结果应保留每个有效 URI 入口及其实际关联 Edge 元数据。
3. `SearchIndexer._build_search_documents_for_node` 当前为每个可达 Path 生成一条 SearchDocument，正文来自活动 Memory；每条记录带各自 Path 对应的 Edge Priority/Disclosure。
4. `search()` 的候选查询最终使用 `seen_nodes` 按 `node_uuid` 去重，只保留排序靠前的一个入口。问题确实存在，但修复时应先定义“同一实体的多个入口如何呈现”，避免简单删除去重后把同一正文重复塞满结果。
5. MCP `search_memory` 当前把 URI、Priority、Disclosure 和正文 Snippet 格式化为文本；`read_memory(uri)` 是独立的 URI 读取入口。第一版可以在原有文本结果中增加摘要段落，不需要改变 MCP 工具名称或参数。
6. `system://boot` 当前逐个调用 `fetch_and_format_memory(uri)`，因此会加载配置记忆的完整内容；随后还会附加最近 5 条记忆视图。它是上下文初始加载量的重要来源。
7. 迁移 runner 在有待执行迁移时先尝试备份：SQLite 使用在线备份并校验；PostgreSQL 优先 `pg_dump`，找不到时会退化为 JSON 数据导出并明确提示 Schema 不受保护。不能把这个回退路径描述为完整数据库备份。
8. 当前迁移文件最高编号为 `015_add_node_lifecycle_status.py`，因此本轮计划新增 `016_add_memory_summary.py`。迁移 runner 按文件名排序并按 `schema_migrations` 记录跳过已执行迁移。

### 10.2 开发任务拆分与依赖

| 顺序 | 任务 | 主要文件 | 完成定义 |
|---|---|---|---|
| 1 | Memory 摘要字段 | `backend/db/models.py` | Memory 增加可空摘要正文和更新时间；SearchDocument 增加摘要字段 |
| 2 | 数据库迁移 | `backend/db/migrations/016_add_memory_summary.py` | SQLite/PostgreSQL 均可新增字段；迁移可安全识别字段已存在的情况；不回填假摘要 |
| 3 | 摘要写入接口 | `backend/db/graph.py` 或现有合适的写服务 | 按 Memory 版本定位写入；校验目标版本存在；更新摘要后刷新该 Node 的所有 Namespace 搜索文档 |
| 4 | 索引同步 | `backend/db/search.py` | 构建、单节点刷新、全量重建都同步摘要；FTS 两种数据库路径一致 |
| 5 | 搜索返回 | `backend/db/search.py` | 结果增加摘要及状态；区分摘要和正文 Snippet；修正入口去重策略并有测试保护 |
| 6 | MCP 文本输出 | `backend/mcp_server.py` | 原有 search_memory 参数和 read_memory URI 行为不变；搜索输出明确显示 Summary / Snippet / MISSING |
| 7 | Boot 渐进披露 | `backend/system_views.py` | Boot 默认不再无条件加载所有正文；摘要缺失时不自动回退全文；明确 URI 直读仍保持全文 |
| 8 | 测试与评估 | `backend/tests/` | 覆盖版本、索引、双数据库、入口语义、Boot、旧工具兼容和 Token/全文读取量 |

### 10.3 关键实现约束

- 摘要更新接口必须定位到 `memory_id`，不能只按 `node_uuid` 更新，否则可能覆盖历史版本摘要。
- 更新摘要后，当前 `refresh_search_documents_for_node(..., refresh_all_namespaces=True)` 可复用来刷新各路径索引；应确认它使用当前活动 Memory 并在同一 Session 内完成。
- `SearchDocument` 当前的 FTS5 表和 PostgreSQL GIN 表达式不是 ORM 自动生成的：SQLite 插入/删除/重建 SQL、PostgreSQL 查询表达式和迁移回填必须一起改。
- SQLite FTS5 表当前包含 `path`、`uri`、`content`、`disclosure`、`search_terms` 等列；增加摘要后必须同步建表/重建策略、插入 SQL、查询 SQL和 BM25 列权重。不能只给 ORM 增字段。
- PostgreSQL 当前在搜索时动态构建 `to_tsvector('simple', ...)`；摘要字段必须同时进入匹配表达式和 rank 表达式。若迁移中修改 GIN 表达式，必须删除并重建旧索引，避免索引表达式与查询不一致。
- Alias 结果策略建议先保留不同 URI 的候选，再做轻量实体去重：当同 Node 多入口都命中时，默认保留得分最高入口，并把其他入口作为 `aliases` 附加信息；如果入口披露策略确实不同，则保留必要的入口元数据。不要把所有 Alias 正文重复返回。
- `system://boot` 的默认改造建议为：按配置 URI 返回 L0 + L1 摘要；摘要缺失则只返回 L0 + `MISSING`；不自动展开 L2。保留当前 recent 区块，但应单独评估它的内容长度，避免 Boot 虽然不读全文却又从 recent 区块加载大量正文。
- 迁移前必须核对实际数据库类型、连接目标和备份结果。PostgreSQL 仅 JSON 回退时不能把它当成可完整回滚的保护。

### 10.4 必须补齐的测试用例

1. 新建 Memory 默认无摘要，搜索结果状态为 `MISSING`。
2. 写入摘要后，Memory 与 SearchDocument 中摘要一致，`summary_updated_at` 更新。
3. 正文更新创建新 Memory 版本，新版本摘要为空，旧版本摘要仍保留。
4. 对历史 Memory ID 更新摘要，不得改变活动版本摘要或搜索结果摘要。
5. 摘要更新后，所有 Namespace/Path 对应 SearchDocument 均刷新。
6. 全量重建搜索索引后摘要仍存在，SQLite FTS5 可命中摘要关键词。
7. PostgreSQL 可命中摘要关键词，rank 表达式包含摘要字段。
8. 同一 Node 多个 Path 命中时，不会错误丢失入口 URI；共享 Edge 的入口显示相同 Priority/Disclosure，不同 Edge 的入口显示各自元数据。
9. 搜索结果中的 Summary 与 Snippet 分开标识；摘要缺失时不返回全文。
10. `read_memory(uri)` 仍返回完整正文；`system://boot` 默认只返回摘要/索引，不自动展开正文。
11. namespace/domain/lifecycle_status 过滤行为不回退。
12. 对旧 MCP 客户端，原有 `search_memory(query, domain, limit, include_obsolete)` 和 `read_memory(uri)` 调用仍有效。

### 10.5 当前环境验证限制

此前尝试使用当前默认 Python 环境运行指定 pytest 用例，因环境未安装 `pytest` 而未能启动测试。后续先只读检查项目虚拟环境和依赖管理配置，找到项目已有测试环境再运行；不为跑测试擅自安装依赖或修改项目环境。



## 11. V3.1 首批代码实现记录

本节记录已落地的代码，不代表已在工作数据库执行迁移。

### 11.1 已实现

- `Memory`：增加 `summary_content`、`summary_updated_at`，摘要跟随具体版本。
- `SearchDocument`：增加 `summary_content`，由活动 Memory 派生。
- Migration 016：增加上述字段；先从 Memory 回填派生 SearchDocument 摘要，再重建 SQLite FTS5 表；PostgreSQL 重建包含摘要字段的 GIN 全文索引。迁移可重复执行，不生成假摘要。
- `GraphService.update_memory_summary(memory_id, summary_content)`：按版本 ID 保存/清空摘要；活动版本更新后刷新所有 Namespace 搜索文档；历史版本只保留摘要，不覆盖活动搜索索引。
- `SearchIndexer`：摘要进入 SQLite FTS5 和 PostgreSQL tsvector 查询；返回 `summary`、`summary_status`、`memory_id`、`expandable`，正文 `snippet` 独立保留。
- Alias 结果：同一 Node 只返回一份内容；其他匹配 URI 作为 `aliases` 附加，保留对应入口的 Priority / Disclosure。若底层路径复用同一 Edge，则按当前模型共享该 Edge 元数据。
- MCP：新增 `update_memory_summary(memory_id, summary_content)`；`search_memory` 显示 Summary / Body snippet / 全文读取入口；旧工具签名不变。
- Boot：新增只查 L0/L1 的 `get_memory_summary_by_path`；`system://boot` 默认只交付 URI、摘要和必要元数据，摘要缺失不自动展开；显式 `read_memory(uri)` 仍读取全文。
- 预算：新增 `boot_summary_token_budget` 默认 2000 estimated tokens；按 UTF-8 字节做轻量估算，超出时截断/省略摘要，不建设 Token 账本。
- recent 区块已核对为 URI、Priority、Disclosure 和时间等轻量元数据，不会重新灌入记忆正文。

### 11.2 已做的隔离验证

- Python 编译检查覆盖模型、搜索、GraphService、MCP、迁移和新增测试文件，全部通过。
- 使用独立 SQLite 内存库执行 Migration 016 两次，验证幂等和 FTS5 摘要召回，通过。
- 使用独立 SQLite 内存库验证摘要写入、摘要搜索、全量索引重建、正文更新后新版本摘要为空、历史版本摘要保留、Alias 入口信息保留，通过。
- 使用隔离 SQLite 内存库验证 MCP 摘要写入和搜索输出，通过。
- 使用隔离 SQLite 内存库验证 Boot 只交付 L0/L1、摘要缺失不自动展开、显式全文读取保持原行为，通过。
- 使用隔离 SQLite 内存库验证 Boot 摘要预算截断和预算信息输出，通过。

### 11.3 当前验证状态（2026-11-18）

- 项目虚拟环境和依赖已就绪；最新完整后端测试为 216 passed、0 failed、25 warnings。测试使用隔离 SQLite，不等同于真实库验收。
- 当前正式部署数据库已确认是 SQLite：`E:\myPrivateSpace\记忆系统数据库\work\work-memory.db`，不是 PostgreSQL。
- 已通过 SQLite Online Backup API 创建迁移前备份：`E:\myPrivateSpace\记忆系统数据库\work\work-memory.db.20261118_185546.13632-8a27c4f3.bak`；备份 `integrity_check=ok`。
- 已先在真实库副本上通过项目原生 `run_migrations()` 完整执行 Migration 016，验证迁移记录、摘要字段、FTS5 重建和行数一致。
- 随后在正式工作库执行 Migration 016，迁移记录已写入 `schema_migrations`；`memories` 新增 `summary_content`、`summary_updated_at`，`search_documents` 新增 `summary_content`，FTS5 已重建。
- 正式库迁移后 `PRAGMA integrity_check=ok`；`memories=105`、`search_documents=48`、`search_documents_fts=48`，迁移前后行数一致。没有生成或伪造任何记忆摘要，现有摘要为空，等待后续按需生成。
- PostgreSQL 兼容分支尚未在真实 PostgreSQL 实例验证；当前部署使用 SQLite，本阶段不以 PostgreSQL 作为验收目标。
- 真实库迁移已完成；仍需继续验证正式库上的应用层搜索/摘要读写链路。未提交 Git。


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

