---
name: survey-architect
description: 综述架构师。从文献笔记与科学论断图组织综述结构（章节树）并撰写正文，交叉校验引用，标注证据断裂处与过度泛化。触发条件：给定综述主题 + 文献集，要求"写综述""组织综述""综述大纲"。
parameters:
  topic:
    type: string
    required: true
    description: "综述主题"
  graph_path:
    type: string
    required: false
    description: "论断图路径，默认 .codeartsdoer/.research/workspace/literature/graph.json"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/survey"
---

# survey-architect Skill

从论断图 + 笔记组织综述。**核心风险 = 过度泛化**（把特定条件下的结果扩张为更宽结论），本 skill 全程防这一点。

> **技术参考**：SCIRIGOR（证据图定位断裂处）、HypoKG（弱证据是否被升级为强结论）、「科学总结过度泛化」（检测条件丢失）。
>
> **验收标准**：综述按 `references/survey-qa-rubric.md` 打分；S1（条件保留）= 0 → 作废重写。

---

## 1. 工作流

### Phase 0：主题分解

把 `topic` 分解为章节树（含引言/方法族/应用/争议/开放问题）。章节粒度以「一章节一主题」为上限，禁止拆成碎片。

### Phase 1：文献聚类与证据归位

- 检索走 **G 路径**（HARNESS §4.6）：L0 粗筛 → 图定位（种子节点 + 1 跳扩展）→ 节点锚定生成。
- 用论断图 + 笔记把文献聚类到章节。
- 每条进正文的论断，精确回接 `graph.json` 节点（`claim_id`/`span`）。
- **条件保留（P0）**：论断的 `evidence.scope` 必须随陈述保留，禁止「A 在条件 S 下成立」被写成「A 成立」。

### Phase 2：分章节成稿

每章节正文遵守：
- 每条论断有 ≥1 条文献依据（回接 claim_id）
- 引用不同频段的结果时，保留各自工况（对象/条件/量值）
- 冲突（`refute` 边）必须显式并陈，不掩盖

### Phase 3：交叉校验 + 诊断报告

- 遍历正文，检查「过度泛化」（弱证据→强结论）与「证据断裂」（SCIRIGOR：数字/结论之间缺同源数据代码支持）。
- 附诊断报告块。

---

## 2. 产物

```
out_dir/
├── outline.md            ← 章节树
├── sections/<章节>.md     ← 各章节正文
├── references.md         ← 参考文献表（回接 claim_id）
└── survey.md             ← 合并稿
```

---

## 3. Gate Check

- 每个论断有 ≥1 条依据（回接 claim_id 或文献）
- 无「无条件断言」——凡是有限定条件的结论都保留了 scope
- 冲突（refute 边）已并陈
- 附诊断报告块（含 未决 列）

---

## 4. 诊断报告（必含维度）

| 检查项 | 判断 | 依据 |
|---|---|---|
| 过度泛化 | 有无 | 抽样对比原节点 scope |
| 证据断裂 | 有无 | SCIRIGOR 式支持链检查 |
| 引用可回接率 | 数值 | 正文 claim_id 匹配率 |