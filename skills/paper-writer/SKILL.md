---
name: paper-writer
description: 从作者的证据和实际实验起草、修订论文，维护论断、数字、引用与跨章节一致性。
---

先定义论文类型、目标读者、中心论点与证据边界。维护 claim ledger、results ledger、引用库及章节状态；材料不足时可写明确的计划/占位，不把计划实验写成结果。

先确定故事骨架，再逐节起草与一致性协调；结果与方法版本一致。每个定量表达绑定 metric/condition/unit/run/value，不止白名单匹配一个数字。保存未经风格修改的基线稿；风格只改表达。

运行 `tool writing-audit` 覆盖正文、摘要、表格及说明文字；对每个数字提供精确字符区间，年份/章节/引用编号用 non_result 并给理由。引用 ID 存在检查之后，另行检查 entailment、否定、hedging、范围、因果词与限制。

模拟评审生成问题表后，使用版本化 revise/retest/rereview，更新相关章节与 ledger；不能仅改摘要而让表格和正文保留旧数值。交付稿件、账本、引用库与未决问题。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
