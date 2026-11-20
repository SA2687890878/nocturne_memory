# Nocturne 当前运行验收快照（2026-11-20）

> 同日最新验收：全量 310 passed；工作库 sidecar 增量更新 3 项后 59/59 完整对账；修复 stdio 可选 NumPy 导入阻塞，真实 stdio/NVIDIA 查询 Top1 命中新记录且直接交付摘要。见 [核心链路可用验收](./memory-core-ready-2026-11-20.md)。已有客户端进程需正常重载；长期会话 Token 指标仍未测。

> 同日后续进展：分层读取扩展已完成，原生 venv 全量 295 passed；新 stdio 进程已在真实库隔离副本验证摘要/行段调用。详见 [分层读取与召回保持验收](./progressive-disclosure-2026-11-20.md)。下文为扩展前的历史检查结果；真实客户端重载与供应商 Token 仍待采样。

## 自动化回归

- `backend/tests`：277 passed，25 warnings，114.11s，exit code 0。
- 单独复测此前 SQLite/FTS5 失败用例：1 passed，1 warning，1.30s。
- 本次使用宿主 Python `D:\Python\python.exe`，并加载项目 `.venv\Lib\site-packages`。不是直接使用 `.venv\Scripts\python.exe`，因此原生虚拟环境解释器仍待验证。
- 此前 `unable to open database file` 本轮未复现；未定位根因，不能声称已修复。

## 当前 MCP / 客户端运行状态

- 对 `http://127.0.0.1:8233/api/health` 和 Dashboard `/` 的只读探测均返回 WinError 10061（连接被拒绝），当前 HTTP MCP 服务未在该地址监听。
- Deva 客户端仍处于关闭状态。此前正常启动尝试被宿主 SAFE 模式拦截；未关闭安全层或绕过限制。
- 源码和 Deva 配置已包含关键词压缩、L0/L1预算选择、摘要优先、正文按需读取、同URI复用、索引只导航规则；配置文件存在不等于客户端运行时已加载。
- 此前 stdio MCP 进程的工具描述与只读检索验收属于历史结果，不能代替当前客户端运行时验收。

## 已有产品效果证据

- 受控关键词检索对照：18/18目标命中；人工压缩关键词严格首轮18/18，较自然语言长句减少50% MCP调用、响应字符减少55.3%。这是人工改写受控实验，不代表自动改写器盲测。
- L0 与摘要预算对照：候选集合与目标召回保持18/18；L0服务端估算Token减少42.41%。该数值不是模型供应商真实Token，也不含客户端注入及其他上下文。
- Top10摘要级标注评估：Recall@10 100%；Precision@returned（grade>=1）86.96%；Precision@returned（grade=2）78.26%。标注是模型辅助初判，不是用户确认真值。

## 交付判断

- 核心检索与披露逻辑已具备代码、测试和受控评估支撑。
- 自动化全量回归本轮通过。
- 最终交付仍需完成：原生 venv 解释器复验、HTTP/stdio MCP当前进程验收、Deva正常启动后的真实会话验证、自动查询改写盲测及真实模型Token采样。
- 未修改真实工作库、NVIDIA凭据或向量索引；未提交Git。
