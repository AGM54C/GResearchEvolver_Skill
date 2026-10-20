---
name: statistical-analyst
description: 按独立分析单位进行数据质量检查、配对效应与区间、多重校正及受限 meta-analysis，报告假设和负结果。
---

先看冻结协议、数据词典、独立单位与缺失/泄漏处理，再选择统计方法。`data-audit` 提示重复、恒定变量、相同目标列与组跨划分；复杂时间/因果/预处理泄漏仍需人工检查。

`paired` 将同任务多 seed 先汇总，bootstrap 重采样任务而非种子；至少三个独立任务才给提升 CI，小样本仍不稳定。报告方向、原始效应、区间、样本量和任务覆盖；不以显著性替代实际意义。

`adjust` 提供 Holm/BH，要求原 p 值有效且 family 预先定义。`meta` 提供固定效应和 DerSimonian–Laird 随机效应、Q/I²/τ²，输入需同 estimand 与独立 study；少研究、依赖效应、稀有事件应用专门统计软件与敏感性分析。

其他领域检验可使用合适的 R/Python 库，在 workflow 记录命令、环境、数据与结果。不得为了使用内置函数改变研究问题。输出机器可读 results ledger 和解释，包含无信号、排除和失败分析。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:statistical-analyst`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
