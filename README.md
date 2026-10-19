# GResearchEvolver — Evidence-based AI4Research

面向科研全过程的技能包与轻量 Python runtime：将文献来源、实验执行、统计结果和论文论断连起来，允许研究者查看原始证据、暂停、修改、分支重跑与回滚策略。

本次 v2 从提示词约定推进到可执行的状态与证据检查。包含 **25 个技能**：原 17 个中 15 个科研技能已升级，新增系统综述、文献库、统计、假设验证、人机控制、形式化证明、基金申请和文献监测。绘图与 PPT 不在本次功能升级范围；原模块保留，仅规范安装所需的元数据。

## 上手

Python 3.10+；核心只依赖标准库。PDF 摄取另需 PyMuPDF；外部检索、SSH、Zotero、Lean 需要各自环境。宿主模型负责开放科研推理与写作，runtime 不内置模型账号。

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
| 证据与写作 | 原子数量、条件/单位/run 绑定、源文件与引文核验、data→code→result→claim 图、失效传播、正文/表格数字审计 |
| 设计与统计 | 协议、对照、独立单位、配对 bootstrap、效应量、Holm/BH、受限 meta-analysis、条件式序贯证据 |
| 执行与控制 | 显式 DAG、本地进程、SSH 适配、资源队列、预算、原始日志、暂停/取消/单步、人工批注、checkpoint fork、里程碑对齐 |
| RSI | 冻结评分器与数据分区、候选/现任实跑、回归/成本/覆盖门槛、复用预算、固定 final 基线、完整策略导出与回滚 |
| 其他研究流程 | 系统筛选/裁决/PRISMA 账目、RoB/GRADE 记录、Lean 证明回执、基金目标/风险/预算、文献增量摘要、修订—补实验—复审/改投 |

运行手册：[runtime-guide.md](skills/_shared/runtime-guide.md)。科学保证与恢复边界：[HARNESS.md](HARNESS.md)。架构：[SKILL-ARCHITECTURE.md](SKILL-ARCHITECTURE.md)。

## 证据与验证

- [22 篇论文精读笔记](docs/evidence/reading-notes.md)：方法、实验、局限与实现选择，附 PDF 页码及原文件哈希。
- [论文—需求—实现映射](docs/evidence/implementation-map.md)：哪些方法借鉴了、哪些依赖未实现，避免把提示词称为论文算法复现。
- [升级与验证报告](docs/UPGRADE-REPORT.md)：测试、独立使用检查和外部未验证项。
- [历史勘误](docs/historical-errata.md)：旧归档/论断图/A-B 案例的限制；`research-instance/` 原样保留。

开发检查：`python -m unittest discover -s tests -v`。技能元数据通过 skill-creator validator 检查；该检查不评价科学质量。

本地文件哈希与事件链是完整性机制，不是安全密封。候选和评分器具有相同系统权限；对抗 RSI 需独立可信执行服务。人类裁决、模型共识、引用存在或编译通过都不自动证明科学真值。本项目尚未完成同模型、同任务、同预算的外部能力基准，不能宣称“最强”“零幻觉”或全局首创。
