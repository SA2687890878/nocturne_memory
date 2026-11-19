# Deva / Nocturne 真实客户端调度抽查（2026-11-19）

## 范围与方法

只读检查本机 Deva 最近 20 个会话的会话 JSON：统计 tool_use 中的 Nocturne MCP 调用，以及新会话首条用户消息内由 Deva 自动附带的“记忆条目”文本块。未把会话数直接当成调度准确率。

## 观察结果

| 指标 | 结果 |
|---|---:|
| 抽查会话 | 20 |
| 自动注入 Deva 记忆块 | 20/20 |
| 注入块长度 | 2,142～3,550 字符 |
| 平均注入长度 | 2,989.8 字符 |
| 含 Nocturne MCP 调用的会话 | 12/20 |
| Nocturne 工具调用总数 | 63 |
| read_memory | 35 |
| search_memory | 20 |
| create_memory | 3 |
| update_memory | 2 |
| manage_triggers | 2 |
| add_alias | 1 |
| 显式 include_snippets=true | 4 次 |
| 显式 include_partial=true | 1 次 |

## 发现

1. **常驻注入是当前最明显的 Token 优化点。** Deva 全局 memory.json 有 21 条记录；最近 20 个会话均注入了记忆块，平均约 2,990 字符。部分记录是详细环境事实、工具踩坑和一次性排障结论，不符合“Deva 内建记忆只保留偏好与指针、工程事实由 Nocturne 按需读取”的既定分工。
2. **Agent 偶尔主动扩大搜索披露。** 抽查到 4 次 include_snippets=true、1 次 include_partial=true。其中一条 DSH NEXT 检索先返回了主题不匹配的候选正文片段；后续 PARTIAL 查询在显式展开后也返回了摘要和正文片段。说明仅有默认参数保护还不够，客户端可见工具描述需要更明确地约束首轮调用。
3. **不能据此认定 8 个未调用 MCP 的会话调度错误。** 是否需要记忆取决于任务内容；这些会话没有逐条人工标注“是否依赖历史记忆”，因此不计算调度准确率、无效检索率或证据命中率。
4. **Token 数值不做跨会话对比。** 会话中的 lastInputTokens / cache 字段受到模型、上下文长度和缓存影响，不能直接证明某项记忆策略节省了多少 Token。

## Deva 全局记忆与 Nocturne 对账

只读核对 Deva memory.json 的 21 条记录与 Nocturne 当前正文/摘要后，初步分类如下。这里的“覆盖”指 Nocturne 已有可定位的对应记忆，不代表 Deva 条目可以不经备份直接删除。

| Deva 条目主题 | 对账结果 | Nocturne 入口 / 处理 |
|---|---|---|
| 记忆分工 | 已覆盖 | core://agent/memory-governance/single-source-memory-retirement |
| 工程任务路由、数据库入口 | 已覆盖 | core://agent/delivery、core://agent/source-catalog/database |
| Copilot bridge | 已覆盖 | core://agent/environment/deva-copilot-provider |
| Nocturne 核心目标 | 已覆盖 | core://agent/nocturne-memory |
| 回复风格 | 已覆盖 | core://my_user/collaboration-preferences |
| DSH skills 适配层 | 已覆盖 | core://agent/environment/deva-engineering-layer |
| Deva 大输出 / RTK | 已覆盖 | core://agent/dsh/context-output、core://agent/source-catalog/code-access/deva-cli-tooling |
| 子代理使用约束 | 已覆盖 | core://agent/delivery/review |
| 性能对比口径 | 已覆盖 | core://agent/environment/dsh-copilot-latency |
| FlyClash / WorkBuddy 代理配置 | 已覆盖 | core://agent/environment/workbuddy-office-checkin |
| Nocturne stdio 的 NO_UI 启动约束 | 部分覆盖 | 现有 Nocturne 单一真源记录未承接该启动细节 |
| SQL Server DDL / tempdb 安全红线 | 部分覆盖 | database 入口有身份预检，但正文明确标记专项承接待完成；Deva 原规则暂时保留 |
| Deva 全局注入层结构 | 尚未找到对应记录 | 暂时保留 |
| Git 分支、凭据和命名硬约束 | 尚未找到完整对应记录 | 暂时保留 |
| 获批后连续完成独立任务切片 | 尚未找到对应记录 | 暂时保留 |
| Windows .bat 纯 ASCII 规则 | 尚未找到对应记录 | 暂时保留 |
| GitLab commit message hook 规则 | 尚未找到对应记录 | 暂时保留 |
| FlyClash DNS suffix 细节 | 尚未找到对应记录 | 暂时保留 |
| ACL 排障禁止破坏真实文件的探针纪律 | 尚未找到对应记录 | 暂时保留 |

**结论：** 12 条已有明确对应入口，2 条部分覆盖，7 条暂未找到完整承接。暂不改写或删除 Deva memory.json。下一步先把缺失的长期规则迁入 Nocturne 并生成摘要，再备份 Deva memory.json，将已完整承接的细节条目改成短 URI 指针；SQL Server 安全红线在专项规则完成验证前继续留在 Deva 常驻层。

## 本轮迁移落地（2026-11-19 15:27）

Deva memory.json 实际为 22 条记录。逐条核对 Nocturne 入口后，已完成：
- 新增并生成有效摘要的记忆：core://agent/source-catalog/database/sqlserver-ddl-safety、core://agent/delivery/engineering-workflow-guardrails、core://agent/delivery/non-destructive-file-diagnostics、core://agent/environment/flyclash-dns-suffix-matching、core://agent/environment/deva-global-injection、core://agent/environment/nocturne-mcp-client-launcher。
- 更新 core://agent/source-catalog/database，正式指向 SQL Server DDL 专项；该专项现在有独立 URI 与有效摘要。
- 对 Deva 22 条记录中的 19 条详细工程事实改为短 URI 指针；保留 3 条真正属于常驻层的用户目标/表达偏好/协作偏好。
- 修改前备份：C:\Users\huzhijun\.deva\memory.json.backup-20261119-1527。
- memory.json 正文字符数从 3,530 降至 1,772，减少 1,758 字符（49.8%）；文件字节数从 9,526 降至 5,558。条目数量保持 22，不删除任何条目。
- 6 条新增专题记忆和数据库父入口均已验证有效摘要；精确标题检索均命中目标 URI。此前审计发现的 Memory 112、114 两条缺失摘要也已按正文补齐。最新质量审计：当前有效版本 56，摘要缺失 0，摘要/索引不一致 0，重复候选 0，孤立 SearchDocument 0，路径 58 / SearchDocument 58。
- 语义索引增量同步成功：source/vector 均为 58，首次 upserted 10；摘要补齐后再次 upserted 2、unchanged 56、deleted 0，integrity_ok=true。

**边界：** 这是 memory.json 文件层面的常驻文本缩减，不是新 Deva 会话的实际注入 Token 实测。下一次新会话加载后需再抽查实际注入长度；本轮没有强制终止或重启 Deva 会话。SQL Server 旧安全句已改为明确指向专项 URI，不删除其保护意图。

## 本轮已实施

- 强化 search_memory 的 MCP 工具描述：首轮保持 include_partial=false 和 include_snippets=false；严格命中仍需主题核验；PARTIAL 仅在首轮候选直接相关后才二次展开；正文通过 read_memory(uri) 按需读取。
- 同步强化 docs/system_prompt.md 的首轮搜索与正文披露规则。
- 增加工具描述回归测试，防止客户端可见指引退化。\n- MCP 专项测试 59 passed、1 warning；全量测试此前 274 passed、25 warnings。

## 下一步

- 对 Deva memory.json 的 21 条记录逐条与 Nocturne 检索对账。先确保详细事实已在 Nocturne 有可检索入口，再把 Deva 常驻层收敛为少量长期偏好、硬约束和 URI 指针。迁移前备份，不直接删除未核实内容。
- 客户端需重新加载 MCP 工具定义后，新的工具描述才会进入模型上下文。
- 对真实会话做任务级人工标注后，再计算 V4.0 调度准确率。

## 验收边界

本报告是最近 20 个 Deva 会话的只读抽样，不代表所有客户端，也不代表所有任务。没有逐条标注的准确率指标保持“未测”。未修改 Deva memory.json、Nocturne 真实记忆正文、生命周期、向量库或快照。
