---
name: paper-writer
description: 论文写作。把综述、IDEA、复现结果、诊断报告组装成论文章节，引用对齐，防止「未决断言被写成确定结论」；存在风格画像（style-mimic 产出）时按画像执行语言层。触发条件：各产物齐备后要求"组装成论文""写论文""成稿"。
parameters:
  structure:
    type: string
    required: false
    description: "目标结构，默认 摘要/引言/方法/实验/结论"
  style_profile:
    type: string
    required: false
    description: "风格画像路径（style-mimic 产出）；缺省时自动探测 out_dir/style-profiles/ 下画像，无则跳过风格层"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/paper"
---

# paper-writer Skill

组装成文。**唯一硬约束：任何未决（真值未知、未复现、诊断存疑）的内容，不得被写成确定结论。**

> **验收标准**：成稿按 `references/writing-qa-rubric.md` 打分；W2（未决不写死）或 W3（引用真实）= 0 → 作废重写；启用画像时 W6（风格不碰红线）= 0 → 同样作废。

---

## 1. 工作流

### Phase 0：产物清单

收集 survey-architect / idea-forge / experiment-replicator / diagnosis-clinician 的产物与诊断块，确认引用源。

同时探测风格画像：`style_profile` 参数指定，或 `out_dir/style-profiles/` 下的画像文件。**画像只作用于语言层（怎么说），内容红线（说什么、数字、引用、未决标记）永远优先。**

### Phase 1：逐章起草（迭代协调，非一次组装）

按**信息依赖序**逐章起草（数字源头先写，聚合章节后写）：方法 → 实验 → 引言 → 结论 → 摘要（最后聚合）。

**跨章状态卡**（长文连贯的机制底座）：首个实质章完成后建 `paper-state.json`——

- 术语表：每个术语的规范形 + 首次定义章节（后文不得换叫法）；
- 数字账本：全文每个数字的规范值 + 出处（run 号/claim_id），后续章节引用数字只从账本取；
- 符号表：数学符号 → 定义处；
- 结论强度登记：每结论的已验证/待验证态（摘要与结论章起草时按此对齐措辞）。

后续每章起草前**必读状态卡**；引入新术语/新数字先入卡再入文（起草顺序靠后的章节因此天然前向连贯）。

**启用画像时**：先产出无风格基线稿（`paper.baseline.md`），再调用 style-mimic Phase 1 按画像执行语言层（句式/hedging 谱/连接词/opener；红线项原样保留）——双版本落盘供 Phase 2 红线 diff。

### Phase 2：引用对齐 + 跨章一致性迭代

- 引用回接到 claim_id / run 号。
- 未决项在正文中加显式标记（如「（未决）」），禁止模糊化。
- **一致性迭代**（W5 的执行机制）：跨章检查（数字对账 vs 状态卡 / 术语一致性 / 结论强度对齐）发现不一致 → **回流修订对应章节**（不就地硬改他章迁就）；修订后重查。**迭代上限 2 轮**，仍冲突的项显式列入诊断报告（含两侧原文与证据指针），不静默平均化、不擅改数字。
- 启用画像时：风格执行稿 vs 基线稿逐项 diff 数字/引用/claim 锚/未决标记（应零变化）；style-mimic Phase 2 的一致性报告随稿归档。

### Phase 3：成稿 + 诊断报告

---

## 2. 产物

```
out_dir/
├── paper.md                      ← 成稿（启用画像时为风格执行版）
├── paper.baseline.md             ← 无风格基线版（启用画像时留存，供红线 diff）
├── paper-state.json              ← 跨章状态卡（术语/数字账本/符号/结论强度）
└── style-consistency-report.md   ← 风格一致性报告（style-mimic 产出，启用画像时）
```

---

## 3. Gate Check

- 引用一致（正文引用 = 参考文献表）
- 无「未决」写成「确定」
- 状态卡在位：数字账本覆盖全文数字且每条有出处；术语无未登记的变体
- 一致性迭代记录留存（轮数 / 回流修订清单 / 未解决冲突已入诊断报告）
- 附诊断报告（列出所有未决项的落点）
- 启用画像时：红线 diff 零变化 + 一致性报告在位

---

## 4. 技术参考对照

| 机制 | 参考 |
|---|---|
| 逐章迭代协调（状态卡 + 回流修订） | PaperOrchestra（章节编排做长文连贯；本 skill 以状态卡实现同等机制，适配组装形态） |
| 起草顺序按信息依赖（数字源头先写） | 本 skill 设计（聚合章节后写保证摘要/结论不超前定调） |
