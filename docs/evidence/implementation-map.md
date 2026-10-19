# 论文与实现映射

P01–P22 的完整标题、阅读证据与限制见 [reading-notes.md](reading-notes.md) 和 paper-index.json。以下是方法启发到工程实现的映射，不表示复现这些论文的模型、训练或论文指标。测试位置为 `tests/test_runtime.py` 与 `tests/test_v21.py`；合成闭环为 `skills/_shared/examples/offline_research.py`。真实模型/数据、隔离及集成的结果见 [v2.1 验证报告](../VALIDATION-V2.1.md)。

| 论文 | 采用/改进的机制 | 代码或技能 | 验证与未覆盖项 |
|---|---|---|---|
| P01 Latent Critic、P13 ReCast | 字段/步骤级依据与诊断接口，区分结构检查和白盒模型 | adapter-contracts、diagnosis-clinician、representations.py | 实跑冻结 MiniLM 隐层与线性诊断器，保留 8/24 的负结果；未复现这两篇论文的训练方法 |
| P02 Failure Attribution、P21 Who&When Pro | 自然/注入分层、简单基线、误报/exact-set、多错误及漂移意识 | diagnosis-clinician、reviewer-panel | 作为评估协议；未复现完整归因基准 |
| P03 POPPER | H0 蕴含、条件有效性、数据使用记录、e-process 的有限声明 | statistics.sequential_evidence、hypothesis-validator | 缺少前提拒绝；不自动证明条件有效性或 FDR |
| P04 DeFA | 协议依赖与语义依赖分离，修复前先检查首个观察坏边 | core DAG、evidence graph、diagnosis-clinician | 依赖/篡改测试；未复现 DeFA 模型 |
| P05 DiLLS、P22 XAgen | 运行/阶段/事件导航，原始证据，定位反馈 | console、Store.annotate | HTTP 控制鉴权及实际批注；无 HCI 用户研究结论 |
| P06 DiscoveryWorld | 执行成功/知识/机制证据分开 | offline_research、experiment-designer | 合成负对照；未跑其 120 任务环境 |
| P07 RL coverage、P12 ProRL | 覆盖/多样性/成本，不以采样效率等同能力边界扩展 | rsi-evolver、required_domains/回归门槛 | 无权重训练；未复现 RLVR 或长程训练 |
| P08 DoVer、P10 AGDebugger | 实际 checkpoint、fork、重复未修改对照、遵循与状态质量 | core.fork、execution、review.intervention_assessment | 实跑分支/取消/恢复；测量口径变化拒绝改进判定 |
| P09 InconLens | 人可声明/修改里程碑，跨阶段 ID 对齐、保留未对齐项 | core.compare_runs、console | 独立使用测试发现后修复；不做未经确认的语义自动对齐 |
| P11 SAGE | 多候选原因、独立批评、区分执行失败/负结果；数字到条件/run 绑定 | diagnosis-clinician、audit_writing | 正文+表格、原结果上下文、缺证拒绝 |
| P14 RSI survey | 经验/候选/晋升分开，防自我确认，优化器不自动获认可 | rsi-evolver、evolution.py | 验收次数、拒绝、回滚；不宣称开放 RSI |
| P15 AIDE2 | 候选与现任同任务/种子/预算实际执行，开发/选择/审计/报告分区 | evolution.freeze/evaluate | 实跑晋升/退化/平局/最终基线测试；合成结果非能力评测 |
| P16 SCIRIGOR | data→code→result→claim；独立数值复核与语义判断不互相覆盖 | execution、evidence、writing ledger | 真实命令/输入哈希/输出验收；独立测试重算一致 |
| P17 SEAL | 自测仅开发信号，外部评分、整包保留与回滚、final 隔离 | evolution.py、isolation.py、attestation.py | 实测可选 Docker 候选边界、独立签名与拒绝重放；trusted-local 仍非 sealed，宿主/daemon/控制器须可信 |
| P18 RQGM | epoch 内冻结，变更依赖失效，历史保留；固定外部 anchor 校准 | evolution.epoch_comparison、retrieval.invalidate | 程序判断版本可比性；外部 anchor 校准尚需可信部署与实际任务 |
| P19 SCHEMA | 保留 hedge/否定/量词，反证检索，潜在失效而非自动判错 | evidence、retrieval、literature-scholar | 不采用首个非空证据短路；图影响不等于真实因果 |
| P20 TruthInsightBench | 控制/稳健性/泛化/新颖性/证伪逐项状态，planned≠executed | designer、validator、reviewer | 合成闭环验证执行；尚无跨领域同预算能力排名 |

## 对照产品补齐

此前 Auto-Research-Skills 等固定版本源码比较发现的缺失：systematic-review（协议/双人筛选/裁决/PRISMA/RoB/GRADE/meta）、reference-manager（CSL/RIS/BibTeX/EndNote/PubMed/Zotero/笔记）、theory-prover（命题对齐/Lean/公理）、grant-planner、literature-monitor 均已有技能和实际辅助代码。

已有不足：执行编排/队列/SSH、统计、来源/数字审计、查新矩阵、本地检索、修订补实验复审、RSI/HCI、安装与归档已补实现。v2.1 加入实际模型适配、源绑定语义复核与候选隔离；语义仍有错误，完整领域方法和私有数据访问需专业环境。不能把“提供适配接口”写成“该外部环境已经端到端验证”。

新增机制多数有清楚的既有来源，不应申报单点算法首创。可考察的差异是这些机制在同一证据与人工介入闭环中的组合及执行质量；全局优先权和性能优势需要另做查新与公平实验。
