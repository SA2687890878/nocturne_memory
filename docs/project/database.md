# 数据库设计

## 概述
项目使用 SQLAlchemy async 管理 SQLite 与 PostgreSQL；本地默认使用 SQLite，PostgreSQL 可用于远程/多设备部署。数据库连接与模型创建由后端管理，结构变化通过迁移目录维护。

## 核心表

| 表 | 职责 | 主键/关键字段 |
|---|---|---|
| `nodes` | 稳定的记忆概念身份 | `uuid`、创建/最近访问时间 |
| `memories` | 节点正文与版本链 | `id`、`node_uuid`、`content`、`deprecated`、`migrated_to` |
| `edges` | 有向父子关系及边级元数据 | `id`、`parent_uuid`、`child_uuid`、`name`、`priority`、`disclosure` |
| `paths` | URI 路径到图关系的映射 | 复合主键 `namespace/domain/path`，并含 `edge_id`、`node_uuid` |
| `glossary_keywords` | 关键词到记忆节点的绑定 | `id`、`keyword`、`node_uuid`、`namespace` |
| `search_documents` | 活动记忆的派生搜索文档 | 复合路径键、`node_uuid`、`memory_id`、正文及检索字段 |
| `memory_access_logs` | 记忆读取事件 | `id`、`node_uuid`、`namespace`、`accessed_at`、`context` |
| `presets` | Boot URI 预设 | `id`、唯一名称、Boot URIs、路径掩码、活动标记 |

SQLite 的 `search_documents_fts` 是 FTS5 虚拟表；PostgreSQL 对搜索文档建立 GIN 全文索引。它们服务于搜索，不是记忆图的事实源。

## 关系

- 一个 Node 可有多个 Memory 版本。
- Edge 分别通过 parent/child UUID 关联两个 Node；同一 parent-child 组合受唯一约束。
- 多条 Path 可以指向同一个 Edge；Path 也保存目标 Node UUID，namespace 参与路径隔离。
- GlossaryKeyword、SearchDocument 和 MemoryAccessLog 关联 Node；SearchDocument 还关联活动 Memory。
- Preset 独立保存启动配置；数据库以唯一索引保证同一时刻最多一个活动预设。

## 索引与约束

- 主键、外键和唯一约束保护身份、父子边、Glossary 绑定与活动预设。
- Node UUID 和访问时间等列建有辅助索引。
- 搜索派生表按 Node、Memory、domain 建立索引；SQLite 用 FTS5，PostgreSQL 用 GIN/tsvector。
- SQLite 连接开启外键约束、WAL、5 秒 busy timeout 和 NORMAL synchronous 模式。

## 初始化与迁移

数据库首次初始化时，在未检测到 `memories` 表的情况下按 ORM 元数据创建模型表，然后执行 `backend/db/migrations/` 下的迁移。升级时不要手工修改生产库结构；先阅读对应迁移和项目部署说明，并备份数据。

## 参考
- [ORM 表结构与约束](../../backend/db/models.py#L73-L271)
- [数据库连接、SQLite 设置与初始化](../../backend/db/database.py#L35-L103) · [初始化与迁移调用](../../backend/db/database.py#L125-L149)
- [搜索索引器](../../backend/db/search.py#L29-L40)
- [全文检索迁移](../../backend/db/migrations/009_v1.3.0_add_search_fts.py#L31-L99)
- [项目迁移目录](../../backend/db/migrations/)
