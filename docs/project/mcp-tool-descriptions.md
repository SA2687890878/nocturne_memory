# Nocturne MCP 工具说明

工具描述面向模型调用决策，遵循“做什么 + 关键边界”，不重复实现细节。参数说明只保留用途、默认值和不可违反的限制。工具名、参数名、类型、默认值和执行逻辑不因文案优化而改变。

| 工具 | 简要说明 |
|---|---|
| `read_memory` | 按 URI 读取记忆正文或系统视图。需要原文、代码、接口或参数时调用。 |
| `create_memory` | 在指定父节点下创建记忆。创建前先搜索，确认没有可复用的已有记忆。 |
| `update_memory_summary` | 保存指定记忆版本的 AI 摘要；传入空字符串可清除摘要。 |
| `update_memory` | 更新记忆正文或元数据。调用前必须先读取该 URI 的完整正文；仅更新传入的字段。 |
| `delete_memory` | 删除指定 URI 路径。删除前必须读取完整正文并确认确需删除；若存在不能安全删除的子节点，工具会返回处理提示。 |
| `add_alias` | 为已有记忆创建别名 URI；别名与原记忆共享同一份正文，不会复制内容。 |
| `manage_triggers` | 为记忆节点添加或移除触发词；触发词应已出现在记忆库正文中。 |
| search_memory | 按路径和关键词全文检索，默认只返回严格命中；首轮无自动 PARTIAL 兜底，显式 include_partial=true 才执行第二阶段；默认不返回正文片段，需核验相关性。 |
| `semantic_search_memory` | 按语义相似度检索候选记忆。结果只是近邻候选，不代表相关性已确认；使用前应读取正文核实。 |
| `diagnose_memory_backend` | 检查当前 MCP 进程对记忆 SQLite 数据库的读写能力；写入测试会回滚，不修改记忆数据。 |
| `sync_semantic_index` | 增量同步语义索引。可能调用配置的 Embedding API；API 失败时保留原索引。 |

## 调用边界

- `search_memory` 默认只交付元数据和摘要；需要原文时再调用 `read_memory`。
- `semantic_search_memory` 返回近邻候选，不是相关性判断；使用前读取正文核实。
- `create_memory` 前先搜索已有记忆，优先复用或更新，避免重复。
- `update_memory` 和 `delete_memory` 前必须读取完整正文。
- `sync_semantic_index` 是显式操作，可能调用配置的 Embedding API。
- 文案精简不改变参数 Schema、默认值、权限控制或业务行为。
