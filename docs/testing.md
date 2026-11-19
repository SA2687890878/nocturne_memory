## 1. 后端测试分层

后端测试框架：

- `pytest`
- `pytest-asyncio`
- `pytest-cov`

目录结构：

- `backend/tests/unit/`
- `backend/tests/service/`
- `backend/tests/api/`
- `backend/tests/mcp/`

当前覆盖重点：

- 鉴权中间件与排除路径：`backend/tests/unit/test_auth.py`
- search terms 与查询词展开：`backend/tests/unit/test_search_terms.py`
- changeset/snapshot 的 before/after 语义：`backend/tests/unit/test_snapshot.py`
- GraphService 的创建、更新、别名、删除、版本链：`backend/tests/service/test_graph_service.py`
- GlossaryService 的关键词绑定与召回：`backend/tests/service/test_glossary_service.py`
- SearchIndexer 的索引刷新与搜索结果：`backend/tests/service/test_search_indexer.py`
- 浏览、审核、维护 API：`backend/tests/api/test_api_routes.py`
- MCP 工具与系统视图：`backend/tests/mcp/test_mcp_tools.py`

## 2. 测试隔离策略

后端测试通过 `backend/tests/conftest.py` 统一做环境隔离：

- 默认使用 SQLite 临时库
- 可通过 `TEST_DATABASE_URL` 切到 PostgreSQL
- 每轮测试都重建测试数据库和 snapshot 目录
- 测试时显式覆盖 `DATABASE_URL`、`SNAPSHOT_DIR`、`VALID_DOMAINS`、`CORE_MEMORY_URIS`
- 测试时把 `API_TOKEN` 设为空，避免被本地 `.env` 污染


## 3. 本地运行

运行全部后端测试：

**Windows (PowerShell)：**
```powershell
.\scripts\run-tests.bat -q
```

首次运行会自动创建 `.venv` 并安装 `backend/requirements.txt` 与 `backend/requirements-dev.txt`；后续直接复用。脚本同时将 `TEMP/TMP` 指向项目 `.tmp`，避免 Windows 临时目录不可写导致 pip/pytest 失败。
pytest 缓存目录固定为 `.tmp/pytest_cache`，不依赖仓库根目录已有 `.pytest_cache` 的写权限。不要使用全局 Python 直接代替项目虚拟环境执行测试。

**Linux/macOS：**
```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

**Linux/macOS:**
```bash
.venv/bin/pytest backend/tests
```

带覆盖率运行：

**Windows (PowerShell):**
```powershell
.\scripts\run-tests.bat -q --cov=backend --cov-report=term-missing
```

**Linux/macOS:**
```bash
.venv/bin/pytest backend/tests --cov=backend --cov-report=term-missing
```

如果想单独验证 PostgreSQL 路径，可以显式指定：

**Windows (PowerShell):**
```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://user:password@127.0.0.1:5432/nocturne_memory?ssl=disable"
.\.venv\Scripts\pytest backend/tests/service backend/tests/api -q
```

**Linux/macOS:**
```bash
export TEST_DATABASE_URL='postgresql+asyncpg://user:password@127.0.0.1:5432/nocturne_memory?ssl=disable'
.venv/bin/pytest backend/tests/service backend/tests/api -q
```

## 4. GitHub Actions

- `.github/workflows/backend-tests.yml`

触发时机：

- `pull_request`
- `push`
- `workflow_dispatch`

执行内容：

1. SQLite 路径下，按 Python `3.10` / `3.12` 矩阵运行 `backend/tests`
2. 额外跑 PostgreSQL smoke


### 最近一次验证（2026-11-18）

- 完整后端测试：`.venv\Scripts\python.exe -m pytest -q backend/tests`，`208 passed`，`0 failed`，74.73 秒（Windows BAT 实际执行）。直接 pytest 复测为 76.21 秒。
- Windows 脚本目标路径验证：`scripts\run-tests.bat -q backend/tests/service/test_memory_summary_migration.py`，只执行指定文件，`1 passed`。无路径参数时默认执行 `backend/tests`。
- pytest 缓存目录：`.tmp/pytest_cache`；临时目录：`.tmp/pytest-temp`。
- 当前项目配置使用 SQLite；自动化测试使用隔离数据库，不会自动迁移个人工作库。
- 仍有 25 条测试警告，主要来自 AnyIO 对 pytest 内部兼容别名的弃用提示，以及测试启动时未配置 `API_TOKEN` 的提示；不影响本次测试退出码。
- 合成检索集现已改为先构造完整的 15 条记忆，再逐条查询，避免之前逐条创建、逐条查询造成的单文档简单场景偏差。结果：Recall@10 100%、MRR 1.000、P@10 0.100；仅代表当前合成数据。
- 新增 5 个不直接使用记忆标题/URI 的任务式查询。首次实测严格 AND 查询 5/5 全部无结果；增加 SQLite 严格 AND 无结果时才回退 OR，并按 BM25 排序后，5/5 命中且目标均排第 1。此结果是合成集上的诊断，不代表真实语义召回。


### Boot 渐进披露专项回归（2026-11-18）

- `test_boot_budget_is_summary_only_not_total_output_budget`：验证摘要预算只约束摘要，不是整个 Boot 输出的总预算；Boot 不调用全文读取函数，正文标记不进入输出；显式 URI 读取仍可展开正文。
- `test_boot_missing_summary_does_not_expand_body`：摘要缺失时只返回 `MISSING`，不加载正文。
- 专项结果：7 passed，1 warning，11.96 秒。


### 最新全量复测（2026-11-18）

- `python -m pytest -q backend/tests`：210 passed，0 failed，25 warnings，81.60 秒。
- `git diff --check`：通过。


### 搜索干扰候选实验（2026-11-18）



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


### Boot recent 查询避免读取正文（2026-11-18）

- 检查发现 `generate_boot_memory_view()` 附带的 `system://recent` 不会输出正文，但其底层 `get_recent_memories()` 原先 `select(Memory, ...)` 会把完整 Memory ORM 实体（包括大字段 `content`）取入进程，属于隐式正文读取。
- 已改为显式投影所需字段：Memory ID/创建时间、Edge priority/disclosure、Path domain/path、Node lifecycle；返回结构保持兼容，不改变 recent 展示内容。
- 新增 SQL 监听回归，验证该查询不选择 `memories.content`。全量后端测试：214 passed、0 failed、25 warnings，100.97 秒；隔离 SQLite。

### 自然语言改写召回与召回词边界（2026-11-18）

- `test_auxiliary_search_terms_paraphrase_diagnostic` 使用 15 条合成记忆和 10 条自然语言改写查询。未增加辅助召回词时 Recall@10 为 10%；将查询短语直接注入隔离库的 SearchDocument/FTS 辅助索引后，Recall@10 为 20%，开启 Partial 仍为 20%。此前通过 GlossaryKeyword 得出的 100% 是错误实验方法造成的结果，已撤回。该实验仅是合成数据诊断，不代表真实用户任务成绩。
- 该实验不能证明 `GlossaryKeyword` 可用于同义词/别名。`manage_triggers` 的真实语义是：把记忆库中已经存在的触发词绑定到目标 Node；当该词出现在其他记忆正文时，`read_memory` 展示关联链接。不得将整句查询、任意同义表达或不存在于正文中的词写入 Glossary。
- 当前不修改生产召回策略，不新增 `recall_terms` 字段或迁移。若真实任务评估持续证明词面表达差异造成明显漏召回，再单独评估 Memory 版本级 `recall_terms`：正文更新产生新版本时默认清空，需重新确认；由 SearchDocument 将其作为独立召回词来源合并进现有 FTS `search_terms`，不改变 Glossary 语义，也不混入摘要。
- 是否值得实现，先看真实任务集的漏召回率、人工维护成本、误召回率；不以合成数据的 100% 作为上线依据。真实工作库目前不可读，因此真实任务评估仍未开始。
- 修正后专项测试：1 passed；全量后端测试：213 passed、0 failed、25 warnings，93.73 秒。均来自隔离 SQLite；不能据此声称真实工作库迁移已验证。

### 搜索正文按需读取回归（2026-11-18）

- `test_search_reads_only_bounded_body_snippet_from_search_index`：使用大正文且将命中词放在正文尾部，验证搜索返回有限长度的命中片段，并通过 SQL 监听确认没有将完整 `search_documents.content` 投影到 Python。
- SQLite 使用 FTS5 `snippet()` 生成片段；仅摘要命中时回退正文前 240 字符。PostgreSQL 分支使用 `ts_headline()`。
- 搜索专项：5 passed。全量后端测试：216 passed、0 failed、25 warnings，85.59 秒。测试使用隔离 SQLite，不代表真实工作库已验证。

- 追加 `test_boot_summary_query_does_not_select_memory_body`：通过 SQL 监听验证 Boot 摘要查询只投影摘要和元数据，不选择 `memories.content`。搜索/Boot 渐进式读取专项共 5 passed。


### 最新 Boot / Search SQL 投影回归（2026-11-18）

- Boot 核心记忆读取只投影摘要和元数据；recent 只投影 URI 所需元数据；搜索使用 FTS 生成有限 snippet，不把完整记忆正文或完整 `SearchDocument.content` 读入 Python。对应 SQL 监听测试已存在并通过。
- 专项回归：56 passed，1 warning，35.08 秒。全量后端回归：216 passed，0 failed，25 warnings，92.69 秒；`git diff --check` 退出码 0。均为隔离 SQLite。
- 真实工作库文件仍返回 Windows `PermissionError`。对文件执行只读 ACL 授权尝试失败（`icacls` 退出码 5）；未读取、备份或迁移真实数据。
