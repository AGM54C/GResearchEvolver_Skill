---
name: slides-builder
description: 学术演示文稿制作。把成稿/复现结果转为答辩 PPT、组会 slides 或课程汇报——每页一个论点 + 证据 + 讲稿（speaker notes），数字全部从数字账本取，不逐段粘贴正文。触发条件：要求"做PPT""答辩幻灯片""组会汇报 slides""汇报演示"。
---

# slides-builder Skill

成稿的演示形态转换。**核心纪律：一页一论点——slides 是论点骨架的投影，不是正文的压缩粘贴；页内每个数字可回接数字账本，未决结论的页加显式「（初步）」标注。**

> **验收标准**：按 `references/slides-qa-rubric.md` 打分；S2（数字账本回接）= 0 → 作废。
>
> **诚实边界**：本 skill 保证**结构正确与内容真实**，不承诺设计美观（模板/配色由用户提供或用极简默认）；设计感需求建议转专业模板工具。

---

## 1. 工作流

### Phase 0：论点骨架萃取

- 从 source + paper-state.json 提取：核心主张（1 句）、支撑证据链（每条带 claim_id/run 号/强度态）、关键图表（figure-id）；
- **未决项清单**单独提取——slides 上出现时必须带「初步/待验证」标注。

### Phase 1：结构映射（按 mode 选模板）

| mode | 页序模板 |
|---|---|
| defense | 标题页 → 问题（1-2 页，为什么重要） → 方法（2-3 页） → 实验（3-4 页，每页一个实验论点+图） → 局限（1 页，诚实） → 结论（1 页） → 致谢/QA |
| group_meeting | 上周计划回顾 → 进展（数据为主） → 问题/卡点 → 下周计划 → 讨论项 |
| course | 是什么 → 为什么 → 怎么做 → 证据 → 启发/延伸 |

映射纪律：每页 = 论点标题（结论式，非「实验设置」式）+ 3-5 个要点 + 证据（图/表/数字）+ speaker notes（这页怎么讲，40-60 字/页）。

### Phase 2：产出

- `format: pptx` → python-pptx 脚本生成（结构化：每页 title/bullets/notes/图占位）；
- `format: marp` → markdown 源（`---` 分页，frontmatter 定主题）；
- 图从 `figures/` 按 figure-id 引用（figure-map 对账），**不在 slides 里重画数据**。

### Phase 3：对账 + 交付检查

- **数字对账**：slides 中每个数字 ↔ 数字账本条目逐项比对（应零无源数字）；
- 页数合规（defense ≤15 / 组会 ≤10）；未决标注完备；
- 产出 slides-ledger.md：每页 ↔ 论点 ↔ 证据指针对账表。

---

## 2. 产物

```
out_dir/
├── slides.pptx 或 slides.md    ← 演示稿（含 speaker notes）
├── build_pptx.py               ← pptx 格式时的生成脚本（可复现）
└── slides-ledger.md            ← 页↔论点↔证据对账
```

---

## 3. Gate Check

- 一页一论点（无粘贴式大段文字页）
- 数字 100% 回接数字账本（ledger 对账平衡）
- 未决结论页有显式标注
- 每页有 speaker notes
- 图引用经 figure-map 对账（无幽灵图）

---

## 4. 与其他 skill 的边界

| 能力 | 本技能 | paper-writer | doc-composer |
|---|:--:|:--:|:--:|
| 论文成稿 | — | ✅ | — |
| 演示形态（论点骨架投影） | ✅ | 内容源 | — |
| 分享形态（小红书/博客） | — | — | ✅ |
| 数字红线 | 账本回接（同源同纪律） | 账本生产者 | 账本回接 |

---

## 5. 技术参考对照

| 机制 | 参考 |
|---|---|
| 论点式标题（assertion-evidence slides） | 学术演示研究（Assertion-Evidence 范式） |
| pptx 结构化生成 | python-pptx / pptx skill 生态 |
| marp 可版本控制 slides | marp 生态（markdown → slides） |
| 数字账本回接 | 本项目独有（paper-state.json 底座） |

---

## 6. 运行机制（遵守 HARNESS.md）

- **工具调用**：python-pptx 不可用 → 降级 marp markdown（E2，显式标注）。
- **错误恢复**：E6 幂等（同 source + 同 mode → 同 slides 结构）。
- **人的介入**：H1（mode/format 歧义给选项）；H2 无不可逆操作。
- **Agent Memory**：M2 产物存 `workspace/slides/`；sidecar 刷新。
- **轨迹与归档**：对账结果入 trace；产物入 artifacts。


## 调用参数（原版，未扩展）

```yaml
parameters:
  source:
    type: string
    required: false
    description: "内容源：paper.md（默认）/ repl 报告 / survey；可叠加 paper-state.json 数字账本"
  mode:
    type: string
    default: defense
    enum: [defense, group_meeting, course]
    description: "defense=答辩（12-15 页）；group_meeting=组会（进度+问题+计划）；course=课程汇报（教学性，多背景铺垫）"
  format:
    type: string
    default: pptx
    enum: [pptx, marp]
    description: "pptx=python-pptx 结构化产出；marp=markdown 源（可版本控制）"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/slides"

```
