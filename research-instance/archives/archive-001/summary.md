# 会话摘要（archive-001）

**一行总览**：lit-retrieval v2 检索→建图→诊断→干预验证：两大创新点首次全链路落地 | 3/3 Validated，PM=1.0，2 经验入库 | completed（追溯性补归档，非实时记录）

## 分析

- v2 三源检索（arXiv/OpenAlex/Crossref，S2 限速降级缺席）暴露 3 类实现缺陷：去重键不归一（×3 双身份入库）、`&` 后台落盘竞态（5 文件散落）、S2 30s 间隔硬重试无效
- rsi-1 进化闭环：reflect（四短板 + 两实现缺陷）→ evolve（literature-miner/scholar SKILL.md 五项修复，commit `0ef82db`，git revert 即回滚）→ distill（2 条经验入库）
- L1-L6 依赖图诊断（8 节点 13 边）：裁决 DE-1/DE-2 为决定性错误、S2 429 为被补偿失败、计划性冗余 0
- I1-I3 分级干预真实重放 3/3 Validated；PM=1.0（缺陷单元尺度——协议 §4 补丁后；实测发现里程碑尺度分母失义并已修补 intervention-protocol.md）
- 干预蒸馏：INT-3 增量入 multisource-retrieval-pitfalls（30s 不够、降级更激进）；INT-1/2 为既有经验的验证回链

## 核心请求与意图

用 rsi-1 真实失败轨迹验证「快速定位（L1-L6 管线）+ 分级干预（I1-I3 协议）+ 干预蒸馏闭环（Validated → rsi-evolver → 策略）」两大创新点端到端可执行。

## 关键概念

去重键归一化（arXiv-ID/DOI 双键）；并行后台落盘竞态；被补偿失败 vs 决定性错误 vs 计划性冗余；干预判定四类（Validated/Partially/Refuted/Inconclusive）；PM 备选尺度（缺陷单元）；验证过的干预 → 可复用经验（DoVer/AGDebugger 止步于人工修复处）

## 待办

- S2 引用图数据缺席（`EVIDENCE_MISSING`，限速未解）
- E-10（KGHaluBench）refute 定性待全文核验
- 44 篇相关文献仅精读 6 篇（摄取预算约束）
