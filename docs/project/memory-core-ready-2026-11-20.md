# 个人记忆系统核心链路可用验收（2026-11-20）

## 交付结论

本轮已完成服务端核心链路和真实运行验收：按需检索 → 预算内摘要 → 必要行段/全文。修复了真实 stdio 首次语义调用阻塞，并清除了工作库向量索引的实际缺失和版本落后。客户端规则已保存、备份并回读；已有进程仍需通过客户端正常重载加载新工具 Schema。未把服务端协议验证当作桌面模型已执行正确调度的证明。

## 四项目标的落点

| 目标 | 已验证能力 |
|---|---|
| 按需加载 | 独立任务跳过记忆的客户端规则；搜索默认不交付正文；已知 URI 可只读摘要；语义候选的当前校验只查询元数据和摘要 |
| 渐进式披露 | L0 元数据 / L1 摘要 / L2 行段或全文；摘要缺失不自动展开；同一 Memory ID 已读层级和行段复用 |
| 精准召回 | 严格首轮与显式 PARTIAL；语义候选按当前 namespace、路径、版本、生命周期校验，过滤失效结果；别名合并后补足候选 |
| 节省 Token | 语义工具直接返回预算内摘要，省去另一次取摘要调用；补足候选复用查询向量；保留 token_budget=0 元数据模式和全文按需读取 |

语义距离依然不等于主题相关性置信度；版本核验不能保证摘要修改后的旧向量已经重新生成。实际完整 hash 对账见下方，不宣称任意未来写入都会自动同步向量。

## 本轮发现并修复的问题

1. 向量索引原有 58 个 URI，真实工作库有 59 个；缺失 1 项，另有 2 个 URI 的 Memory ID、hash 和元数据落后。备份后执行现有增量同步：upserted=3、deleted=0、unchanged=56。
2. 真实 stdio 请求在 sqlite_vec 导入其可选 numpy.typing 的原生库时阻塞，45 秒客户端超时；直接函数调用和隔离测试没有复现。线程栈定位后，改为直接加载已安装包内 vec0 扩展，使用与原包相同的 struct float32 格式，避免无关 NumPy 初始化。未修改第三方包、向量维度、模型或已有索引格式。
3. 语义结果以前仅给 URI；现在批量核验活动版本并返回当前摘要。旧版本、已删除路径和 obsolete 不占候选名额，别名不重复占位；缺额补足不再次请求查询 Embedding。

## 验收证据

- 最终全量后端：**310 passed，25 warnings，69.98 秒，退出码 0**。日志 `.tmp/pytest-memory-ready-final.log`，JUnit `.tmp/pytest-memory-ready-final-20261120.xml`。
- 本轮新增 15 项回归：失效版本/路径/生命周期、命名空间、别名去重、补足时仅一次 Embedding、摘要 SQL 无正文、预算、活动数据库路径覆盖，以及向量操作不得导入 NumPy。既有 18 项分层读取回归继续通过。
- 真实工作库和 sidecar 的只读快照对账：**59/59**；缺失、失效路径、完整同步 hash、版本和元数据不一致均为 0。见 [完整对照结果](./memory-ready-evaluation-2026-11-20.json) 和 [同步前后收据](./memory-index-sync-2026-11-20.json)。
- 实际新启动 stdio 进程连接**真实工作库 mode=ro**，通过真实 NVIDIA 查询 Embedding，Magpie 网关接入查询在 **Top1** 命中本轮补入的记忆；直接返回预算内摘要，不展开正文。完整调用约 5 秒，11 个工具正常加载。见 [真实运行记录](./memory-runtime-verification-2026-11-20.json)。
- 既有受控样本保持：关键词 18/18 目标命中；负向 25/25 严格首轮无候选；72 组片段开关对照的候选和排序不变。
- 18 个目标 URI 的完整摘要响应相对完整正文响应，UTF-8 字节/3 估算 Token 仍减少 71.36%。这是响应大小对比，不是模型供应商计费 Token，也不是所有任务的总体节省率。

## 客户端与数据保护

- Deva：仅更新已有 nocturne-memory 服务的 description，227→195 字；连接命令、参数、env 和其他配置逐项比对保持不变。备份 `mcp.json.backup-20261120-111026`。
- Claude Code：更新已有 nocturne-memory.md 规则，明确语义结果摘要复用、已知 URI 摘要读取、必要行段补读和默认正文数量；备份 `nocturne-memory.md.backup-20261120-111026`。
- 未强停用户正在使用的 MCP 或桌面进程，未另起 uvicorn 或开放端口。验证进程禁用内置 UI，结束后正常关闭。
- 原始工作库正文、摘要、路径和生命周期未写入；同步和运行验证前后工作库 SHA256 相同。向量 sidecar 只更新上述 3 项，备份已核验，路径记录在同步收据。
- 审计采用 SQLite 一致备份；必要时使用 Windows 排除写者的只读句柄和无 WAL 检查。源文件写入校验使用同一源文件前后 hash，避免把 SQLite backup 的物理页面差异误报为源库变化。

## 使用与复验

正常重载现有客户端的 Nocturne MCP 后即可使用本轮 Schema；不需要重建连接、改 namespace 或重新导入旧库。

```powershell
.\scripts\run-tests.bat -q --basetemp=.tmp/pytest-memory-recheck
.\.venv\Scripts\python.exe -B -X utf8 scripts/evaluate-progressive-disclosure.py --semantic-audit
D:\Python\python.exe -B -X utf8 scripts/verify-memory-runtime.py --query "Magpie 网关接入协议" --expected-uri "core://agent/environment/magpie-gateway-integration"
```

最后一条会显式调用一次已配置的查询 Embedding API；前两条测试/快照审计不调用 Embedding。后续真实客户端的无效检索率、重复读取率、过度展开率及供应商 usage 仍需实际会话采样；这些属于持续效果评估，不能从本轮服务端调用推算。
