# GResearchEvolver — Evidence-based AI4Research

面向科研全过程的技能包与轻量 Python runtime：将文献来源、实验执行、统计结果和论文论断连起来，允许研究者查看原始证据、暂停、修改、分支重跑与回滚策略。

v2.1 在可执行的状态与证据检查上增加了隔离、真实模型适配和实测记录。包含 **25 个技能**：原 17 个中 15 个科研技能已升级，新增系统综述、文献库、统计、假设验证、人机控制、形式化证明、基金申请和文献监测。绘图与 PPT 不在本次功能升级范围；原模块保留，仅规范安装所需的元数据。

当前源码进一步加固了进程托管、崩溃/队列恢复、环境漂移检查与完整备份，并接入 OpenViking 科研图谱记忆，保留条目节点、关系边及证据历史。设计参考、真实服务验证和部署边界见 [Harness 验证说明](docs/HARNESS-RELIABILITY.md)。

## 上手

[下载最新 Release](https://github.com/AGM54C/GResearchEvolver_Skill/releases/latest)，解压后可按下方命令运行和安装；发布页提供 ZIP 与 SHA-256 校验文件。

Python 3.10+；核心只依赖标准库。PDF 另需 PyMuPDF，签名需 cryptography，SSH 需 Paramiko；容器、Lean 与模型均按需接入。可使用 Responses/Chat/Ollama 或现有 Codex API-key 配置，保存真实用量与失败回执，账号密钥不写入技能包。

```text
python skills/_shared/runtime/research.py --help
python skills/_shared/examples/offline_research.py --output demo-run
python skills/_shared/runtime/research.py --store demo-run/state serve
```

示例实际执行合成数据分析、负对照、数字绑定、人工分支、归档与 RSI 晋升/拒绝/回滚。它验证接口闭环，不证明真实科研能力提升。输出目录需为新目录。

安装到指定宿主技能目录：

```text
python install.py --dest /your/runtime/skills
```

重复安装使用 `--force`，整包替换并保留备份，不产生嵌套 skill 目录。安装包含 HARNESS、registry、共享 runtime 和示例；具体见 [INSTALL.md](INSTALL.md)。

## 已实现的机制

| 环节 | 能力 |
|---|---|
| 检索与阅读 | 五源有界检索、缓存/退避、原始响应、逐页 PDF、文献库互操作、Zotero 元数据/批注、Markdown 笔记、BM25 与可选现成向量混合检索 |
| 证据与写作 | 数量/条件/单位/run 绑定、来源与引文核验、证据图和失效传播；带原文偏移的语义核验、反证/范围/因果/否定检查与拒判 |
| 设计与统计 | 协议、对照、独立单位、配对 bootstrap、效应量、Holm/BH、受限 meta-analysis、条件式序贯证据 |
| 执行与控制 | 显式 DAG、本地进程、SSH 适配、资源队列、预算、原始日志、暂停/取消/单步、人工批注、checkpoint fork、里程碑对齐 |
| 可靠性与复现 | OS 所有权锁、独立监督器、崩溃后代清理、分类失败/有界重试、环境锁、SQLite/CAS 完整性、完整备份恢复 |
| 科研记忆 | 版本化节点/边、邻域遍历、证据失效传播、本地检索、OpenViking 原文同步/向量检索与回执对账 |
| RSI | 可选 Docker 权限隔离、固定评分器、全新审计批次、配对实跑、签名晋升/防重放、固定 final 基线、完整策略导出与回滚 |
| 其他研究流程 | 系统筛选/裁决/PRISMA 账目、RoB/GRADE 记录、Lean 证明回执、基金目标/风险/预算、文献增量摘要、修订—补实验—复审/改投 |

运行手册：[runtime-guide.md](skills/_shared/runtime-guide.md)。科学保证与恢复边界：[HARNESS.md](HARNESS.md)。架构：[SKILL-ARCHITECTURE.md](SKILL-ARCHITECTURE.md)。

部署、恢复、环境锁与 OpenViking 配置：[harness-operations.md](skills/_shared/harness-operations.md)。当前受管本地执行支持 Windows/Linux 单机；未据此验证多机高可用或工业服务等级。

## 证据与验证

- [22 篇论文精读笔记](docs/evidence/reading-notes.md)：方法、实验、局限与实现选择，附 PDF 页码及原文件哈希。
- [论文—需求—实现映射](docs/evidence/implementation-map.md)：哪些方法借鉴了、哪些依赖未实现，避免把提示词称为论文算法复现。
- [升级与验证报告](docs/UPGRADE-REPORT.md)：测试、独立使用检查和外部未验证项。
- [v2.1 真实验证](docs/VALIDATION-V2.1.md)：同模型小基准、人工标签语义评估、真实隐藏状态诊断、隔离攻击与外部集成结果。
- [HCI 研究方案](docs/HCI-STUDY.md)：导师/同学可参加的平衡交叉 pilot、盲评指标和观测分析；尚未实施用户研究。
- [历史勘误](docs/historical-errata.md)：旧归档/论断图/A-B 案例的限制；`research-instance/` 原样保留。

开发检查：`python -B tests/run_checks.py --report validation.json`。CI 覆盖 Windows/Linux、Python 3.10/3.13；真实 OpenViking 测试按需运行 `tests/live_openviking.py`。技能元数据检查不评价科学质量。

默认本地模式用于可信开发；显式 Docker 模式将候选与评分/签名权限分开，宿主和 daemon 仍须可信。已完成 3 个领域、6 个真实数据微任务的同模型/任务/预算 pilot，两组均满分，未测出增益。语义核验在独立样本上仍有错误，简易隐藏状态诊断器表现较弱；因此保留拒判和人工复核，不据此宣称“最强”“零幻觉”或全球首创。
