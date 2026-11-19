# 生命周期与摘要待复核清单（2026-11-19）

## 审计口径

- 真实工作库 SQLite 只读检查；没有更新 Memory、摘要或 lifecycle_status。
- 当前 111 个 Memory 版本、48 个当前有效版本、50 个 URI 路径和 50 条 SearchDocument。
- Node 生命周期统计：active 39、completed 1、obsolete 1、unspecified 10。
- 10 个 unspecified 节点中，1 个是系统根节点占位符；另 9 个有业务 Memory。
- Memory ID 111 曾是当前摘要缺失项，现已生成并通过 search_memory 回读验证；48/48 当前有效 Memory 均有摘要。此前“47 条当前 Memory”的报告已过时。

## 逐条复核建议

| Memory | URI | 建议状态 | 依据与限制 |
|---:|---|---|---|
| 79 | core://agent/environment/deva-copilot-provider | active | Deva 当前 Copilot bridge 的接入方式和请求约束仍有持续参考价值；具体凭据、端口和运行状态必须使用前核验 |
| 80 | core://agent/environment/toolchain/iqa-low-integrity-tests | completed | 记录的是一次特定测试环境诊断；保留历史排障经验，不代表当前机器权限仍相同 |
| 84 | core://agent/environment/zcode-weekend-build-limits | completed | 记录的是一次产品合规/接入评估结论；政策可能变化，重新使用前必须查当前官方规则 |
| 86 | core://agent/environment/toolchain/context-mode-deva-assessment | completed | 已形成“不常驻接入”的工具选型结论；Deva 能力变化时重新评估 |
| 87 | core://agent/environment/deva-engineering-layer | active | Deva 技能适配、共享规范和 DSH 只读边界属于持续工程背景 |
| 98 | core://agent/environment/workbuddy-office-checkin | unspecified | 内容混合网络限制、客户端行为和账号接入事实；高度依赖网络/版本/账号现状，现有证据不足以判定仍在使用或已失效 |
| 101 | core://agent/environment/toolchain/deva-cli-tooling-codegraph-rtk（含别名） | active | 当前 CLI 工具选用和安全边界可复用；CodeGraph 索引状态等动态信息仍需现场核实 |
| 102 | core://agent/environment/codex-copilot-provider（含别名） | active | Codex/Copilot bridge 协议兼容和配置约束仍有持续参考价值；模型清单和可用性必须按需验证 |
| 111 | core://agent/environment/dsh-next-profile-acl-denied | completed | 一次 DSH NEXT 启动故障的根因、修复与验证记录；适合作为复发时历史处置依据；摘要已补充并验证 |

以上是内容证据驱动的候选，不是数据库变更指令。completed 不代表删除或不再检索；unspecified 也不等于过期。当前没有足够证据把 98 标记为 obsolete。

## Memory ID 111 的摘要（已写入并验证）

> DSH NEXT 启动失败的根因是 profile 的部分文件和 pnpm store 文件使用受保护且阻断继承的 DACL，未授权当前交互登录用户读取；不是文件损坏或共享锁。修复方式是解除受保护 ACL 并继承父目录权限，随后以非提权进程验证整树可读。运行中 Electron lockfile/GPU 缓存的共享锁属于正常现象，不应误修。复发时先核实当前账户 SID、文件 ACL 和实际进程权限，不直接照搬旧路径或批量修改 ACL。

该摘要已通过 MCP update_memory_summary 写入 Memory 111，并通过 search_memory 回读确认状态 VALID。只更新摘要，没有修改正文或 lifecycle_status。

## 下一步

1. Memory ID 111 摘要已补齐；后续只需在确认历史故障已稳定解决后决定是否标记 completed。
2. 对 80、84、86、111 的 completed 候选、79、87、101、102 的 active 候选逐一确认后再调整生命周期。
3. 98 暂时保持 unspecified，直到核实当前是否仍在使用及网络事实是否仍成立。
4. 根节点占位符不参与业务生命周期统计。

**本次没有修改真实记忆库。**
