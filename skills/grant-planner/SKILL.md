---
name: grant-planner
description: 将有证据的研究目标转为基金申请的 aims、工作包、里程碑、风险与预算，核对征集要求。
---

读取具体 call、资助对象、期限、预算口径与评审标准。把已有发现、初步结果和预期结果分开；每个 aim 有假设、证据、可测成功标准和失败解释。

工作包标负责人、依赖、起止时间、交付物；风险写触发信号、缓解与替代路径。预算 quantity×unit_cost 用 `tool grant` 核对，声明币种、间接费用和资助方限制。

起草 significance/innovation/approach、资源、伦理及数据共享计划时只用实际材料。工具检查结构与算术，不替代资助资格/财务/伦理审查。交付完整申请草稿、依据矩阵和缺失项；不自动提交或联系资助方。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:grant-planner`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
