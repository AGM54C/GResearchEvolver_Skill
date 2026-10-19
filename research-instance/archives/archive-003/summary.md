[style-mimic 画像提取]：kghalubench 全文四层风格画像首证 | 正文 4401 词/215 句机械画像 + AI-tel 白名单 5 词/零注入 23 项，数值全可复现 | 完成（Phase 0 画像就绪；Phase 2 校验待 paper-writer 成稿触发）

## 分析

skill 落地与首执行同轮完成：调研确认「从用户 PDF 动态提取风格画像」市面空白 → style-mimic 四件套 + manifest 注册（phase: style 新轴 + paper-writer consumes +style_profile）+ paper-writer 挂钩（基线稿/风格稿双版本 + 红线 diff + rubric W6）→ commit `f898cf6` → kghalubench 真全文画像提取。

关键读数（全部脚本可复现，stats.json）：hedging 谱 show×6 / suggest×4 / indicate×3，**prove×0**——样本动词纪律与本项目「动词强度不超证据」天然对齐，本样本上风格忠实与内容红线零冲突；However 16 次且 81% 句首为最强句法信号；英式拼写 13:0；AI-tel 白名单仅 5 词（novel / comprehensive / leverage / extensive / numerous，全部「样本特有：模仿优先于去味」），其余 23 项零注入。

方法论收获：① 首版脚本整行剔除含 `\mathrm` 段 → 20% 正文误删 + hedging 谱假象且**无报错**（P1 静默违规风险）→ 段内 LaTeX 清洗修正（经验 latex-fulltext-style-stats.md）；② 人工印象「This+NP+V 概括句高频」被机械统计纠正（实测 2 次）——画像模板强制脚本统计（P1）的动因实证。

## 核心请求与意图

用户决策「完整落地 + 实证（拿 fulltext 真全文做画像提取入 archives）」：验证第 12 个 skill 的画像提取管线真实可跑，产物按 HARNESS v2 归档。

## 关键概念

四层风格画像（结构/句法/词汇/修辞）· 每特征三件套（观测方法/verbatim 例句/应用指令）· AI-tel 白名单 vs 零注入 · HOW not WHAT 边界 · prove×0 = 样本谱与证据纪律的交集 · LaTeXML 段内清洗

## 待办

- paper-writer 成稿时触发 Phase 1/2（风格应用 + 一致性校验 + 红线 diff），产出 style-consistency-report
- 中文样本画像（模板 §5 中文维度）未实测
- 多篇样本画像合并（分布 + `[样本分歧]` 标注）未实测
