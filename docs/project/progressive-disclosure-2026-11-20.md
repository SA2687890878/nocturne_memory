# 个人记忆系统：分层读取与召回保持验收（2026-11-20）

## 本轮结论

已把按 URI 的摘要读取、正文行段读取和默认搜索的片段提取控制落实到服务端，并保留原有完整正文调用方式。本轮验收覆盖隔离自动化测试、真实工作库一致快照和新启动的 stdio MCP 协议；未把这些结果当成既有桌面客户端已经重载或真实模型用量下降的证明。

## 实际改进

| 目标 | 实现与边界 |
|---|---|
| 按需加载 | read_memory(uri, detail="summary") 复用元数据/摘要专用 SQL，不查询 memories.content、子节点或触发词；摘要缺失返回 MISSING，不回退全文 |
| 渐进式披露 | 已知 URI 和语义候选可先取摘要；需要局部证据时用 start_line/end_line，从 1 开始且包含两端；返回 Memory ID、总行数和原始行号，局部响应不附带关联节点 |
| 精准召回 | 本轮不修改 FTS 排名、分词、别名或语义融合策略；关闭片段时保留 PARTIAL 所需的内部有界证据，避免覆盖率和候选集合漂移 |
| 节省 Token | 默认严格 MCP 搜索不再执行 SQL snippet/substr 片段提取；已知 URI 无需为了取得摘要先读全文或重新搜索；复用同版本已读层级/行段 |

兼容性：read_memory(uri) 仍返回完整正文；原有系统视图调用不变；MCP 工具总数仍为 11。摘要读取使用既有 search_summary_token_budget，默认 1200，只限制摘要部分。行段读取是在所请求正文加载到进程后切片，不是数据库流式读取或固定 Token 上限。修改、删除前仍须读取完整正文，不能将摘要或局部读取当作已读全文。

## 自动化与协议验证

- 改动前专项基线：58 passed。
- 改动后 MCP/搜索专项：88 passed。
- 全量后端：295 passed，25 warnings，65.65 秒，退出码 0；使用原生 `.venv/Scripts/python.exe`。
- 新增 18 项回归，覆盖摘要无正文 SQL、缺摘要不回退、预算与 UTF-8、行段边界、非法参数、命名空间隔离、活动版本切换、默认搜索不提取片段、STRICT/PARTIAL 候选与排序保持。
- 新 stdio 进程实际完成 initialize / tools/list / tools/call：11 个工具；read_memory 已暴露 uri/detail/start_line/end_line，摘要与局部读取均成功。该进程只连接临时副本，关闭内置 UI，没有另起 uvicorn 或占用正式端口。
- 全量日志：`.tmp/pytest-progressive-full.log`；JUnit：`.tmp/pytest-progressive-full-20261120.xml`。25 条警告为既有 AnyIO/pytest 弃用提示及 localhost 测试的 API_TOKEN 提示。

首次直接运行测试复现了 SQLite FTS5 DROP 阶段的 `unable to open database file`。在同一原生 venv 解释器下，将 TEMP/TMP/TMPDIR 指向项目内独立可写目录后，基线与全量均通过。这个对照说明临时目录配置影响复现，不足以宣称所有同名 SQLite 错误都已修复。项目既有 `scripts/run-tests.bat` 已设置项目内临时目录。

## 真实工作库快照对照

数据与方法见 [机器可读结果](./progressive-disclosure-evaluation-2026-11-20.json)，可运行 [评估脚本](../../scripts/evaluate-progressive-disclosure.py) 重现。

- 沿用既有 18 条人工压缩关键词及对应自然语言问题，分别比较严格/显式 PARTIAL、片段开/关，共 72 组候选对照。
- 72/72 组除 snippet 字段外完全一致，包括返回顺序、摘要、版本 ID、别名和 PARTIAL 覆盖率；关键词严格检索 18/18 命中目标。
- 25 条既有负向查询严格首轮均为零候选。
- 对 18 个目标 URI，分别测量完整格式化响应、按 URI 摘要响应和前 3 行响应。后者是大小对照，不是假设前 3 行就足以回答任务。

| 完整响应指标合计 | 全文 | 摘要 | 前 3 行 |
|---|---:|---:|---:|
| 字符数 | 29,553 | 8,056 | 12,591 |
| UTF-8 字节/3 向上取整估算 Token | 14,080 | 4,032 | 5,885 |

摘要模式的完整响应估算 Token 比全文少 71.36%。这是同一批 URI 的可交付响应大小对照，不是供应商真实 Token，不是线上平均节省率；未计入工具 Schema 增量、客户端常驻注入、缓存或任务实际展开比例。该组查询是既有受控样本，不是新增盲测，也不用于声称检索精度进一步提高。

## 工作库保护

未对真实记忆正文、摘要、生命周期、向量索引或客户端配置做写入。本轮源库为 WAL 模式且只读 SQLite 打开失败；没有修改目录权限，也没有在未锁定的实时库上使用 immutable 模式。

评估脚本在 Windows 使用只读文件句柄排除已有及新写者，并确认没有 WAL 文件后复制到临时目录，再执行 quick_check。所有查询与协议验证都在副本上完成。额外隔离检查确认：副本字节一致、已有写者时拒绝复制、存在 WAL 文件时拒绝原始复制。评估结束后源库哈希与协议验证前快照相同，源目录未产生 WAL/SHM 文件。

复现命令：

```powershell
.\scripts\run-tests.bat -q --basetemp=.tmp/pytest-progressive-recheck
.\.venv\Scripts\python.exe -B -X utf8 scripts/evaluate-progressive-disclosure.py
```

评估默认将完整结果写入 `.tmp/progressive-disclosure-evaluation.json`。如需归档到文档目录，再用 PowerShell Copy-Item 复制；不修改真实库 ACL。

## 当前交付边界与下一步

- 已完成：本轮代码、隔离回归、工作库快照召回保持与响应大小对照、新 stdio 进程验收、文档同步。
- 尚未验证：Deva 正常重载后的真实会话调度、全文过度展开率、重复读取率和模型供应商 usage。当前未发现 Deva 进程或 8233 监听；未启动桌面客户端，也未以单独 HTTP 服务替代正式 DSH/stdio 入口。
- 下一轮优先用真实客户端新会话检查：独立任务不检索；续作先取项目摘要；只补充必要行段；默认不超 3 条正文；同版本内容复用。没有这些轨迹前，不宣称四项目标在客户端端到端全部达标。
- 自动查询改写盲测、扩大相关性人工标注和语义索引时效验证继续作为后续工作；本轮没有为了已有样本调整召回权重或启用自动向量回退。
