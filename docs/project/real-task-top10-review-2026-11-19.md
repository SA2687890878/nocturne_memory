# Nocturne Top10 检索评估补充（2026-11-19）

## 方法

使用当前真实工作库，通过当前 `search_memory` 实现对 18 条人工压缩关键词查询进行只读检索。参数：`limit=10`、`include_partial=false`、`include_snippets=false`、`token_budget=0`。未读取正文。

## 结果

| 指标 | 结果 |
|---|---:|
| 查询数 | 18 |
| 实际返回候选 | 23 |
| 目标命中 | 18/18 |
| 目标排名第 1 | 18/18 |
| Recall@10 | 100.00% |
| Precision@returned（grade≥1） | 86.96% |
| Precision@returned（grade=2） | 78.26% |
| Precision@10（grade≥1） | 11.11% |
| Precision@10（grade=2） | 10.00% |
| 未标注候选 | 0 |

## 解释与限制

- Precision@10 按标准固定分母 10 计算；未返回的排名槽位按不相关处理，因此在每条查询仅返回 1～3 条时，该指标会明显低于 Precision@returned。
- grade=2 表示直接回答；grade=1 表示有用的相邻上下文；grade=0 表示无关。
- 现有标注为模型辅助的摘要级初步判断，不是用户确认的最终真值。
- 本轮新增 4 条候选判断，依据仅为搜索结果中的 L0/L1 摘要和查询主题，不读取全文；相关性判断存在主观性。
- 18 条关键词由人工根据已知目标记忆构造，仍是受控实验，不是自动改写器盲测。
- `token_budget=0` 只用于测量导航/候选输出，不代表日常默认摘要预算；本次不把响应字符数换算成真实 Token。

## 产物

- `real-task-top10-reviewed-2026-11-19.json`：完整候选、逐条等级、指标。
- `real-task-qrels-reviewed-2026-11-19.json`：扩充后的暂定相关性标注。
