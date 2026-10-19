# 风格画像：kghalubench

- **样本**：`workspace/literature/inbox/fulltext/kghalubench.txt`（KGHaluBench, arXiv:2602.19643, Newcastle University & Sage Ai）· 语言 en · 1 篇
- **提取参数**：strength=balanced · 提取日期 2026-10-19 · 统计脚本 `style_stats.py`（本目录），口径=正文行区间 [233, 505)（Abstract 正文起 → References 前），LaTeXML 残留段内清洗（`\mathrm{}`/`_{}`/`\displaystyle` 剔除，非整行删），图注/章节标题/公式行剔除；附录与参考文献排除（prompt 文本非正文风格）
- **样本规模**：4401 词（清洗后）/ 215 句 / 80 段 —— >2000 词，画像置信度正常
- **数值来源**：`kghalubench-stats.json`（脚本输出原样落盘，P1 可复现：同区间重跑数值一致）

---

## 结构层

- **章节推进式**：Abstract → 1 Intro → 2 Related Work（两主题小节带冒号标题）→ 3 Method（三级深度 3.1.1）→ 4 Experimental Setup → 5 Results（按指标分小节）→ 6 Conclusion → 7 Limitations（**ACL 式独立成章**）→ Appendix — 证据：全文目录结构 — 指令：生成稿采用同构序列，Limitations 必须独立成章（含诚实数据质量限定）
- **Intro 漏斗模式**：A1 宽挑战式 — 例句："Recent advancements in language generation and critical reasoning of Large Language Models (LLMs) have driven their widespread adoption"（§1 首句）→ However 转 limitation → gap 句 "This emphasises the need for robust benchmarks to quantify hallucinations"（§1）— 指令：首句领域进展陈述，2-3 句内 However 转缺陷，gap 用 "This emphasises the need for..." 式收口
- **贡献陈述式**：bullet 枚举式 — 例句："Our key contributions are:" + "• We propose a question-generation approach that leverages the KG's relational structure..."（§1，4 条，动词首 We+V：propose/construct/develop/conduct）— 指令：贡献段用 "Our key contributions are:" 引导 + 3-5 条 bullet，每条 We+动词开头
- **问题-方案链**："To address the limitations above, we present KGHaluBench, a KG-synergised hallucination benchmark."（§1）— 指令：gap 陈述后用 "To address..." 句引出方案
- **段落长度**：mean 2.7 句/段 / SD 1.8 / max 8（脚本 S10）— 指令：短段落，2-3 句为主，超 5 句拆段
- **图表前向引用**：1.82 次/千词（脚本 S6）— 例句："as displayed in Figure 5"（§5.1）、"As shown in Figure 6"（§5.2）— 指令：结果小节首段挂图/表前向引用

## 句法层

- **句长分布**：mean 20.5 词 / SD 6.9 / p25-p75 = 15-24（脚本 S1）— 例句（中位长度）："We assessed 25 state-of-the-art LLMs on the KGHaluBench benchmark, as detailed in Appendix A.1."（§4.2）— 指令：主句 18-24 词；穿插 ≤15 词短句做节奏；禁连续 3 句 30+
- **主被动比**：被动占 21.9%（脚本 S4）— 例句：被动用于流程描述 "These questions are then assessed at a conceptual level, and if no hallucinations or abstentions are detected, they are verified for factual correctness."（§6）；主动用于实验行动 "We assessed 25 state-of-the-art LLMs"（§4.2）— 指令：方法/管线流程可被动，实验行动 We+主动，比例约 4:1
- **名词化度**：80.4 个/千词（脚本 S5，高密度学术文体）— 例句："the question-generation process"（§5.1）、"an entity-popularity bias"（§2）— 指令：领域术语名词化照常（基准/指标名），非术语句避免连续 2 个以上名词化串
- **嵌套深度**：人工抽 10 句——最多 1 层从句 + 1 个分词/介词尾巴，无 3 层嵌套 — 例句："Therefore, we believe models should implement constructive abstention, in which the response provides guidance on how users can locate reliable information themselves."（§5.3，1 层 in which）— 指令：从句 ≤1 层，尾巴限 1 个

## 词汇层

- **hedging 动词谱（核心）**：show×6 / suggest×4 / indicate×3 / demonstrate×2 / reveal×2 / establish×1 / **prove×0**（脚本 S2）— 例句："This trend suggests that the smaller models lack the competence to understand and recognise the focal entity in question."（§5.2）；demonstrate 仅在有人类对照数据支撑时："The proprietary models demonstrate superior factuality, achieving an average Wa of 55.94%"（§5.1）— 指令：**主档位 show / suggest / indicate**；demonstrate 仅限强证据（人类对照/大样本显著差）；prove / establish 零使用（数学证明除外）——与本项目「动词强度不超证据」纪律天然对齐，谱交集即样本谱
- **连接词谱**：However×16（3.64/千词，**81% 句首**）/ Therefore×11 / While×8（让步 pivot）/ Yet×3 / Instead×3 / Additionally×1 / **Moreover×0 / Furthermore×0**（脚本 S3/S11）— 例句："However, GLM-4.5 achieves 54.35% Wa, outperforming powerful proprietary models, such as Claude-4-Opus and Gemini-2.5-Flash."（§5.1）；让步："While this mechanism clearly reduces hallucinations, over-abstaining can severely limit the usefulness of the model."（§5.3）— 指令：转折一律 However 句首；因果 Therefore 句首；让步 While 置句首；**禁用 Moreover / Furthermore**（样本零使用，注入即 Phase 2 违规）
- **拼写习惯**：英式 -ise×13 vs 美式 -ize×0（脚本 S13）— 例句："Our framework utilises the KG to dynamically construct challenging, multifaceted questions"（Abstract）— 指令：全稿统一英式（utilise / emphasise / analyse / recognise / organise）
- **数字报告式**：delta 5 / absolute 6 混合（脚本 S9）— delta 例："the HaluBOK metric dramatically decreases, from 54.75% to 11.91%"（§5.2）；absolute 例："with GPT-5 achieving the highest Wa of 65.60%"（§5.1）— 指令：主结果 absolute + 两位小数；模型对比分析 delta（from X to Y / by N%）
- **首人称密度**：19.3 次/千词（脚本 S8，We 驱动）— 指令：方法/实验/立场句用 We；局限陈述也用第一人称（"we rely on Wikidata" §7）

## 修辞层

- **opener 类型**：A1 宽挑战式 — 见结构层 Intro 例句 — 指令：Intro 首句领域进展陈述（Recent advancements in X have driven...），禁公式化 "has attracted increasing attention"
- **pivot 习惯**：However 81% 句首（13/16）；While 让步句首 8 次（脚本 S11）— 指令：gap/转折优先 However 句首；对比让步用 While 句首
- **时态习惯**：Abstract 现在时（"We present KGHaluBench, a Knowledge Graph-based hallucination benchmark that assesses..."）；方法现在时（"We retrieve three key sets of information"）；结果现在时（"Figure 8 reveals that..."）— 指令：三区一律现在时，禁 "we conducted / our experiments showed" 式过去时叙事
- **收尾式**：结论 = We-V 贡献复述链 + 展望末句 — 例句："We hope KGHaluBench can be used to develop effective strategies in addressing the challenge of mitigating hallucinations."（§6 末句）— 指令：结论段逐条 "We + 动词" 复述贡献，末句 hope/can 展望；Limitations 章诚实限定 + future work（"Therefore, we would like to expand the benchmark further to include domain-specific KGs..." §7）

## 负向核对（AI-tel 交叉）

**白名单（样本特有，画像照录，生成可模仿）**：
| 特征 | 频次 | 备注 |
|---|---|---|
| novel | 6 | 样本用于方法/指标命名陈述（"a novel benchmark"）；**内容红线交叉**：不得用于未决结论强化 |
| comprehensive | 5 | "a comprehensive hallucination benchmark" |
| leverage | 4 | "leverages the KG's relational structure" |
| extensive | 2 | "extensive experimental results"；**红线裁决**：无数值支撑时本项目证据纪律优先（内容红线 > 风格忠实） |
| numerous | 1 | "Numerous benchmarks have been developed" |

**零注入清单（样本 0 命中，生成稿出现即 Phase 2 不通过）**：delve / underscore / intricate / tapestry / pivotal / showcase / foster / realm / seamless / landscape / paves the way / opens new avenues / sheds light on / bridges the gap / paramount / for the first time / to the best of our knowledge / various / a wide range of / em-dash（—）/ it is worth noting / in order to / not just...but

---

## 复现

```
python style_stats.py ../../literature/inbox/fulltext/kghalubench.txt 233 505
# 输出 = kghalubench-stats.json（本画像全部数值来源；E6 幂等：同区间重跑数值一致）
```

提取轮轨迹：archive-003（trace 含脚本调用与首版清洗缺陷修正记录）。Phase 2（风格应用校验）**本轮未执行**——需 paper-writer 成稿后触发，属诚实边界非遗漏。
