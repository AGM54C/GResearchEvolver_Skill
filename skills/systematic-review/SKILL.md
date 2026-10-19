---
name: systematic-review
description: 执行有冻结协议、独立筛选、冲突裁决、PRISMA 计数和偏倚评估记录的系统综述。
---

冻结问题框架、纳排标准、数据库与完整检索式、时间/语言边界、结局、研究单位、筛选人及修改政策（`review-freeze`）。按需采用 PICO/PECO 等框架，不强行把所有学科套成临床问题。

用参考文献库去重，保留每个原始记录及 alias；record/report/study 分别计数。同一研究多报告不能当独立研究。先双人 title/abstract，再 full_text；分别记录真正独立判断、理由与原文定位（`screen`）。

分歧进入第三人或明确共识会议裁决（`adjudicate`）；unavailable/uncertain/pending 不当作已排除。`review-report` 给 PRISMA 账目与待办，不画图。抽取需记录单位、分母、随访、效应与方差，并交叉核验。

按研究设计选择 RoB 工具，GRADE 逐结局记录五域和理由；`quality` 检查记录完整性，不冒充临床专家。兼容且独立的研究才进入 statistical-analyst 的 meta-analysis；异质性、依赖报告、选择性报告及发表偏倚需单独分析。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
