# MCP Tool Reference

> 本文档说明 Nocturne Memory MCP Server 的主要工具及其使用方式。
> 安装 MCP 后，AI 可以直接通过 tool docstring 获取这些信息，无需手动查阅。

---

## `read_memory(uri, detail="full", start_line?, end_line?)`
按 URI 分层读取记忆。原有单参数调用继续返回完整正文、metadata 和子节点列表；摘要与局部读取不会展开关联节点。

| 参数 | 类型 | 说明 |
|------|------|------|
| `uri` | `str` | 记忆的 URI，如 `"core://agent"` |
| `detail` | `str` | `full`（默认）或 `summary`；summary 只查询元数据和预算内摘要，摘要缺失不回退正文 |
| `start_line` | `int?` | 可选正文起始行，从 1 开始，包含该行；仅 full 支持 |
| `end_line` | `int?` | 可选正文结束行，包含该行，超出总行数时截到末尾；仅 full 支持 |

- 已知 URI 或语义候选先用 `read_memory(uri, detail="summary")` 判断相关性，摘要足够即停止。
- 只需局部原文时使用 `read_memory(uri, start_line=1, end_line=30)`，返回行号、总行数和版本 ID。该入口减少返回上下文，底层仍读取所请求记忆的正文后切片；不是数据库行级流式读取，也不是硬 Token 上限。
- 摘要、局部原文和完整正文是不同披露范围；可以补读尚未获取的范围，复用同一版本已读内容，版本变化后不要拼接新旧行段。
- 修改或删除前仍需读取完整正文；摘要或局部读取不满足这一要求。
- 系统 URI 保持原调用方式，不支持 detail="summary" 或正文行范围。

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

## `search_memory(query, domain?, limit?, include_obsolete?, include_partial?, token_budget?, include_snippets?)`
按关键词搜索记忆内容和路径。使用全文检索，不是语义搜索。默认返回 L0 元数据与预算内 L1 摘要；正文片段默认关闭，摘要缺失时不会自动展开全文。默认严格检索不会自动执行 OR/PARTIAL 兜底；只有显式 include_partial=true 才执行第二阶段。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | `str` | ✅ | 搜索关键词（词项全文检索） |
| `domain` | `str` | ❌ | 限定搜索域（如 `"core"`, `"writer"`） |
| `limit` | `int` | ❌ | 最大返回数量（默认 10） |
| `include_obsolete` | `bool` | ❌ | 是否包含 obsolete，默认 false |
| `include_partial` | `bool` | ❌ | 是否显式开启第二阶段部分匹配，默认 false |
| `token_budget` | `int?` | ❌ | 摘要估算预算，默认服务端配置 1200；0 只取 L0；不含元数据等开销 |
| `include_snippets` | `bool` | ❌ | 是否交付正文片段，默认 false；默认严格检索也不执行 SQL 片段提取 |


### 检索与披露建议

- 不知道 URI：先调用 `search_memory`，不要猜 URI。
- 摘要足够：直接使用搜索结果，不调用 `read_memory`。
- 首轮保持 include_partial=false；无结果且任务确实依赖历史记忆时，才考虑显式 include_partial=true。PARTIAL 候选必须核对匹配覆盖率、URI、摘要和主题，弱相关候选不要展开或引用。
- 显式 PARTIAL 阶段仍在数据库内计算有界片段作为匹配覆盖率证据，避免片段展示开关改变候选集合或排序；include_snippets=false 时不把这些片段交给模型。
- 需要原文细节：再调用 `read_memory(uri)`。
- 关键词表达明显不一致、怀疑漏召回：可调用 `semantic_search_memory`；它返回近邻候选，不代表相关性已确认。
- `sync_semantic_index` 是显式操作，可能调用 Embeddings API；普通 create/update/delete 不会自动同步向量。
- `diagnose_memory_backend` 检查当前 MCP 进程对数据库的读写能力。

## `semantic_search_memory(query, domain?, limit?, token_budget?)`

显式语义候选检索，可能调用配置的 Embedding API；不自动并入关键词检索。limit 为 1～50，默认 10；token_budget 使用既有摘要预算配置，默认 1200，0 只返回元数据，预算不含 URI 等格式开销。

- 返回前按当前 namespace、路径、活动 Memory ID 和生命周期核验，过滤已删除路径、旧版本和 obsolete；按节点合并别名，避免重复占用候选名额。
- 过滤后自动补足近邻候选，复用同一查询向量，不为补足重复请求 Embedding API。
- 直接交付预算内当前摘要，不查询记忆正文；摘要足够即可停止，缺失不回退全文。距离仍只是近邻距离，不能当作语义相关性置信度。
- 仅改摘要可能使索引语义变旧，版本校验不能代替完整 hash 对账；按需显式调用 sync_semantic_index。
