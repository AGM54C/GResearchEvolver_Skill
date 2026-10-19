---
name: figure-mimic
description: 论文图表风格模仿。从样本论文的图中提取视觉风格画像（配色板/线型/布局/标注习惯），按画像生成图表——数据图（折线/柱状/热图）走代码生成（matplotlib/pgfplots，数据点从数字账本取，坐标精确）；概念图（teaser/框架图）走生图模型 prompt 工程 + 强制人工确认。与 style-mimic 对称：文本画像 ↔ 视觉画像。触发条件：要求"模仿这篇论文的图风格""按XX风格画图""生成论文图表"。
parameters:
  samples:
    type: string
    required: true
    description: "样本来源：论文 PDF/图目录/已有 figures/ 目录"
  figure_type:
    type: string
    required: true
    enum: [data, concept]
    description: "data=数据图（代码生成，坐标精确）；concept=概念图（生图模型+人工确认）"
  data_source:
    type: string
    required: false
    description: "数据图必填：runs/<run-id> 或 paper-state.json 数字账本路径——数据点只从这里取"
  gen_endpoint:
    type: string
    required: false
    description: "生图模型端点/工具名（concept 图必填，用户接入；未提供则只产 prompt 包不生成）"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/paper/figures"
---

# figure-mimic Skill

视觉层模仿，与 style-mimic（语言层）对称。**硬约束：数据图的数据点必须来自数字账本/run 产物，生图模型不得用于「画数据」——生成式像素做数据可视化是编造数据的图像形态。**

> **验收标准**：按 `references/figure-qa-rubric.md` 打分；F2（数据真实）= 0 → 图作废。
>
> **诚实边界**：生图模型画概念图（teaser/框架图）当前质量不稳定——本 skill 的产出是「prompt 工程包 + 生成尝试 + 人工确认环」，确认不通过时诚实降级（建议手绘/drawio），不硬交付劣质图。

---

## 1. 工作流

### Phase 0：样本图收集与分类

- 从 samples 提取图（PDF 抽页/目录遍历），逐图分类：**数据图**（含坐标轴/数值映射）/ **概念图**（示意/流程/框架）；混合图标注主导类型。
- 每图记 figure-id 与原文位置（§ + 图号）。

### Phase 1：视觉风格画像（figure-style-profile.md）

对样本图集提取可机械化观测的特征（参照 `references/figure-style-template.md`）：

| 层 | 特征 | 观测方法 |
|---|---|---|
| 配色 | 主色/辅色/强调色（hex 列表）、灰度使用 | 图像取色（前景聚类） |
| 编码 | 线型/标记/柱宽比/误差棒样式 | 人工标注 + 类型归纳 |
| 布局 | 图例位置、子图标号（(a)(b) 式）、双栏并置习惯 | 逐图标注 |
| 标注 | 均值线/背景带/箭头注释的用法与频率 | 计数 |
| 字排 | 字号层级比、轴标签风格 | 抽样测量 |

每特征三件套（与 style-mimic 同构）：观测值 + 样本例证（figure-id 指针）+ 应用指令。

### Phase 2：生成（二路，按 figure_type 分流）

**数据图（可靠路）**：
- 生成 matplotlib（或 pgfplots）代码：数据从 `data_source` 逐点读取；颜色/线型/标记/布局全部按画像执行；
- 代码即产物（可复现：同数据 + 同代码 → 同图）；渲染输出 PNG/PDF + 代码文件。

**概念图（生图路，人工确认环）**：
- prompt 工程包：风格画像的文本化（配色/构图/线宽风格）+ 内容需求（要素与关系，来自论文方法描述）+ 负向提示（禁文字乱码/禁加数据轴）；
- `gen_endpoint` 提供则调用生成（失败/劣质 → 如实记录）；未提供则只交付 prompt 包；
- **H2 强制确认**：生成图交用户验收（内容准确性：要素关系对不对；风格：像不像样本），不通过 → 降级建议（手绘草图 + 本 skill 按画像做排版建议），不硬交付。

### Phase 3：回接审计

- `figure-map.json`：每图 ↔ 正文引用位置 ↔ 数据源指针（数据图）或确认记录（概念图）；
- 正文图引用（"如图X"）与图文件双向对账（幽灵图/孤儿图列出）。

---

## 2. 产物

```
out_dir/
├── figure-style-profile.md   ← 视觉风格画像（可归档，E6 可复现）
├── figs/<fig-id>.{png,pdf}   ← 生成的图（数据图附 .py 源码）
├── prompts/<fig-id>.md       ← 概念图 prompt 工程包
├── figure-map.json           ← 图 ↔ 引用 ↔ 数据源 对账表
└── figure-report.md          ← 生成报告（含确认记录与降级声明）
```

---

## 3. Gate Check

- 画像特征全部有样本例证指针（不凭印象描述「大概是什么风格」）
- 数据图：数据点 100% 来自 data_source；代码可复现
- 概念图：生成经过 H2 确认或诚实降级；无未确认的生图直接入稿
- figure-map 对账平衡（无幽灵图/孤儿图未标注）

---

## 4. 与其他 skill 的边界

| 能力 | 本技能 | style-mimic | latex-adaptor |
|---|:--:|:--:|:--:|
| 视觉风格画像 + 生成 | ✅ | —（语言层对称件） | 引用图文件（\includegraphics） |
| 数据可视化 | ✅ 代码路（精确） | — | — |
| 生图模型调用 | 概念图路（+人工确认） | — | — |
| 图表内容审计 | ✅（figure-map） | — | cite-map 同构 |

---

## 5. 技术参考对照

| 机制 | 参考 |
|---|---|
| 学术插图自动化 | PaperBanana（★7240，Automating Academic Illustration） |
| 风格画像三件套（观测/例证/指令） | 本项目 style-mimic（对称设计） |
| 数据图代码生成优先（生图不碰数据） | 本 skill 独有红线（反捏造的视觉层延伸） |
| drawio/图示 playbook | embodied-ai-paper-writer（概念图降级路径参考） |

---

## 6. 运行机制（遵守 HARNESS.md）

- **工具调用**：生图调用失败返回 `{exit_code, stderr}`；无端点是预期降级（prompt 包交付）非错误。
- **错误恢复**：E2 降级链（生图失败 → prompt 包 + 排版建议）；E6 幂等（同数据 + 同画像 → 数据图代码一致）。
- **人的介入**：H2 强制——概念图每张生成后确认（内容准确性 + 风格相似度双指标）。
- **Agent Memory**：M2 产物存 `workspace/paper/figures/`；画像入 HARNESS 归档。
- **轨迹与归档**：生成调用与确认记录入 trace；figure-map 入 artifacts。
