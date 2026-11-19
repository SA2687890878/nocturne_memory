# 词法检索负向查询评估（2026-11-19）

- 数据库：真实工作 SQLite，只读连接。
- 方法：复用当前查询规范化、人工短语别名、FTS5排序、obsolete过滤及 OR+partial fallback；未写数据库、未调用Embedding API。
- 查询数：25
- 无候选：13
- 有候选：12
- 返回候选数：27，人工核对 27/27 均与对应查询无关
- 排除范围不确定的婚礼主题 N11 后，确认域外查询 24 条，其中 11 条返回无关候选，域外查询候选返回率 45.8%

| ID | 查询 | 候选数 | 路径 | Top 3 |
|---|---|---:|---|---|
| N01 | 帮我规划一次东京五天四晚的自由行，安排景点和交通。 | 3 | or_partial | core://agent/delivery/testing；core://agent/delivery；core://agent/source-catalog |
| N02 | 今天北京天气怎么样，明天会不会下雨？ | 0 | none | — |
| N03 | 给我推荐几道适合周末做的川菜家常菜。 | 3 | or_partial | core://agent/delivery/testing；core://agent/delivery；core://agent/source-catalog/code-access/deva-cli-tooling |
| N04 | 解释一下光合作用的基本过程，适合小学生理解。 | 0 | none | — |
| N05 | 帮我写一首关于秋天落叶的现代诗。 | 2 | or_partial | core://agent/source-catalog；core://agent/delivery |
| N06 | 比较几款适合家庭使用的空气净化器。 | 2 | or_partial | core://agent/source-catalog；core://agent/environment/dsh-copilot-latency |
| N07 | 如何给阳台上的多肉植物浇水和施肥？ | 3 | or_partial | core://my_user；core://agent/environment/workspaces；core://agent/nocturne-memory |
| N08 | 推荐一部轻松的悬疑电影，最好不要太恐怖。 | 1 | or_partial | core://agent/environment/workbuddy-office-checkin |
| N09 | 帮我制定一个每周三次的跑步训练计划。 | 3 | or_partial | core://agent/delivery/testing；core://agent；core://agent/delivery/requirements |
| N10 | 解释欧元和美元汇率变化通常受哪些因素影响。 | 0 | none | — |
| N11 | 给婚礼现场写一段温馨的主持人开场白。 | 1 | or_partial | core://my_user/rewrite-consent |
| N12 | 怎么做一个松软的戚风蛋糕，列出材料比例。 | 2 | or_partial | core://agent/delivery/testing；core://agent/delivery/requirements |
| N13 | 介绍一下太阳系八大行星的特点。 | 0 | none | — |
| N14 | 帮我润色一封申请年假的邮件，语气礼貌自然。 | 0 | none | — |
| N15 | 推荐适合初学者的吉他练习曲和练习方法。 | 0 | none | — |
| N16 | 分析英超本赛季积分榜和争冠形势。 | 0 | none | — |
| N17 | 如何清洗白色运动鞋，避免鞋面发黄？ | 0 | none | — |
| N18 | 解释个人所得税专项附加扣除的申报流程。 | 1 | or_partial | core://my_user/visual-output-routing |
| N19 | 帮我设计一份适合露营的三天菜单和采购清单。 | 3 | or_partial | core://agent/delivery；core://agent/delivery/testing；core://agent/verification/test-design |
| N20 | 把这段中文翻译成法语，并保持商务语气。 | 3 | or_partial | core://agent/environment/deva-copilot-provider/codex；core://agent/environment/codex-copilot-provider；core://agent/environment/dsh-next-profile-acl-denied |
| N21 | 凤凰城周末家庭野餐菜单 | 0 | none | — |
| N22 | 量子纠缠实验历史 | 0 | none | — |
| N23 | 猫咪修剪指甲 | 0 | none | — |
| N24 | 古典吉他与钢琴音域 | 0 | none | — |
| N25 | 欧洲足球比分 | 0 | none | — |

## 结论与处理

- OR + partial fallback 是主要噪声来源：无关任务可能因为共享“计划、如何、推荐、流程”等通用词而命中交付规范、个人偏好或项目工具记忆。
- 本轮不直接提高生产阈值，因为正向改写集 Recall@10 为 18/18；阈值变化可能造成真实历史任务漏召回。
- Agent 调度层已补充 abstention 规则：任务不依赖个人历史时不检索；即使检索，也必须核对摘要与任务直接相关；弱相关候选不展开、不引用。
- N11 涉及用户既有婚礼主题，虽其返回候选不相关，仍单独标记为范围不确定，不纳入确认域外比例。

本评估是离线合成样本，不代表线上调度表现。客户端真实调用轨迹仍需后续取得。
