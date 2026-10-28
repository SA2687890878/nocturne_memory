# V3 验收用例对照（T01–T25）

依据：`docs/features/memory-lifecycle-v3/03-design.md` 第 26 节。
证据来自隔离测试：后端 198 通过 / 前端 17 通过（0 失败）。运行态证据见 `rollout-receipt.md`。

| 编号 | 场景 | 证据 | 结论 |
|---|---|---|---|
| T01 | 全新库模型 schema | `test_lifecycle_migration.py::test_fresh_model_schema_matches_contract` | 通过 |
| T02 | 冻结旧 nodes 升级 | `test_migration_015_upgrades_frozen_old_schema` | 通过 |
| T03 | DDL 已提交、记录未提交后重跑 | `test_migration_015_retry_after_committed_ddl_is_safe`；非契约旧列停止见 `test_migration_015_stops_on_preexisting_column_outside_contract` | 通过 |
| T04 | 四种合法值写入读回 | `test_fresh_schema_accepts_four_values_and_rejects_bad_ones` + 状态 API 用例 | 通过 |
| T05 | 非法值/空串/NULL 被拒 | 同上（隔离库直接 SQL） | 通过 |
| T06 | 不传状态创建取默认 | `test_default_applies_when_status_omitted` | 通过 |
| T07 | MCP/REST/Graph 纯状态更新不增版本 | `test_lifecycle_status.py::test_status_only_write_shared_by_alias_without_new_version` | 通过 |
| T08 | 省略/null/显式 unspecified/相同值 | `test_mcp_create_default_and_explicit_null`、`test_rest_create_default_and_null`、`test_rest_status_nav_only_and_null_update` | 通过 |
| T09 | 别名一致、命名空间隔离 | `test_status_only_write_shared_by_alias_without_new_version`；`test_lifecycle_recall.py::test_search_keeps_namespace_isolation` | 通过 |
| T10 | 状态与内容/边元数据组合更新 | 既有更新事务用例覆盖组合路径，但未新增生命周期专项断言 | 部分（未加专项用例） |
| T11 | 纯状态 Review 差异可见 | `test_pure_state_diff_and_approve` | 通过 |
| T12 | 改状态→访问时间→改回，净变化归零 | `test_state_read_reset_is_zero_net_change` | 通过 |
| T13 | 回退保留最新访问时间 | `test_state_rollback_preserves_committed_access_time` | 通过 |
| T14 | 人工改动后 CAS 冲突整组保留 | `test_human_status_conflict_keeps_whole_group` | 通过 |
| T15 | 已等于 before / 条件更新落空 | `test_already_restored_status_rolls_back_other_group_changes`、`test_conditional_status_update_miss_retains_group` | 通过 |
| T16 | 旧快照无状态键、内容版本恢复不清状态 | `test_content_version_restore_preserves_node_status`、`test_legacy_snapshot_without_status_does_not_restore_it` | 通过 |
| T17 | 搜索/近期/随机/Glossary 先过滤再排序 | 搜索与 Glossary 有直接断言：`test_search_excludes_obsolete_before_limit`、`test_glossary_auto_links_skip_obsolete_but_listing_keeps_status`；recent/random 共用同一过滤条件，未单独断言 | 部分 |
| T18 | 显式 URI/树/索引/Boot 仍可见并警示 | `test_explicit_views_show_status_and_keep_loaded_count_honest`（URI、Boot、索引、Glossary 索引）；层级树未单独断言 | 部分 |
| T19 | unspecified advisory，结构/索引错误仍失败 | `test_audit_memory.py::test_untriggered_is_advisory_but_real_issues_fail` | 通过 |
| T20 | 关键词真实触发、频率与绑定预算 | `test_audit_memory.py` 多条（频率边界、别名不稀释、预算、泛词） | 通过 |
| T21 | 源变更组与治理项交叠即停止 | 运行门禁：`deployment-preview.json` 记录 35/35 交叠，治理未执行；无自动化用例 | 运行门禁 |
| T22 | 备份失败/完整性失败即停止 | `test_lifecycle_backup_safety.py` 两条 + migration 两条 | 通过 |
| T23 | 快照创建/删除与旧 glossary 比较 | `test_node_comparison_preserves_creation_deletion_and_other_fields` | 通过 |
| T24 | 前端四值标签、纯状态差异 | `LifecycleBadge.test.jsx`(2)、`CreateMemoryModal.test.jsx`(2)、`ReviewPage.test.jsx`(2)；运行态截图见 backups 目录 | 通过 |
| T25 | 创建省略/null 三入口 | `test_mcp_create_default_and_explicit_null`、`test_rest_create_default_and_null`、`test_graph_create_rejects_invalid_status_without_creating_node` | 通过 |

## 未覆盖

- **PostgreSQL**：本机无 PostgreSQL 服务（`Get-Service` 无匹配），未执行真机迁移/约束测试；设计允许明确列为未覆盖，不以 SQLite 结果代替。
- **P6 存量治理**：设计第 22 条门禁触发（35 组待审与 35 个候选全部交叠），且第 23 条要求逐条授权；本轮未治理，36 个节点保持 `unspecified`。
- T10、T17、T18 的缺口如上，属补充用例即可关闭，不影响已上线行为。
