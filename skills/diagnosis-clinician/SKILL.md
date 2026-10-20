---
name: diagnosis-clinician
description: 沿原始事件、数据变换与论断追溯失败，提出可检验的修复假设并用人工干预和重复对照验证。
---

把执行故障、证据错误、统计错误、推论越界和表达错误分开。先定位最早可观察到的坏依赖边，再提出多个候选根因；它不是已证明的潜在根因。每个判断附事件 ID、输入/输出/原文依据和反证。

无指标且工具失败先修执行；数据充分但结果为零时保留有效负结果；只有设计缺陷证据支持才改协议。独立 critic 检查假设，router 按证据选择局部修复、方法修复或重新设计。

用 research-control 保存前缀、建立未修改对照与干预分支，核查干预是否被遵循、外部状态与预算是否可比，重复运行。`tool intervention` 给出四类有限范围判定；样本不足、工具缺失、环境漂移和不遵循都应 inconclusive。

归因评估分自然/注入失败，加入位置/长度/全判错等简单基线，同时报告 precision/recall/exact-set、误报和多错误情况；总体 micro-F1 不能代替因果解释。可选白盒方法见 [适配器边界](../_shared/adapter-contracts.md)。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:diagnosis-clinician`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
