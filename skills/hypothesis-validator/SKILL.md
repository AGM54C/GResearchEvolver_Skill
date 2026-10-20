---
name: hypothesis-validator
description: 将科学假设转为可证伪的检验链，维护预注册、竞争解释、序贯证据条件与未通过结果。
---

写出 H0、备择、可观察预测与竞争解释，区分统计拒绝、机制支持和科学真值。冻结主要结局、数据使用、停止规则、选择过程与检验族；已看过数据的分析标探索性。

固定样本分析交 statistical-analyst。适应性 e-process 使用 `eprocess`：每个主 H0 要蕴含子 H0，e-value 需在过去历史条件下有效，记录 data_use 与独立 validity_review。输入公式论证由专家核验；程序仅累加，不证明这些前提。

不要相乘任意重复使用数据的 p 值，也不要把 p→e 转换当有效性的修复。阈值跨越最多支持前提下的单假设拒绝，不能自动宣称 FDR、因果机制或科学发现为真。

记录所有尝试、失败和负结果。探索后的 confirmatory 检验需要独立数据/有效选择性推断。计划中的对照/鲁棒性测试标 planned，真实执行后才能升级 executed。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:hypothesis-validator`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
