---
name: theory-prover
description: 把理论论断转成明确假设与形式化命题，调用可用 Lean 编译器并核查证明占位和公理依赖。
---

先核对自然语言论断、符号域、量词、边界情形和反例；选择实际适用的证明路线，避免“形式化了另一个弱命题”。

在用户项目的 Lean/lake 环境写证明，`tool proof` 编译并对指定 declaration 输出 axioms。禁止把 sorry/admit 当完成；公理白名单按数学任务明确审查。保存 lean-toolchain、lake-manifest 哈希、编译日志与命题对应表。

环境未安装或编译失败标 unverified，仍可交付证明草稿与失败义务。编译成功只验证形式命题与列明公理，不证明实验结论、自然语言对应关系或研究新颖性。不要声称完成了本地不存在的 Lean 验证。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
