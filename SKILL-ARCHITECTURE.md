# v2 架构

技能负责研究判断与流程选择；runtime 固化输入、执行、检查和状态；研究者在任何有记录的阶段查看证据和介入。

| 层 | 责任 | 实际入口 |
|---|---|---|
| 科研能力 | 阅读、综述、假设、设计、解释、写作、评审、理论、基金 | skills/*/SKILL.md，按需加载 |
| 编排 | 具体运行的显式 DAG、host/command 交替、版本化迭代 | core.py、execution.py；manifest.yaml 仅是路由目录 |
| 可追溯证据 | 原文件/页码/结果绑定、图检查与失效、文献库/本地检索 | evidence.py、literature.py、retrieval.py |
| 统计与验证 | 独立任务级区间、修正、meta、序贯前提；系统综述记录 | statistics.py、review.py |
| HCI | 运行/阶段/事件、原始日志、批注、pause/step/cancel/fork/compare | console.py、core.py |
| RSI | 冻结协议/评分器、实际候选比较、整包 active/rollback/export | evolution.py |
| 外部适配 | 本地/SSH、资源队列、Lean、宿主模型 | execution.py、projects.py、adapter-contracts.md |

依赖声明分 required/optional/external 能力契约；实际执行另用 stage.needs 和输入路径。写稿与评审可以循环迭代，但实例 DAG 必须使用不同版本 ID/输出路径，不能让 writer→reviewer→diagnosis 的注册表声明形成运行环。

SQLite 保存状态和全局追加事件链；CAS 存原字节；每个 stage 记录检查点和真实调用。归档可移植，支持全新 Store 导入。安全权限、模型内部状态、远程环境与科学真值不是 SQLite 哈希可提供的保证。

人机介入依赖稳定科学里程碑，不依赖调用多少次技能。对齐只接受明确 milestone ID/相同声明标签或 stage ID；不擅自把语义相近当同一实验。干预的测量口径与评价人群不一致时不能把数值差异标为改进。

RSI 的选择器与报告器分开。候选提升后，audit 比较当前 incumbent；final 对比 epoch 开始时的固定 reporting_baseline。导出 active 整包作为下一次研究运行的显式输入，实现“改策略—验证—采用”的闭环；优化器自身的提升仍需单独评估。

现有 figure-mimic/slides-builder 不扩展。跨领域依靠数据契约、领域方法及工具适配，不声称一种统计/评审规程覆盖所有学科。
