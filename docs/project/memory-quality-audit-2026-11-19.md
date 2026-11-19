# Nocturne 记忆质量只读审计（2026-11-19）

## 审计范围

- 数据源：config.json 当前指向的个人 SQLite 工作库。
- 审计方式：SQLite mode=ro 只读连接。
- 未修改真实记忆、摘要、生命周期状态、索引或快照。
- 可复现命令：D:\Python\python.exe scripts\audit-memory-quality.py。

## 结果

| 检查项 | 结果 | 判断 |
|---|---:|---|
| Memory 版本总数 | 111 | 包含历史版本 |
| 当前有效 Memory | 48 | 以每个 Node 最新且未 deprecated/migrated 的版本计算 |
| URI 路径 / SearchDocument | 50 / 50 | 正常 |
| 当前有效摘要缺失 | 0 | 48/48 当前 Memory 均有摘要 |
| 摘要与 SearchDocument 不一致 | 0 | 正常 |
| 不同 Memory 的完全重复内容组 | 0 | 未发现完全重复记录 |
| 缺失 Disclosure 的路径 | 0 | 正常 |
| 孤立 SearchDocument | 0 | 正常 |
| 生命周期 | active 39、completed 1、obsolete 1、unspecified 10 | unspecified 不擅自判过期 |

## 本轮补充：近似重复与生命周期复核

- 新增近似重复候选检测：对当前有效 Memory 的摘要计算字符三元组 Jaccard 与 SequenceMatcher 相似度；同一 Memory ID 的多个 URI 先去重。
- 本次结果：**0 组近似重复候选**。这只表示当前阈值下未发现摘要高度相似项，不等于语义层面绝对不存在重复。
- 检测阈值：SequenceMatcher ≥ 0.72，或 SequenceMatcher ≥ 0.50 且三元组 Jaccard ≥ 0.28。阈值用于生成待复核候选，不作为自动合并依据。

### 10 个 unspecified 节点的复核结论

| 记录 | 复核意见 | 处理 |
|---|---|---|
| 系统根节点占位符（无 Memory） | 非业务记忆，不应套用业务生命周期 | 保持原状 |
| core://agent/environment/deva-copilot-provider | 当前工具链配置与运行约束，具备持续参考价值；运行状态仍需按需核验 | 建议后续确认后设为 active |
| core://agent/environment/toolchain/iqa-low-integrity-tests | 历史测试环境问题，但保留了安全边界和复测提醒；没有证据证明彻底失效 | 保持 unspecified |
| core://agent/environment/zcode-weekend-build-limits | 活动/产品规则有时效性，当前有效性需重新核实 | 保持 unspecified |
| core://agent/environment/toolchain/context-mode-deva-assessment | 工具选型结论仍可参考，但 Deva 能力可能变化 | 保持 unspecified |
| core://agent/environment/deva-engineering-layer | Deva 技能适配与工程能力层仍是持续性工程背景 | 建议后续确认后设为 active |
| core://agent/environment/workbuddy-office-checkin | 网络、版本与客户端状态强时效，摘要已要求使用前核验 | 保持 unspecified |
| core://agent/environment/toolchain/deva-cli-tooling-codegraph-rtk（含别名） | 当前工具使用规范，仍有持续参考价值 | 建议后续确认后设为 active |
| core://agent/environment/codex-copilot-provider（含别名） | 当前 Codex/Copilot 接入配置与兼容约束，仍有持续参考价值 | 建议后续确认后设为 active |
| core://agent/environment/dsh-next-profile-acl-denied | 一次已完成的启动故障排查与修复记录；适合作为复发时的历史处置参考 | 已补摘要；建议后续确认修复稳定后设为 completed |

**生命周期没有自动修改。** 上表的 active 仅为候选建议；历史记录不等于过期，时效性事实也不能仅凭创建日期判 obsolete。需在实际配置/使用状态核实后再更新。系统根节点不参与业务生命周期治理。

## 需要正确理解的现象

1. core://agent/environment/toolchain/deva-cli-tooling-codegraph-rtk 与 core://agent/source-catalog/code-access/deva-cli-tooling 指向同一个 Memory ID（101）；这是两个访问入口，不是重复记忆。
2. core://agent/environment/codex-copilot-provider 与 core://agent/environment/deva-copilot-provider/codex 指向同一个 Memory ID（102）；同样是别名入口，不应合并或删除。
3. 两个没有 URI 路径的业务 Node 当前分别为 obsolete 和 completed；另一个是系统根节点占位符。当前没有证据要求修改它们。
4. 10 个 unspecified 节点（含系统根节点）复核后仍保留原状态；DSH NEXT 故障记录 id=111 已补摘要，生命周期仍待确认。
5. 63 条 deprecated 记录属于历史版本，不应被误报为当前摘要缺失。

## 结论

当前工作库没有发现索引摘要不一致、完全重复 Memory 或孤立搜索文档；且 Memory ID 111 的摘要缺失已修复并验证。V3.3 的第一步只读质量基线已建立。下一步重点是对 10 个 unspecified 节点做证据驱动的生命周期复核，并扩展近似重复检测；不自动合并、覆盖或删除任何真实记忆。
