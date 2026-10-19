---
name: rebuttal-drafter
description: 评审意见回应起草。把 reviewer-panel 的模拟评审或用户贴来的真实审稿意见逐条 triage（可反驳/需补实验/应让步），生成逐条编号的 rebuttal 草稿与 cover letter；每条反驳必须有 run 号/claim_id/文献锚支撑，无证据的回应显式建议让步——禁止编造数据回应评审。触发条件：要求"写 rebuttal""回应审稿人""回复评审意见""投稿信/cover letter"。
parameters:
  reviews_path:
    type: string
    required: false
    description: "评审来源：reviewer-panel 的 review.json 或用户提供的评审文本路径"
  paper_path:
    type: string
    required: false
    description: "被评审稿路径（证据回接底座）"
  venue:
    type: string
    required: false
    description: "目标 venue（决定 rebuttal 格式惯例：字数/结构/语气）"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/rebuttals"
---

# rebuttal-drafter Skill

逐条回应。**硬约束：每条反驳要么有证据锚（run 号/claim_id/文献条目），要么显式建议让步——评审逼你要数字时，没有就是没有，编一个数字回应是反捏造红线在 rebuttal 场景的直接违反。**

> **验收标准**：按 `references/rebuttal-qa-rubric.md` 打分；B2（证据锚完整）或 B3（无编造）= 0 → 草稿作废。
>
> **诚实边界**：rebuttal 是**草稿**，语气分寸与最终措辞由作者定夺；「应让步」条目不伪装成可反击。

---

## 1. 工作流

### Phase 0：评审意见解析

1. 输入归一：review.json 直接读；自由文本评审（用户贴的真实意见）→ 解析为同构条目（编号/评审人/原文引述）；
2. venue 惯例确认：字数限制（如 ACL 500 词/NeurIPS 无硬限）/ 结构（逐条 vs 主题分组）/ 语气惯例；
3. 意见拆原子：一条评审意见可能含多问（「实验少且基线旧且没显著性」= 3 问），拆开编号。

### Phase 1：逐条 triage（三分档）

对每条原子意见判定：

| 档位 | 判据 | 处理 |
|---|---|---|
| **可反驳** | runs/ 目录有对应 run 号 / claim 锚有支撑 / 文献库有反例 | 反驳段：观点 + 证据锚 + （可选）原文位置澄清 |
| **需补实验** | 证据不足但实验可行 | 如实说「已在补充中」**仅当实验真的在设计/执行中**（回接 experiments/ 的 plan）；否则标「建议回复：我们承认并列为未来工作」——不虚构进行时 |
| **应让步** | 评审对（错误/局限确实存在） | 诚实承认 + 限定损失范围（「该局限影响 §5.2 的 X，不影响主结论 Y，因为 Z 锚」） |

**triage 依据落盘**：每条判定记录证据指针（run 号/claim_id/文件路径），无可指的 → 只能进「应让步」或「需补实验」。

### Phase 2：rebuttal 起草

- 结构：感谢段（短）→ 逐条编号回应（引述评审原句 → 回应）→ 总收尾；
- 语气：对事不对人、不过度道歉、不让步也不傲慢；harsh 意见保持专业（学审稿文化的「respond to the point, not the tone」）；
- **红线**：数字全部来自 runs/ 与成稿（逐项与 repl 报告对账）；「未决」结论不得在 rebuttal 中升级为确定；补实验承诺只写已存在的 plan；
- 字数按 venue 惯例分配预算（重大问题优先占额度）。

### Phase 3：cover letter + 对账报告

- cover letter（投稿信）：贡献一句话陈述 + 与 venue 契合声明 + （首次投稿）无重复投稿声明——不夸大，不替编辑做判断；
- 对账报告 `rebuttal-ledger.md`：意见总数 / 三档分布 / 每条证据指针 / 无锚条目清单（应为空，除非标了让步/补实验）。

---

## 2. 产物

```
out_dir/
├── rebuttal.md           ← 逐条编号草稿（含 triage 档位标注，作者可删）
├── cover-letter.md       ← 投稿信草稿
└── rebuttal-ledger.md    ← 对账报告（证据指针审计）
```

---

## 3. Gate Check

- 每条意见有回应（含应让步的显式承认，无遗漏）
- 全部反驳段证据指针可回接（ledger 对账平衡）
- 无编造数字 / 无虚构「实验进行中」 / 未决未升级
- 字数与结构符合 venue 惯例
- cover letter 无 over-claiming

---

## 4. 与其他 skill 的边界

| 能力 | 本技能 | reviewer-panel | experiment-designer |
|---|:--:|:--:|:--:|
| 评审意见生成 | ❌ | ✅（本 skill 的上游） | — |
| 逐条回应 + 证据锚 | ✅（独有纪律） | — | — |
| 补实验设计执行 | ❌（只回接已有 plan） | — | ✅（「需补实验」档的出口） |

---

## 5. 技术参考对照

| 机制 | 参考 |
|---|---|
| 逐条编号 + 原文引述 + 分档回应结构 | Rebuttal-Skill（★480）/ chtc66 academic-skills rebuttal 惯例 |
| 语气分寸（respond to the point） | 学术审稿回应文化惯例 |
| 证据锚纪律（无锚不让步不反驳） | 本 skill 独有（反捏造红线延伸；run 号/claim_id 体系为底座） |

---

## 6. 运行机制（遵守 HARNESS.md）

- **工具调用**：对账用确定性匹配（ledger 中每个指针 grep 落盘文件），失败标 `dangling_ref` 并禁用该条反驳段（降级为让步）。
- **错误恢复**：E6 幂等（同评审 + 同证据库 → 同 triage 分布）；真实评审文本解析失败条目标 `unparsed` 给人工，不猜测。
- **人的介入**：H1（triage 分档存疑时给选项——尤其「需补实验」vs「应让步」的边界）；H2（草稿均新增产物）。
- **Agent Memory**：M2 存 `workspace/rebuttals/`；sidecar 刷新。
- **轨迹与归档**：triage 决策（含证据指针）入 trace；三件产物入 artifacts。
