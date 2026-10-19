---
name: style-mimic
description: 风格画像与模仿引擎。从用户提供的论文 PDF/全文中提取四层语言风格画像（结构/句法/词汇/修辞，含 verbatim 例句与机械可测特征），供 paper-writer 按画像执行语言层写作，并量化校验生成稿与画像的一致性。只学「怎么说」，不碰「说什么」——内容纪律（图锚定/未决不写死/引用回接）优先于风格。触发条件：用户提供论文样本要求"模仿风格""按 XX 的风格写""学习这篇的写作风格""风格画像"；或写作管线中提供了 style_sources。
parameters:
  style_sources:
    type: array
    required: true
    description: "风格样本路径（PDF/txt/markdown，1-N 篇；多篇时画像取分布并标注分歧）"
  target_lang:
    type: string
    default: auto
    enum: [auto, en, zh]
    description: "生成目标语言；auto = 与样本主语言一致（支持中英双语画像）"
  strength:
    type: string
    default: balanced
    enum: [light, balanced, strong]
    description: "模仿强度——light 只取结构层与 hedging 谱；balanced 四层全取；strong 额外对齐句长分布节奏（可能牺牲表达自然度）"
  out_dir:
    type: string
    required: false
    description: "画像产物目录，默认 .codeartsdoer/.research/workspace/paper/style-profiles"
---

# style-mimic Skill

风格画像提取与模仿引擎。**定位（对齐 embodied-ai-paper-writer 哲学）：教 HOW to write，不碰 WHAT to claim**——学其形，不造其实。

> **市场差异化（调研 2026-10-19 二轮修正）**：动态风格提取并非零先例——journal-adapt-writing-skill（★762）已做「目标期刊语料 → 动态写作 skill → 稿件修订」，本声明初版「市面无先例」**不准确，特此修正**。真实差异化收窄为四点：①**任意样本**（论文/作者/任意文本，不限期刊适配场景）；②**量化画像**（机械特征统计 + 数值偏差校验，非定性惯例卡）；③**内容红线隔离**（HOW/WHAT 硬边界 + 风格执行前后红线 diff）；④画像为 **HARNESS 可归档产物**（E6 幂等、trace 可复现）。借鉴其静态基规则层概念（领域惯例可选底座）作为后续扩展方向。

> **验收标准**：画像按 `references/style-qa-rubric.md` 打分；P1（忠实于样本——画像特征必须有 verbatim 证据）或 P3（内容红线隔离——风格执行不得改动任何数字/引用/未决标记）= 0 → 作废。

---

## 1. 硬边界（先于一切风格规则）

| 层 | 允许 | 禁止 |
|---|---|---|
| **风格层（本 skill 管辖）** | 句式、hedging 强度、连接词选择、段落节奏、opener 类型、术语拼写习惯 | — |
| **内容层（paper-writer 红线，风格永不触碰）** | — | 数字与测量值、引用与 claim_id 锚、未决标记（「未决」）、证据 scope 限定、结论强度（W2/W3 红线） |

冲突裁决：风格特征要求与内容红线冲突 → **红线赢**。例：目标论文爱用 "we prove"，但我们的结论只有部分验证 → 用目标论文的**句式**（"We now turn to..."）但保持我们证据允许的动词强度。

---

## 2. 工作流

### Phase 0：样本摄取与画像提取

1. 读样本（PDF 走既有解析路径；HTML/txt 直接读）；多篇样本 → 特征取分布，分歧大的维度标注 `[样本分歧]` 并列两态。
2. 按 `references/style-profile-template.md` 四层提取，每层含：
   - **机械可测特征**（可复算）：句长均值/方差、hedging 动词频次谱、连接词频次、主被动比——这些用脚本统计，数值入 trace（P1 可复现）；
   - **verbatim 例句**（few-shot 素材）：每个特征 ≥1 条原文例句，标注出处 span；
   - **应用指令**：生成时如何执行该特征。
3. **AI-tel 负向清单核对**（`references/ai-tell-catalog.md`）：样本中存在的 AI-tel 特征 → 画像照录并标 `[样本特有：模仿优先于去味]`；样本中不存在的 → **生成时零注入**（宁可漏学，不可错加——对齐 §4.5 失败语义）。
4. 画像落盘 `out_dir/<样本名>-style-profile.md`，特征统计脚本与原始数值入 trace。

### Phase 1：风格应用（被 paper-writer 调用）

- paper-writer 组装正文时，语言层按画像执行；`strength` 控制范围（light/balanced/strong）。
- 术语锁定：样本的缩写定义时机、大小写习惯照画像执行（对齐 embodied Step 0 术语对齐纪律）。
- 中英双语：画像按样本语言取对应维度集（中文维度见模板 §5，英文见 §4；跨语言模仿——如英文样本中文写作——只取语言无关层：结构层 + hedging 谱语义映射）。

### Phase 2：风格一致性校验（量化，非感觉）

- 对生成稿重算 Phase 0 的机械特征 → 与画像对比：
  - **数值偏差表**：句长均值偏差、hedging 动词谱分布差、连接词频次比；
  - **AI-tel 注入检查**：生成稿中出现的 AI-tel 是否全部属于「样本特有」白名单；
  - **内容红线检查**：数字/引用/未决标记与风格执行前的版本逐项 diff（应零变化）。
- 产出 `style-consistency-report.md` 附于成稿；偏差超阈值（句长均值 ±30%、hedging 谱主档位错位）→ 标注并给修订建议，不静默通过。

---

## 3. 产物

```
out_dir/
├── <样本名>-style-profile.md      ← 四层画像（verbatim 例句 + 机械特征 + 应用指令）
└── <样本名>-consistency-report.md  ← 应用后校验（数值偏差表 + 红线 diff）
```

---

## 4. Gate Check

- 画像四层齐全，每特征有 verbatim 证据（P1）
- 机械特征可复算（统计脚本/数值入 trace）
- AI-tel 清单已核对，样本外特征标零注入
- 校验报告含数值偏差表 + 内容红线零变化确认（P3）
- 画像与生成稿语言匹配（或跨语言时仅用语言无关层并已声明）

---

## 5. 与其他 skill 的边界

| 能力 | 本技能 | paper-writer |
|---|:--:|:--:|
| 风格画像提取与校验 | ✅ | ❌ |
| 语言层写作执行 | 供给画像与指令 | ✅（执行者） |
| 内容组装/引用对齐/未决标记 | ❌ | ✅ |
| 图表绘制 | ❌（不做——市面已有专项，且当前 AI 绘图质量不达论文标准） | ❌ |

---

## 6. 技术参考对照

| 机制 | 参考 |
|---|---|
| 修辞功能模板 + [SLOT] 填空 + verbatim 例句 | embodied-ai-paper-writer phrasebank（63 篇顶会蒸馏） |
| AI-tel 目录 / 动词强度不超证据 | academic-humanizer（Layer 1-2） |
| 「HOW not WHAT」边界哲学 | embodied-ai-paper-writer |
| 语料驱动动态 skill 生成（先例） | journal-adapt-writing-skill（期刊适配场景；本 skill 扩至任意样本 + 量化画像） |
| 静态基规则 + 动态层叠加 | journal-adapt（base_rules 概念，后续扩展方向） |

---

## 7. 运行机制（遵守 HARNESS.md）

- **工具调用（HARNESS §1.2）**：特征统计脚本失败返回 `{exit_code, stderr}`，读错后降级为人工抽取并标注 `stats_mode: manual`。
- **错误恢复**：E2 降级（PDF 无文本层 → OCR → 失败标 `parse_failed`）；E6 幂等重跑（同样本 + 同模板 → 画像机械特征数值一致，verbatim 例句集一致）。
- **人的介入**：H1（样本语言歧义/多篇样本风格冲突不可自动合并时给选项）；H2（无不可逆操作，画像均为新增产物）。
- **Agent Memory**：M2 画像存 `workspace/paper/style-profiles/`；画像目录维护 sidecar（L0/L1，HARNESS §4.4）。
- **轨迹与归档（HARNESS v2）**：特征统计调用与数值入 trace（`tool_call` + `decision`——特征判定依据指向 span）；画像文件入 artifacts 哈希清单；画像提取轮由 autopilot commit 收编或独立小轮记录。
