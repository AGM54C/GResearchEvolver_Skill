---
name: rsi-evolver
description: 在冻结评估和预算下实跑策略候选与基线，按独立评分、回归和成本门槛决定提升或回滚；用于研究流程与策略改进。
---

将复盘结论记录为未验证经验：failure → evidence → candidate change → falsification test。生成不同修复策略，保留原策略与自测；文本反思、自写测试或自评分不能独立批准提升。

使用 `rsi-freeze` 固化 scorer 源码、任务、数据分区、种子、预算、评分方向、protected_checks、min_gain、max_task_regression、required_domains、max_trials。候选包包括提示/代码/自测/配置；固定评分器与核心授权机制不在候选可改范围。

先 development/selection；audit 实际运行 candidate 和 incumbent，再由独立 scorer 评分。任务级配对 bootstrap 下界严格大于最小收益、保护检查与回归/成本/覆盖门槛通过才 promote；平局保留 incumbent。失败/中断也消耗验收次数。final 只作一次报告，始终对照 freeze 时的 reporting_baseline，不用于提升。

active 是原子更新的整包快照；`rsi-rollback` 恢复整包，历史失败不删除。评估器改变需新 epoch，旧分数失效但产物保留；跨 epoch 要在固定外部 anchor 上实际校准，不以两边分数直接宣称改进。

本地评分进程与策略具有相同系统权限，**不是密封验收**；bootstrap 是近似门槛，重复自适应使用固定任务仍会过拟合。对不可信候选，需独立可信执行服务/权限隔离。不能把此软件测试称为开放 RSI、能力边界扩展或单调科研进步。

接口及示例见 [RSI 协议](../_shared/rsi-protocol.md)。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
