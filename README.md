# GResearchEvolver

> **G**raph · **R**esearch · **Evolver** —— 用论断图对抗遗忘幻觉、全程可归档复现、会从每次运行中沉淀经验自我进化的科研 Skill 集合。

丢给一个研究主题，它走完：文献检索 → 论断图构建 → 综述 → IDEA 生成 → 实验设计与复现 → 失败诊断 → 论文成稿 → 模拟评审 → rebuttal 起草——**每一步的数字、引用、结论都可回接到证据，无锚论断不得写**。

## 三条底线（为什么可以信它）

1. **反捏造红线**：所有产出遵循 `_shared/anti-fabrication.md`——检索必须真实调用 API，失败输出 `EVIDENCE_MISSING` 而非编造；数字只来自 run 产物/数字账本；未决结论显式标注，禁止写成确定。
   实证：同主题对照实验中，图锚定生成 18/18=100% 可回接，无图自由写作基线仅 11/17=64.7%，4 条坏论断全部命中 LLM 综述典型幻觉形态（多源泛化/来源混淆/弱证据强化/编造结论）——见 `research-instance/workspace/survey/graph-ab-1/`。
2. **全程可复现（HARNESS v2）**：P1-P5 公理（模型可见⟺已记录/归档不可变/…）+ trace 事件化 + 两阶段归档 + artifacts sha256 清单。三轮真实归档在 `research-instance/archives/`，每轮含 trace.jsonl（逐事件）/ manifest / 全产物哈希 / memory-diff，可独立核验。
3. **会进化（Evolver）**：每轮运行后 rsi-evolver 走 reflect → evaluate → distill → evolve，把踩过的坑蒸馏成经验（`research-instance/memory/experiences/`），经验库与进化日志（`evolution-log.md`）随实例公开——跑得越多越聪明，且每次进化有 memory-diff 审计。

## 快速开始（三个场景）

> **安装**：一行命令装进 Claude Code / 任意 Agent 运行时 → [INSTALL.md](INSTALL.md)（3 分钟试用路径也在里面）

| 场景 | 入口 | 说明 |
|---|---|---|
| **论文精读**（最轻） | `skills/literature-scholar` | 丢 PDF/链接 → 结构化条目 + 论断图节点 + 《我的想法》笔记位 |
| **全管线** | `skills/research-autopilot` | 编排器按 manifest 路由自动走完研究管线 |
| **单点调用** | `skills/manifest.yaml` | 查路由表：intents 触发词 / provides-consumes 数据契约 |

> 运行环境：Claude Code / CodeArts 等支持 SKILL.md 的 Agent 运行时；零外部服务依赖（无向量库/无数据库/无 GraphRAG 运行时——外部引擎仅为可选加速层，见 HARNESS §9 降级声明）。

## Skill 一览（16 条管线）

| 管线 | Skill | 一句话 |
|---|---|---|
| intake | literature-miner | 5 源真实检索（arXiv/S2/Crossref/OpenAlex/PubMed），去重排序 |
| reading | literature-scholar | 摄取建图：原子论断节点 + 四类原子关系 |
| ideation | idea-forge | 进化计算式 IDEA 生成（变异/交叉/选择） |
| design | experiment-designer | 可复现协议设计（env.lock/种子/run 号） |
| replication | experiment-replicator | 复现执行（real 全量留痕 / protocol_only 显式标注） |
| diagnosis | diagnosis-clinician | L1-L6 诊断定位 + 干预验证（唯一汇聚点） |
| survey | survey-architect | G 路径图锚定综述（无锚不写） |
| style | style-mimic | 任意样本 → 量化风格画像（HOW not WHAT） |
| writing | paper-writer | 逐章迭代协调 + 跨章状态卡（数字账本） |
| production | latex-adaptor | markdown → venue .tex → PDF，cite-map 三向对账 |
| review | reviewer-panel | 动态评审人格压力测试，问题直通诊断 |
| rebuttal | rebuttal-drafter | 逐条 triage（可反驳/需补实验/应让步），证据锚纪律 |
| figures | figure-mimic | 视觉风格画像；数据图代码生成（生图模型不碰数据） |
| presentation | slides-builder | 论点骨架投影式 slides + 讲稿 |
| outreach | doc-composer | 小红书/博客/报告/周报四形态，传播力零升格红线 |
| evolution | rsi-evolver | 受控 RSI 自进化 |

架构全貌见 [SKILL-ARCHITECTURE.md](SKILL-ARCHITECTURE.md)；运行规范见 [HARNESS.md](HARNESS.md)；每个 skill 附 1-5 分 rubric 硬验收（0 分即作废）。

## research-instance/（真实研究实例）

以「LLM 幻觉研究」为首个跑通案例的全部运行数据——**不是 demo，是真实轨迹**：

- `archives/` 三轮归档（补归档实证 / 图对照实验实时归档 / 风格画像提取轮）
- `memory/experiences/` 经验库 + `memory/evolution-log.md` 进化日志
- `workspace/literature/` 30 节点论断图 + 6 篇全文 + 6 份精读笔记 + 检索原始层
- `workspace/survey/graph-ab-1/` 图锚定 vs 无图基线对照实验五件套
- `workspace/paper/style-profiles/` 首次风格画像实证（4401 词样本可复现统计）

导读见 [research-instance/README.md](research-instance/README.md)。

## 组内使用与贡献

- **用法反馈**：跑完一轮把 trace/产物发出来，按 HARNESS §5 归档格式即可入档
- **经验贡献**：踩坑后按 `memory/experiences/` 现有格式写一条（skill / failure_mode / 为什么 / 如何应用四段式），rsi-evolver 会在下轮 reflect 时收编
- **新 skill**：SKILL.md（遵守 HARNESS）+ rubric + manifest 注册一条，编排器零改动自动路由

## 仓库关系

本仓库为**完整版**（组内试用）；参赛提交版为 30 文件压缩包（华为小红书 skill 创新赛，仓库 [Huawei-Redbook_Skills](https://github.com/AGM54C/Huawei-Redbook_Skills)）。
