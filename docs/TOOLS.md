# MCP Tool Reference

> 本文档说明 Nocturne Memory MCP Server 的主要工具及其使用方式。
> 安装 MCP 后，AI 可以直接通过 tool docstring 获取这些信息，无需手动查阅。

---

## `read_memory(uri)`
读取一条记忆。返回内容、metadata 和子节点列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| `uri` | `str` | 记忆的 URI，如 `"core://agent"` |

**特殊系统 URI：**
- `system://boot` — 加载 Dashboard Settings / `config.json` 中配置的 Boot URIs；使用命名空间时优先读取当前 namespace 的配置，未设置时降级到全局 Boot URIs
- `system://index/<domain>` — 特定域名记忆索引
- `system://recent` — 最近修改的 10 条记忆
- `system://recent/N` — 最近修改的 N 条记忆
- `system://glossary` — 全量关键词库及节点引用映射
- `system://diagnostic/<domain>` — 记忆健康诊断报告（检出过时、拥挤、孤儿节点等结构性问题）

---

## `create_memory(parent_uri, content, priority, disclosure, title?)`
在指定父节点下创建新记忆。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_uri` | `str` | ✅ | 父节点 URI。强调联想相关性（What/主题），如 `core://user/health`，不要用无意义的容器如 `core://logs`。 |
| `content` | `str` | ✅ | 记忆内容（支持 Markdown） |
| `priority` | `int` | ✅ | 优先级（0=最高，数字越小越优先） |
| `disclosure` | `str` | ✅ | 触发条件：描述"在什么情况下该想起这条记忆" |
| `title` | `str` | ❌ | 路径名称（仅限 `a-z`, `0-9`, `_`, `-`）。不填则自动分配序号 |

```
create_memory("core://", "Bluesky 使用规则...", priority=2, disclosure="当我准备发 Bluesky 时", title="bluesky_manual")
```

---

## `update_memory(uri, ...)`
更新已有记忆。支持两种互斥的内容编辑模式：

**Patch 模式**（精确替换）：
| 参数 | 说明 |
|------|------|
| `old_string` | 要替换的原文（必须在内容中唯一匹配） |
| `new_string` | 替换后的新文本。设为 `""` 可删除该段落 |

**Append 模式**（追加）：
| 参数 | 说明 |
|------|------|
| `append` | 追加到内容末尾的文本 |

**Metadata 更新（可与上述模式组合）：**
| 参数 | 说明 |
|------|------|
| `priority` | 新的优先级 |
| `disclosure` | 新的触发条件 |

> ⚠️ **没有全量替换模式。** 必须通过 `old_string/new_string` 显式指定修改内容，防止意外覆盖。
> ⚠️ **更新前必须先 `read_memory`**，确认你知道自己在改什么。

---

## `delete_memory(uri)`
删除一条记忆的一条访问路径（不伤及记忆的正文）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `uri` | `str` | 要删除的 URI |

---

## `add_alias(new_uri, target_uri, priority, disclosure)`
为已有记忆创建别名路径。**不是复制**——是同一段内容的新入口，可以设置独立的 priority 和 disclosure。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `new_uri` | `str` | ✅ | 新的别名 URI |
| `target_uri` | `str` | ✅ | 指向的目标 URI |
| `priority` | `int` | ✅ | 此别名的独立优先级 |
| `disclosure` | `str` | ✅ | 此别名的独立触发条件 |

---

## `manage_triggers(uri, add?, remove?)`
为记忆节点绑定触发词，为记忆增加超越父子层级的横向召回通道。当任何记忆正文中出现该触发词时，系统会自动在底部显示指向该节点的超链接。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `uri` | `str` | ✅ | 目标节点 URI |
| `add` | `List[str]` | ❌ | 要绑定的触发词列表，如 `["Salem", "User"]` |
| `remove` | `List[str]` | ❌ | 要解绑的触发词列表 |

> 💡 **查询全局触发词库：** 执行 `read_memory("system://glossary")`

---

## `search_memory(query, domain?, limit?, include_obsolete?, include_partial?)`
按关键词搜索记忆内容和路径。使用全文检索，不是语义搜索。默认返回 L0 元数据与预算内 L1 摘要；正文片段默认关闭，摘要缺失时不会自动展开全文。严格检索无结果时最多返回 3 条 PARTIAL 兜底候选，默认省略其摘要。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | `str` | ✅ | 搜索关键词（词项全文检索） |
| `domain` | `str` | ❌ | 限定搜索域（如 `"core"`, `"writer"`） |
| `limit` | `int` | ❌ | 最大返回数量（默认 10） |


### 检索与披露建议

- 不知道 URI：先调用 `search_memory`，不要猜 URI。
- 摘要足够：直接使用搜索结果，不调用 `read_memory`。
- 默认严格检索无结果时可能返回最多 3 条 PARTIAL 兜底候选；默认不交付 PARTIAL 候选摘要以节省 Token；先检查匹配覆盖率和命中词，只有显式 include_partial=true 才查看摘要，弱相关候选不要展开或引用。
- 需要原文细节：再调用 `read_memory(uri)`。
- 关键词表达明显不一致、怀疑漏召回：可调用 `semantic_search_memory`；它返回近邻候选，不代表相关性已确认。
- `sync_semantic_index` 是显式操作，可能调用 Embeddings API；普通 create/update/delete 不会自动同步向量。
- `diagnose_memory_backend` 检查当前 MCP 进程对数据库的读写能力。
