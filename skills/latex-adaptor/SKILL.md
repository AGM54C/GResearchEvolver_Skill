---
name: latex-adaptor
description: LaTeX 成稿适配。把 paper-writer 的 markdown 成稿转换为 venue .tex（会议/期刊模板或通用骨架）、生成并校验 .bib（DOI/字段/去重）、csv→booktabs 表、编译出 PDF，并保持内容红线在 .tex 世界可回接（claim_id → \cite 映射表审计）。触发条件：要求"转 LaTeX""编译 PDF""排版""投稿格式""camera-ready""生成参考文献库"。
parameters:
  venue:
    type: string
    required: false
    description: "目标 venue（如 NeurIPS 2026 / Nature / 我的目标期刊）；缺省用通用学术骨架并标注 template: generic"
  paper_path:
    type: string
    required: false
    description: "成稿路径，默认 .codeartsdoer/.research/workspace/paper/paper.md"
  anonymous:
    type: boolean
    default: false
    description: "双盲匿名模式：剔除作者信息/致谢/自引暴露，生成 anonymized 变体"
  out_dir:
    type: string
    required: false
    description: "产物目录，默认 .codeartsdoer/.research/workspace/paper/tex"
---

# latex-adaptor Skill

论文管线的格式化末端：markdown → venue .tex → PDF。**硬约束：格式转换不得改动任何内容红线（数字/引用/claim 锚/未决标记）——.tex 里的每个 \cite 必须能回接到 claim_id / 文献清单。**

> **验收标准**：按 `references/latex-qa-rubric.md` 打分；L2（红线零变化）或 L3（引用可回接）= 0 → 转换作废。
>
> **诚实边界**：本 skill 不带货 27 个预置模板（与 latex-document-skill ★790 的差距明示）；提供**模板获取协议**（官方源链接 + 人工确认，不自动信任 web 副本——过期的 Overleaf 拷贝是常见坑）+ 自产无版权风险的通用骨架。venue 专属模板由用户提供或按协议获取。

---

## 1. 工作流

### Phase 0：venue 识别与模板决策

1. 识别目标 venue（用户指定或从成稿结构推断）；
2. 模板三分支：
   - 用户提供 `.sty/.cls/.tex` → 直接用（记录来源与版本）；
   - 按协议检索官方模板 → **报告具体来源链接给用户确认**（如 "检测到 neurips_2025.sty；2026 CFP 用 neurips_2026.sty <link>——请确认目标年份"），确认后才获取；
   - 均不可得 → 通用学术骨架（article 单栏 / 会议双栏两式），产物标 `template: generic`，不伪装成官方模板。
3. 编译环境检测：latexmk / pdflatex / xelatex（CJK 强制 xelatex）；无 TeX 环境 → 降级输出 .tex + 编译说明，标 `compile: skipped_no_env`，**不假装编译过**。

### Phase 1：结构转换

- markdown 章节 → .tex sectioning（venue 深度规范：NeurIPS 三级、期刊按 guide）；
- 表格：csv/pipe-table → `booktabs`（`\toprule/\midrule/\bottomrule`，禁竖线）；
- 数学：行内/ display 公式映射；图表占位（**不绘图**——插入 `\includegraphics` 占位 + 指向图片路径，图本身由用户提供，见边界表）；
- 匿名模式（`anonymous: true`）：剔除作者块/致谢/资助号，自引改第三人称，产 `<name>-anon.tex` 变体。

### Phase 2：参考文献工程（.bib）

1. 从 literature/inbox 清单与 claim 锚提取被引文献 → 生成 `refs.bib`（arXiv/DOI 元数据，来自检索原始层，**不从记忆补字段**）；
2. 校验（`references/bibtex-integrity.md`）：必填字段齐 / DOI 与 arXiv id 格式 / 去重（同文多 key 合并）/ key 命名规范（`authorYEARkeyword`）；
3. **claim 映射表**：`cite-map.json`——正文每处 `\cite{key}` ↔ paper.md 中的 claim_id / 文献清单条目，双向对账（多引/漏引/幽灵引均列出）。

### Phase 3：编译闭环 + 红线 diff

- 编译（latexmk，错误分类：缺包/语法/字体三档，修复记录入 trace）；
- **红线 diff**：.tex 正文（剥离宏后）vs paper.md——数字逐项比对（测量值/百分比/样本量）、未决标记（「未决/待复核」）须原样保留或转 `\textcolor{gray}{(未决)}` 等显式形式，禁止静默消失；
- 页数/格式合规提示（超页标注 + 建议压缩段，不擅自删内容）；
- 产出 `format-report.md`：模板来源、编译状态、红线 diff 结果、cite-map 摘要、合规提示。

---

## 2. 产物

```
out_dir/
├── main.tex               ← venue 适配稿（或 <name>-anon.tex）
├── refs.bib               ← 参考文献库（校验后）
├── cite-map.json          ← \cite ↔ claim_id/文献条目 映射表
├── build/                 ← 编译产物（PDF/日志；skipped_no_env 时空）
└── format-report.md       ← 格式化报告（含红线 diff）
```

---

## 3. Gate Check

- 模板来源已记录（用户提供 / 官方链接确认过 / generic 已标注）
- refs.bib 校验通过：无缺字段/无重复/无幽灵条目
- cite-map.json 双向对账平衡（正文引用 = bib 条目 = 映射表）
- 红线 diff 零变化（数字/引用/未决标记）
- 编译状态诚实（成功 / 修复记录 / skipped_no_env 声明）

---

## 4. 与其他 skill 的边界

| 能力 | 本技能 | paper-writer | 市面专项 |
|---|:--:|:--:|---|
| .tex 转换 + 编译 + .bib | ✅ | ❌（终点是 markdown） | latex-document-skill（27 模板，更全） |
| claim_id → \cite 审计 | ✅（独有） | 提供 claim 锚源 | ❌ |
| 图表绘制 | ❌（占位 + 路径引用，不绘图） | ❌ | PaperBanana 等（不做） |
| 模板内容维护 | ❌（协议获取，不带货） | — | K-Dense venue-templates（带货 .tex/.bst） |

---

## 5. 技术参考对照

| 机制 | 参考 |
|---|---|
| 官方源确认后才取模板（不信任 web 副本） | paperjury submission-compliance（desk-reject shield） |
| booktabs/csv→表、latexmk 自动检测、CJK xelatex | latex-document-skill（27 脚本工艺） |
| venue 格式规范（NeurIPS/Nature/Elsevier） | K-Dense venue-templates（references 指南形态） |
| 红线 diff + cite-map 审计 | 本 skill 独有（W3 红线在 .tex 世界的延伸） |

---

## 6. 运行机制（遵守 HARNESS.md）

- **工具调用（§1.2）**：编译/校验脚本失败返回 `{exit_code, stderr}`；无 TeX 环境是**预期降级路径**（E2），非错误。
- **错误恢复**：E2 降级链（latexmk 失败 → pdflatex 裸跑 → 仅出 .tex）；E6 幂等（同 paper.md + 同模板 → main.tex 与 refs.bib 内容一致）。
- **人的介入**：H1（venue 歧义/模板版本冲突给选项）；H2（模板获取须确认，防自动抓到过期副本）。
- **Agent Memory**：M2 产物存 `workspace/paper/tex/`；目录 sidecar 收尾刷新（§4.4）。
- **轨迹与归档**：编译调用与红线 diff 结果入 trace；产物入 artifacts 哈希清单。
