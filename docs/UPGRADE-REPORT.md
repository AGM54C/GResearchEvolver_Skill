# Evidence-based AI4Research：实现与验证

本文保留 v2 的文献阅读、实现与历史测试。后续 v2.1 已补入真实模型/数据 pilot、Docker 隔离与签名、语义拒判、实际隐藏状态诊断、外部集成和可执行 HCI 材料；最新结果以 [v2.1 验证报告](VALIDATION-V2.1.md) 和 [机器记录](validation-v2.1.json) 为准。下文 46 项测试和合成数值是 v2 历史结果，不是当前能力指标。

核查日期：2026-10-19。开发分支 `evidence-research-v2`，基线提交 `bba13cd3c55290b58231bf0e75c9973ef30f867f`。本轮围绕用户提供的 22 篇论文，升级 RSI、人机介入和证据链，并补入此前对照评审中的科研能力。绘图与 PPT 不计入功能升级；原有模块仅修正安装元数据。

现在包含 **25 个技能、27 个路由模板，以及可实际运行的 Python runtime**。技能承担开放科研推理与写作，runtime 负责输入快照、执行、统计和证据检查、状态及人工控制。模板仍须由宿主结合具体研究问题绑定成 DAG；没有伪造一个不需要模型账号或领域工具的后台科研智能体。

## 论文阅读与设计取舍

22 份 PDF 共 600 页，全部提取为带物理页码的文本，逐篇精读方法、实验、局限及相关附录。原始文件名称、页数和 SHA-256 在 [paper-index.json](evidence/paper-index.json)；逐篇证据与取舍在 [reading-notes.md](evidence/reading-notes.md)，对应工程位置在 [implementation-map.md](evidence/implementation-map.md)。这不表示对每条参考文献或长篇原始轨迹作了独立复现。

主要采用的约束如下：

- **RSI**：SEAL、AIDE2、RSI survey 提醒区分开发自测、固定验收和最终报告；候选必须真实执行，不能以文本反思或自己的评分批准自己。RQGM 提醒评分器变化后保留历史、重建可比性。
- **HCI**：DoVer、AGDebugger 要求实际恢复和干预执行；DiLLS、InconLens、XAgen 强调原始证据、可解释导航和人的修改权。checkpoint 只恢复受管文件，不能代表外部世界已恢复。
- **证据与诊断**：SCIRIGOR、SAGE、SCHEMA、DeFA 支持来源—执行—数值—论断的分层核验、竞争解释和失效传播。结构有效与语义支持分别报告。
- **统计与能力评估**：POPPER 的条件有效性不能由代码自动保证；任务独立性、反证、负结果与重复使用数据必须显式记录。DiscoveryWorld、TruthInsightBench 与 reasoning coverage 研究提醒执行成功不等于科学发现或能力边界扩展。
- **需要专门模型的方法**：Latent Critic、ReCast 等保留适配契约；未训练或部署其隐藏状态模型，不把普通提示词称为论文方法复现。

## 功能缺失项的补齐

| 新增技能 | 已有可调用实现 | 当前边界 |
|---|---|---|
| systematic-review | 冻结协议、独立筛选声明、分歧裁决、PRISMA 记录/报告/研究计数、RoB/GRADE 记录、适用时的 meta-analysis | 筛选独立性和专家判断仍需实际人员/宿主保证；程序不自动生成可信证据等级 |
| reference-manager | CSL、RIS、BibTeX、nbib、EndNote、PubMed XML 导入；DOI 去重/冲突保留；导出和 lossless sidecar；Zotero 只读元数据与批注；Markdown 笔记 | 未实连私有 Zotero 库；不声称附件二进制双向同步 |
| statistical-analyst | 任务级配对 bootstrap、效应与区间、Holm/BH、固定/随机效应合并、数据质量和简单泄漏检查 | 统计方法按研究设计选择，不覆盖全部学科统计；种子不冒充独立任务 |
| hypothesis-validator | 零假设、竞争解释、预定分析与证伪记录；有条件的 e-value 累积 | 不证明提交的条件有效性、因果识别或 FDR |
| research-control | 本地控制台、暂停/单步/取消、批注、checkpoint fork、配置修改、里程碑比较 | 暂停在阶段边界生效；外部系统状态不自动恢复 |
| theory-prover | 形式化命题对齐流程、实际 `lake env lean` 调用与公理输出检查 | v2.1 已在真实 Lean 4.0.0 项目验证正确证明和三类拒绝；缺环境仍明确 unverified，形式化命题与科学论断的对齐需专业审查 |
| grant-planner | 目标—证据—工作包—风险记录、Decimal 预算核算 | 申请书内容由宿主按真实项目和指南撰写，不能把计划写成已完成成果 |
| literature-monitor | 增量条目身份、变更、撤稿/更正标志和未再出现状态 | 按调用更新；未再出现不等于撤稿，不自称后台定时服务 |

## 已有功能的改进

| 环节 | 本轮具体改动 |
|---|---|
| 文献检索与精读 | 五源真实 HTTP 客户端、有界分页、退避/缓存、原始响应；逐页 PDF 原文/哈希和 OCR-needed；BM25 与有来源的外部向量融合 |
| 证据图与写作 | source/data/code/result/claim 类型、每页提取绑定、原文核查、单数量论断、条件/单位/run、来源失效传播；正文和表格数字逐项绑定原结果 |
| 查新与评审 | 最近邻工作和反证搜索矩阵；模型意见区分实际证据；显式修订—补实验—复审与改投流程 |
| 实验编排 | 显式 DAG、required/optional 输入完整性、真实 argv/日志/退出码、受限重试、预算、资源队列、SSH 上传/执行/取回适配 |
| 人工介入 | 干预点前的文件快照、保留父轨迹、独立对照分支、稳定 milestone_id、冲突不强行匹配；共同测量目标与评价数据声明 |
| 策略进化 | 冻结评分器/任务/分区、实际候选与现任配对运行、任务回归/覆盖/成本门槛、审计次数限制、整包晋升/导出/回滚 |
| 归档与安装 | SQLite WAL、原字节 CAS、追加哈希链、含历史对象的可移植归档；安装包含 HARNESS/共享 runtime，强制升级不产生嵌套目录且保留备份 |

RSI 的两个比较对象现在明确分开：audit 使用当前 incumbent；final 固定使用 epoch 创建时的 reporting_baseline，且只能使用一次、不能批准晋升。`rsi-export` 导出当前整包并提供下一 run 的输入映射，宿主须实际采用该包，不能只记“进化成功”。

HCI 的干预判定要求两侧 `estimand/metric/unit/analysis_unit/evaluation_data_hash` 一致。更换估计量或评价总体导致数值上升，不会再直接判为改进。该检查依赖声明准确，不能独立证明语义等价或因果效应。

## 实际执行的验证

| 验证 | 结果 | 证据 |
|---|---|---|
| 行为回归测试 | **46/46 通过，0 跳过**；覆盖篡改/缺输入、实际进程/超时/取消、断点/分支、统计/证据、RSI、控制台 HTTP、安装与长路径归档 | validation.json 的 unit_tests，含测试名称、环境及源码哈希；源码在 tests/test_runtime.py |
| 技能元数据 | **25/25 通过** skill-creator validator；仅表示命名/frontmatter/脚手架检查通过 | skill_metadata |
| 最终离线闭环 | 8 个合成独立任务、每任务 2 次重复；增益 0.85、bootstrap 区间 [0.5125, 1.1]，负对照 0；数字审计、分支、归档、晋升、平局拒绝、回滚均执行 | offline_example；可运行源码在 skills/_shared/examples/offline_research.py；数字仅为合成接口结果 |
| 独立使用检查 | 另一个 agent 在隔离目录构造 12 个合成传感器任务、每任务 5 次重复，实际使用技能/CLI；独立重算原始预测、分数和归档 | independent_forward_check；保留汇总，不提供本次临时会话的完整回放 |
| 独立回归 | 原始三项问题及随后发现的里程碑冲突边界均已复核修复；连续两次晋升后的 final 仍对照初始策略 | observed_failures_and_fixes、targeted_regression、final_conflict_check |
| 实际网络请求 | Crossref 查询 scientific reproducibility，返回 2 条记录；只是连通与响应保留验证，不评价检索相关性/召回率 | network_check，保留请求时间与原响应哈希 |
| 包装与保留检查 | 注册表/路径/文档链接、Python 解析、HARNESS 一致性、原 22 PDF 哈希与历史 research-instance 保留 | pre_cleanup_package_check；清理后的状态另记 release_check |

独立前向测试未提供预期答案，也未让测试者修改产品源码。它发现并促成修复：阶段改名后里程碑未对齐、换均值/中位数仍被判改进、晋升后的 final 与候选自身比较。随后回归又发现显式 milestone_id 冲突被 stage ID 回退覆盖，现已修复。上述失败与修复结果保留在验证摘要中。

开发期间还修复了 Windows 文本换行导致的 PDF 页哈希不一致，以及深层归档路径的 MAX_PATH 问题。最终通过记录对应修改后的代码；先前失败不能被解释为从未发生。

精简验证记录见 [validation.json](validation.json)。按维护要求，已清理开发计划、临时源码副本、全文提取缓存、测试运行目录及重复日志。保留测试源码、可运行示例、实际结果摘要和被测源码哈希；独立 agent 的临时会话不再提供逐步回放。用户的 22 份原始 PDF 不随技能包发布。

## v2.1 更新后的边界

1. **科学能力与优势**：已做三个领域、六个真实数据微任务的同模型/任务/预算上限 pilot，两组均满分，未测出增益。尚无完整自主科研流程或竞品对照基准；HCI 材料和分析器已准备，研究尚未实施。不能据此声称“最强”“零幻觉”或全球首创。
2. **RSI 隔离**：显式 Docker 模式已将候选与宿主评分器、隐藏任务及签名密钥隔开，并实际验证权限、只读、网络禁用、超时、签名与重放拒绝。默认新审计批次避免重用相同文献/任务组；仍依赖可信宿主和合理任务设计，trusted-local 模式也仍须信任候选。
3. **外部集成**：五个公开检索源均取得过真实响应，其中 Semantic Scholar 成功的是显式 bulk；Zotero 公开演示库实际读取。真实 SSH/SFTP 在本机临时 Linux 服务验证上传、执行、取回和取消；用户指定外部主机确认 22 端口后仍连接超时。没有私有 Zotero 库，不能验证私有授权。Lean 结果见 v2.1 报告。实际运行 MiniLM 隐藏状态及线性诊断器，保留 8/24 的负结果；不是相关论文方法的完整复现。
4. **人工与领域判断**：新增源绑定的语义模型复核，检查否定、范围、因果和条件，并保留错误与拒判；这改善可检查性，仍不证明 entailment。通用编排需要领域方法、有效测量和专业审查；RoB/GRADE 表格完整性仍不是专家结论。

历史 `research-instance/` 原样保留，旧归档缺项和论断拆分作为 [追加勘误](historical-errata.md) 保存。可运行入口、请求格式和恢复边界分别见 [README](../README.md)、[runtime-guide](../skills/_shared/runtime-guide.md)、[HARNESS](../HARNESS.md)。
