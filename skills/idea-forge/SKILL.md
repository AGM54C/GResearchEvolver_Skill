---
name: idea-forge
description: 从文献缺口和竞争解释产生多样的研究假设，按证据、可证伪性、强基线、预算和新颖性筛选。
---

先给出最近邻工作与未解决的具体问题。生成机制、任务、数据、评价、系统设计等不同来源的候选；允许变异/交叉，但保留候选谱系和失败，避免只优化同一评审偏好。

每个假设标明条件、变量、预期关系、竞争解释、可推翻它的观测、最强合理基线和最小区分实验。真值不可得时，明确代理指标的解释边界。

用带原文证据的 nearest-work matrix 和 `tool novelty` 检查查新记录；不把新名称或提示词组合称首创。可行性/收益分数只是决策建议，不是实测科学发现。保存 Pareto 候选，按预算选择实验；无信号时保留负结果并更新假设。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:idea-forge`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
