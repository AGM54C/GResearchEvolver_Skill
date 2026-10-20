---
name: reviewer-panel
description: 对论文做独立视角的证据、方法、统计、表达与可复现性审查，产出可追踪的问题和验证要求。
---

提供统一稿件与证据包，先分别记录评审再汇总，避免后评审只复述前者。不同 persona 或同模型多次采样不自动构成独立专家证据；标明模型/角色/上下文/是否看过其他意见。

检查贡献与最近邻、理论假设、数据/对照/统计、结果绑定、鲁棒性、限制与复现。每项问题附位置、证据、严重性、反证、建议行动及验收条件；独立查证关键引用与重算关键结果。

使用保留缺陷集评价审稿器时，分自然与注入缺陷并设置简单基线、误报、precision/recall/exact-set。多数票/打分只辅助排序，不代表期刊接受或事实真值。

输出 issue IDs，交给作者 revise/retest，之后按相同问题再审；不能仅凭作者回复关闭问题。审稿风格可按任务选 references/reviewer-personas.md。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:reviewer-panel`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
