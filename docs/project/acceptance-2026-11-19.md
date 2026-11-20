# Nocturne 个人记忆系统验收记录（2026-11-19）

## 已具备并验证的能力

- 本地 Dashboard：`http://127.0.0.1:8233/`；API 健康检查：`/api/health` 返回 `status=ok`、`database=connected`。
- MCP HTTP / stdio 启动入口已配置；历史真实 stdio CRUD 验证完成。Claude Code 与 Deva 的 MCP stdio 配置均已存在；Deva 配置命令通过 initialize/tools-list 协议兼容性验证，11 个工具可加载；用户现已确认客户端能够正常使用 Nocturne 记忆系统。
- 真实工作库：SQLite `work-memory.db`。当前向量同步源包含 49 条有效记忆文档；摘要交付能力已验证，启动上下文按需只交付核心摘要。
- 语义 sidecar：`work-memory-vectors.db`，当前 49/49 向量元数据与向量记录一致；逐 URI 对账结果为缺失 0、过期 0、内容 hash 不一致 0。增量同步支持 hash 检测、变更 upsert、过期删除，Embedding 失败不破坏旧索引。
- `search_memory` 默认只交付 L0 元数据和预算内 L1 摘要，不附带正文片段；全文通过 `read_memory(uri)` 显式读取。
- `semantic_search_memory` 是独立候选通道，不把最近邻距离当作相关性置信度，也不默认混入词法搜索。

## 召回评估基线

来源：`real-task-retrieval-eval-2026-11-19.json`，20 个用户实际主题构造的离线案例，其中 1 个是启动入口，不计入词法搜索指标。

- 词法检索：19 个案例中 18 个在 Top10 命中，Recall@10 = 94.74%。
- MRR = 0.9123。
- 1 个词法漏召回案例由显式语义候选在 Rank 1 找回；该样本组合覆盖率为 100%。
- Precision@10 未计算：每个案例只有一个正例标签，未标注候选不能直接视为负例。
- 这是一份小规模、人工标注的离线基线，不代表线上生产遥测。

## MCP 工具描述优化（2026-11-19）

- `backend/mcp_server.py` 的 11 个 MCP 工具描述已统一精简为中文，参数说明同步精简；保留创建前查重、修改/删除前读取全文、语义候选需核实、语义同步可能调用 Embedding API 等边界。
- 新增 `docs/project/mcp-tool-descriptions.md`，作为工具描述和调用边界基准。
- 直接读取 FastMCP 工具注册结果，确认工具数为 11，工具名及参数字段/required 集合正常；本轮仅修改文档字符串和 Field.description，未改工具函数签名、默认值或执行逻辑。
- 本轮全量测试：271 passed、0 failed、0 errors，107.10 秒；日志：`.tmp/pytest-mcp-descriptions-final.log`。
- MCP 客户端需重启或重新加载 server，才能取得新的工具描述。

## 本轮测试情况

- 此前全量测试：271 passed、0 failed、0 errors，116.70 秒。使用全新独立 `--basetemp` 目录运行。上轮 115 errors 是复用残留锁定目录导致的测试环境问题，并非业务断言或生产连接泄漏。
- 语义同步新增覆盖：内容更新、增量新增、过期删除、Embedding 失败保持旧索引；语义同步专项 3 passed。
- 真实向量索引逐 URI 对账：49 条源文档、49 条索引记录，missing/stale/hash mismatch 均为 0；本次只读核对，没有调用 Embedding API。
- API `/api/health` 返回 HTTP 200，内容为 `status=ok`、`database=connected`；Dashboard 根页面 HTTP 200。
- 测试有 25 条既有警告，其中包含 API_TOKEN 未设置提示；服务当前仅绑定 localhost，但仍建议后续配置访问令牌。
- 本轮没有修改真实工作库数据，没有删除快照，没有提交 Git。

## 当前剩余工作

1. 客户端连接已由用户确认可用；后续仅在工具描述或配置变更后重新加载 MCP。
2. 增加更多真实召回案例，并对 Top10 候选进行人工相关性标注后再计算 Precision@10。
3. 继续保持语义检索显式调用；只有真实任务评估证明有收益，才考虑自动回退，避免每次搜索额外调用 Embedding API。


## 2026-11-19 最新运行态复验

- Dashboard/API 已重启，新的 run_sse.py 进程 PID 20580；/api/health HTTP 200，database=connected。
- HTTP MCP 实际连接成功：initialize 后列出 11 个工具，search_memory 自然语言改写查询正确命中 core://agent/dsh/context-output。
- 使用项目 stdio launcher 新启动独立 MCP 子进程进行真实 initialize/list_tools/search_memory 验收：11 个工具，检索成功。
- Memory 111 摘要已补齐，search_memory 回读状态 VALID；没有修改正文或生命周期。
- 最新只读质量审计：48/48 当前有效 Memory 有摘要，50/50 URI 路径有 SearchDocument，近似重复候选 0，摘要索引不一致 0。
- Claude/Deva 已有客户端会话中的 stdio 子进程未强制终止；需要客户端重载后才会切换到最新代码。
- 新增 V4.0 调度验收矩阵 12 条，尚未在真实客户端逐条采集工具轨迹。


## 2026-11-19 负向检索与调度收敛

- 新增 25 条词法负向查询评估：13 条无候选，12 条有候选；27/27 个返回候选经人工核对均与对应问题无关。排除范围不确定的婚礼主题 N11 后，24 条确认域外查询中 11 条返回无关候选（45.8%），13 条无候选。
- 确认 OR + partial fallback 可能把弱相关个人摘要带入候选列表；本轮未修改生产检索阈值，避免损害 18 条自然语言改写 Recall@10 100% 的现有基线。
- 已更新 docs/system_prompt.md：检索前先判断任务是否依赖历史记忆；候选必须直接相关；弱相关、通用词命中和兜底候选不展开、不引用；没有相关候选立即停止。
- 新增报告：lexical-negative-query-eval-2026-11-19.md / .json。
- 客户端真实 MCP 工具轨迹日志当前未找到可用记录，因此 V4.0 调度准确率、过度展开率和真实 Token 节省量仍未测；不虚报指标。

- PARTIAL 兜底标记与默认摘要抑制改动：检索服务、MCP 工具与命名空间专项回归 66 passed，1 warning；全量测试本轮未完成，不宣称全量通过。

- PARTIAL 兜底摘要抑制的 HTTP MCP 实测：重启服务后，health HTTP 200；域外查询返回 3 条 PARTIAL 标记、默认不返回摘要，Summary budget 为 0/1200；显式 include_partial=true 后可见摘要。相同改写正向查询仍命中 core://agent/dsh/context-output，摘要预算 92/1200。
- 对照修改前同一域外查询的默认结果曾交付 328 estimated tokens 的摘要；修改后交付 0 estimated summary tokens，本条样本节省约 328 个服务端估算 Token。该数值是单条离线验证，不代表全局平均节省。


## 真实客户端调度抽查（2026-11-19）
- 新增 real-client-dispatch-audit-2026-11-19.md：抽查最近 20 个 Deva 会话，记录常驻记忆注入与 Nocturne MCP 调用轨迹。
- 首轮搜索/正文片段的客户端可见工具描述已加强；新增回归测试。
- Deva 全局记忆收敛尚未实施，须先逐条与 Nocturne 对账。

- 本轮补充 MCP 专项回归：59 passed、1 warning；Nocturne 健康检查 HTTP 200，数据库 connected。\n

### Deva 常驻记忆精简（2026-11-19）
- Deva memory.json：22 条记录保留，19 条改为 Nocturne URI 指针，3 条偏好/目标继续常驻。
- 字符数 3,530 → 1,772，减少 49.8%；备份 memory.json.backup-20261119-1527。
- 新增 6 条专题记忆并补齐摘要；SQL Server 数据库入口已更新为专项引用。
- 语义索引增量同步：58/58 一致，10 upserted，0 deleted，integrity_ok=true。
- 新会话实际注入长度待 Deva 下一次新会话确认，未强制重启客户端。

- 最新只读质量审计：56 个当前有效版本摘要缺失 0；SearchDocument 摘要不一致 0；重复候选 0；孤立 SearchDocument 0；路径与 SearchDocument 均 58。\n
### 当前检索回归复验（2026-11-19 15:34）
- 真实工作库只读执行 18 条自然语言改写，按 Node UUID 归一化 URI 别名后 18/18 命中，Recall@10=100%，MRR=0.9352。
- 25 条负向查询中 14 条零候选，11 条仍返回 L0 候选；排除范围不确定的 N11，10/24 条确认域外查询有候选。PARTIAL 候选默认不附摘要/正文。
- 平均响应约 403 个粗估 Token（字符数/2.2），不是客户端 tokenizer 实测。
- 明细：docs/project/live-retrieval-regression-2026-11-19.json。未改生产检索逻辑。

\n### 两阶段披露修复验收（2026-11-19 16:10）
- 默认 include_partial=false 不再触发 OR/PARTIAL 兜底；只有显式 include_partial=true 才会执行第二阶段。
- 真实工作库：18条改写两阶段合并Recall@10=100%；6条首轮命中、12条二次PARTIAL命中。
- 25条负向查询首轮零候选25/25。
- HTTP MCP已重启验证：health 200、11工具可用，默认与显式PARTIAL行为符合预期。
- 详见 docs/project/live-retrieval-regression-2026-11-19.json。

\n### 全量回归（2026-11-19 16:12）
- pytest backend/tests -q：275 passed，25 warnings，退出码0，耗时97.46秒。
- 25条warning主要为pytest/AnyIO弃用提示及测试环境API_TOKEN未配置提示；本地服务仍绑定localhost。
- HTTP服务PID 6828健康检查200，数据库connected；HTTP MCP 11工具可用。


### 真实客户端注入复验与重复读取治理（2026-11-19 16:35）
- 直接解析 Deva 最新会话文件，确认 16:30 新会话已自动注入当前 memory.json 的全部 22 条精简记忆；注入块 2,238 字符。
- 与迁移前 14:52 会话 3,550 字符相比，实际注入文本减少 1,312 字符，下降 36.96%。这验证了客户端真实注入已生效，不再只是文件层面优化。
- Token 代理评估：cl100k_base 2,360→1,144（-51.53%）；o200k_base 1,922→976（-49.22%）。Deva 使用 DeepSeek V4.1 Flash，但实际 tokenizer/逐请求注入 usage 未暴露，以上仅为可复现代理值，不是服务端真实 Token。
- 最近 20 个会话均自动注入记忆块，长度 2,142～3,550 字符，平均 2,972.1 字符；该窗口跨越迁移前后，不能代表迁移后平均值。
- 最新会话 3 次 read_memory 中，同一专项 URI 重复读取 2 次。已强化 MCP read_memory 工具描述与 system_prompt 的同 URI 去重规则，并新增回归测试。
- 明细：docs/project/real-client-injection-token-audit-2026-11-19.md。


### 去重约束回归与服务更新（2026-11-19 16:37）
- 新增 read_memory 同会话 URI 去重工具描述约束及测试；MCP 专项 48 passed、1 warning。
- 全量回归：276 passed、25 warnings，101.50 秒，退出码 0。
- HTTP 服务已更新重启，PID 19168；/api/health 返回 HTTP 200、database connected。
- HTTP MCP initialize/tools/list 实测 11 个工具，read_memory 新去重描述已生效。
- 原 Deva stdio 进程 PID 28544 保持运行，未强制终止用户会话；该进程仍可能持有旧工具描述。下一次新会话/重载 MCP 后会加载新描述。
- 工具说明基准文档同步修正，明确首轮严格检索不自动执行 PARTIAL，避免文档与当前实现不一致。

### 真实会话重复读取率基线与 Deva 配置补强（2026-11-19 16:40）
- 55 个真实 Deva 会话：148 次 read_memory，其中 25 次同 URI 重复读取，重复调用率 16.9%；最近 20 个会话为 6/41（14.6%），最近 10 个会话为 2/20（10.0%）。
- 最新会话仍存在同一专项 URI 重读，说明 MCP 工具描述更新尚未被当前 stdio 进程加载，不能宣称去重已在客户端行为层生效。
- 已修改用户级 ~/.deva/mcp.json 的 Nocturne server description，明确：严格检索优先、PARTIAL 显式第二阶段、同会话同 URI 读取后复用。原配置已备份，JSON 校验通过。
- 下一次客户端 reload/restart 后采集新会话，验证真实重复读取率是否下降；本轮不强制终止 Deva 进程，避免打断会话。
- HTTP 服务健康检查 HTTP 200，数据库 connected；全量测试 276 passed、25 warnings。

### 常驻注入导航去重（2026-11-19 16:45）

- Deva memory.json 重复 URI 导航已合并：22 条降至 17 条，条目内容 1,772→1,510 字符（-262，-14.8%）；7 条原始规则描述全部保留在两个合并条目中。
- 已备份原文件 ~/.deva/memory.json.backup-20261119-164522；Nocturne SQLite 正文库未修改。
- 客户端尚未加载本次精简：运行中的 Deva/MCP 进程启动于 16:29，16:43 会话仍使用旧版 22 条注入。
- 最新重复读取审计：最近10会话 2/20（10.0%），最近20会话 6/41（14.6%），全部55会话 25/148（16.9%）；16:43 会话 3 次读取中有 1 次同 URI 重复。
- 不能将配置文件修改当作客户端效果；需待 Deva 重载后重新采样。

### 索引导航与正文读取预算（2026-11-19 16:50）

- 真实 Deva 新会话验证：精简注入已生效，注入 2,238→1,896 字符；cl100k_base 代理 1,144→1,039 Token，o200k_base 976→869 Token。
- 新会话重复读取为 0，但 60 次读取全部是不同 URI；先读取 system://index/core 后又展开大量节点，产生 91,648 字符工具响应。判定为索引过度展开，不算按需加载达标。
- 已将索引说明改为“导航地图，不是待读清单”，并规定默认每任务最多读取 3 条直接相关正文；read_memory 工具描述和 system_prompt 同步强化。
- 新增回归测试覆盖索引提示和读取预算；全量测试 277 passed，25 warnings。
- 新代码尚未进入运行中的 Deva stdio MCP 进程；需客户端下一次重载后实测。

### Deva 索引导航约束同步（2026-11-19 16:53）

- 16:53 已同步更新 Deva 用户级 mcp.json 的 nocturne-memory description，明确索引仅导航、禁止全域遍历、每项任务默认最多读取 3 条正文；JSON 校验通过，备份为 ~/.deva/mcp.json.backup-20261119-165314。
- 当前运行中的 stdio MCP PID 4000 启动于 16:46:58，早于本轮代码/工具描述修改；未强制终止。下一次客户端重载后才会应用新描述，需用新会话继续验证。
