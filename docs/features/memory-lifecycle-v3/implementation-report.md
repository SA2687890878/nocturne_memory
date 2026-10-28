---
title: 记忆系统 V3 实施与验证收据
lang: zh
---

# 记忆系统 V3 实施与验证收据

## A 当前结论与必须处理的例外

**隔离代码已实现并通过回归，但不能宣称本轮整体交付完成。**

活动库出现了未经本轮独立批准的 015 迁移。
开发目录未在新迁移落盘前完成隔离，这是本次执行失误。
具体触发进程尚未核实；现象与启动链自动加载新迁移吻合。
不以“没有主动执行迁移命令”替代对实际结果负责。

代码候选版本保留在隔离工作树，未合并、未提交。
原运行目录代码已恢复基线；这不等于数据库未发生过迁移。
没有执行批量正文、状态或关键词治理，也没有更新阅读插件。

## B 已实现的 V3 范围

| 范围 | 已实现行为 |
|---|---|
| 数据模型与升级 | Node 四值字段、DB 默认、NOT NULL、命名 CHECK、015 受控重跑 |
| 创建与更新 | MCP/REST/Graph 一致；创建省略使用 unspecified，显式 null 拒绝 |
| 状态与版本 | 更新 null 不变；纯状态更新不创建内容版本；别名共享状态 |
| 召回 | 搜索/近期/随机/自动关联默认排除 obsolete，过滤先于 LIMIT |
| 显式读取 | URI/树/索引/Boot 保留条目并显示状态与过时提示 |
| Review | 复用元数据差异；状态 CAS 回退；冲突保留整个待审组 |
| 快照 | 仅比较时忽略访问时间；仍保存完整快照 |
| 备份 | SQLite online backup、只读源连接与目标断言、精确完整性判断 |
| 审计 | 未标注/模板残留/冲突/过时 Boot 只提示，既有硬错误不降级 |
| 前端 | 复用创建/编辑/导航与 Review；四值选择和状态展示 |

设计依据：[V3 完整方案](<E:/myPrivateSpace/nocturne_memory/.agents/worktrees/memory-lifecycle-v3/docs/features/memory-lifecycle-v3/03-design.md>)。

## C 新鲜验证证据

| 检查 | 结果 | 证据 |
|---|---|---|
| 后端最终完整回归 | 198 passed，exit 0 | [JUnit](<E:/myPrivateSpace/nocturne_memory/.agents/worktrees/memory-lifecycle-v3/docs/features/memory-lifecycle-v3/backend-junit.xml>) |
| 前端最终完整回归 | 17 passed，0 failed，exit 0 | [前端测试报告](<E:/myPrivateSpace/nocturne_memory/.agents/worktrees/memory-lifecycle-v3/docs/features/memory-lifecycle-v3/frontend-tests.json>) |
| 前端生产构建 | 1799 modules，exit 0 | 隔离工作树构建产物；未启动浏览器或服务 |
| diff 检查 | git diff --check，exit 0 | 最终交付前再次核对 |
| 独立静态审查 | 未发现代码交付阻断项 | 一次全链路审查，加一次核心写入/回退对抗复核 |

后端启动器在收集前清除 TEST_DATABASE_URL 与 NOCTURNE_DB_URL。
测试使用临时 config.CONFIG_PATH 和逐项临时数据库。
项目既有开发测试依赖仅装入隔离工作树的临时目录。
没有修改系统 Python、依赖声明或 lock 文件。
前端复用已安装依赖，没有新增包。

一次中间回归为 196 passed、2 failed。
两条新备份测试误把公共 fixture 的数据库备份算入受测结果。
已将断言限定于受测源文件名，再跑完整回归得到 198 passed。
没有放宽生产约束，也没有跳过失败用例。

## D 活动库异常迁移的只读证据

证据：[活动库与既有备份核对](<E:/myPrivateSpace/nocturne_memory/.agents/worktrees/memory-lifecycle-v3/docs/features/memory-lifecycle-v3/live-migration-evidence.json>)。

| 项目 | 活动库 | 既有备份 |
|---|---|---|
| integrity_check | ok | ok |
| lifecycle_status 列 | 已存在 | 不存在 |
| 015 记录 | 已存在 | 不存在 |
| Node 总数 | 36（含根节点） | 36 |
| Memory 版本总数 | 38 | 36 |
| Edge / Path | 35 / 35 | 35 / 35 |
| 原生关键词绑定 | 8 | 8 |

015 的 applied_at 为 **2026-10-28 08:31:29 UTC**。
SQLite CURRENT_TIMESTAMP 使用 UTC。
现有 36 个 Node 的字段值全部为 unspecified。
未发现本轮执行批量状态分类的证据。

备份命名符合旧主文件复制方式，不是新的 WAL 安全备份标识。
虽然完整性通过，但它的 Memory 版本数量少于现库。
**不能直接用这份备份覆盖活动库。**

节点的原有业务列、Edge、Path 与关键词绑定摘要一致。
Memory 版本及访问日志摘要不一致，不能假装两份库等价。
本次未自动恢复、补迁移、清理记录或回退正文。

## E 只读治理预览

产物：[逐条候选清单](<E:/myPrivateSpace/nocturne_memory/.agents/worktrees/memory-lifecycle-v3/docs/features/memory-lifecycle-v3/deployment-preview.json>)。

- 默认 namespace 有 35 个有效、可达记忆节点。
- 35 个节点识别到旧状态模板与检索词模板。
- 清单包含 URI、建议状态、内容摘要校验值与候选差异。
- 检索表达若会丢失，标记需人工改写，不给自动删除差异。
- 关键词列出真实正文触发源及预览统计，没有实际绑定。

预览按源配置 URL 核对了实际 SQLite 目标。
默认快照路径没有找到 changeset 文件。
这**不能证明运行中的源待审池为空**。
运行时 URL/SNAPSHOT_DIR 覆盖尚未核准。
因此待审组数量和交叠数量在清单中标为 null，而不是零。

当前清单只是评审输入，不是可直接执行的批量治理授权。

## F 已做的隔离与尚未激活的约定

隔离分支为 memory-lifecycle-v3，基线为：

e123ce073ad49e870f19bbb5e2d19f0c35413467

新代码位于独立工作树，不再写入原运行目录。
已将原运行目录新增的迁移移到备份区，并恢复代码基线。
这只能阻止后续暴露，不能撤销已发生的数据库 DDL。

全局写作约定未提前切换。
[规则更新草案](<E:/myPrivateSpace/nocturne_memory/.agents/worktrees/memory-lifecycle-v3/docs/features/memory-lifecycle-v3/rule-update.md>) 需在新服务与工具字段验证后启用。
本文不把“字段已存在”视为“新版本已经正确部署”。

## G 未覆盖与残余风险

| 未覆盖或风险 | 当前处理 |
|---|---|
| PostgreSQL 实机迁移与并发 | 未验证，不批准 PostgreSQL 部署 |
| 浏览器视觉与真实页面交互 | 未启动服务，不声称已验收 |
| 活动服务实际加载的代码版本 | 未确认，不把源码恢复当作进程已恢复 |
| 运行时源待审池身份 | 未核准，禁止批量治理与清池 |
| DB 与 JSON 变更池非原子 | 保留既有限制，失败必须核对双方 |
| 既有备份内容落后 | 禁止直接覆盖恢复；需单独恢复评估 |
| 历史正文恢复出旧状态头部 | 只提示，字段仍是唯一真源 |

后端有依赖弃用警告与测试环境无 API_TOKEN 提示。
测试仅使用进程内 ASGI 客户端，未监听外部服务。
前端有 Browserslist 数据较旧及既有 api 动静态导入提示。
这些警告未隐藏，也未扩大范围处理。

代码隔离验证置信度：A（实际退出码与落盘证据）。
整个上线/治理就绪判断：B（存在现场身份与授权缺口）。

## H 下一步必须由用户决定

**建议先保留活动库现状，完成隔离代码评审，不立即回退。**

保留现状不意味着追认之后的批量治理或服务部署。
若用户要求恢复，先制定不丢失现有版本的恢复方案。
不得把当前较旧的备份直接覆盖回去。

后续放行前仍要核准运行服务版本、源待审池与单一迁移入口。
活动库、全局写作约定及 35 条治理候选均需独立确认。
本轮目标保留进行中，等待现场处置决定，不伪报整体完成。
