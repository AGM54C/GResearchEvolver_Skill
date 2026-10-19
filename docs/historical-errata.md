# 历史记录勘误（不改写原档）

基线提交 `bba13cd3c55290b58231bf0e75c9973ef30f867f` 的 `research-instance/` 保持原字节。本次发现问题的依据来自先前固定版本源码/归档审计，不据此推断历史造假。

1. 三轮归档各缺同样 9 个公开文件（8 个 HTML、workspace/codeartsagent-llms.txt）；若干条仅在换行变为 CRLF 后匹配，memory/evolution-log.md 与后来版本不同。旧包不构成全量原字节独立回放。逐档计数见 corrections/legacy-archive-audit.json。v2 新档保存实际原字节和历史 CAS 对象，不回填旧哈希冒充历史。
2. C-hallulens-5 合并三项指标而 quantity 只记录一项。corrections/graph-v2-overlay.json 分成 96.67% 弃权判断、95.56% 正确性判断、94.77% NonExistent 与人类一致率，分别引用现有全文文本及行号。它们是原论文报告，不是本项目实测；原节点的“§4 Evaluation”定位也过粗，改用具体原文片段。
3. E-10 的概念区别不足以构成 refute，E-15 的正交维度不足以成为 condition；新 overlay 暂停这两条关系，保留待裁决原因。E-16 的跨任务推广也降为待审。原图不被静默替换为“当时正确”。
4. 旧 A/B 的 18/18 与 11/17 是单主题单轮、相同生成/评判者、输入约束不匹配的演示；只能描述该次整套流程差异。不能单独归因图结构，不能证明结构上不可能幻觉。README 已移除普遍可靠/单调进步/全程确定性复现的表述。
5. 原安装器漏 HARNESS 且 force 可能嵌套；v2 Python 安装器已替换并有隔离重复安装测试。原 mode 枚举/注册表不一致和循环 consumes 已改成一致路由目录与具体运行显式 DAG。

这些纠错是新增文件；后续分析旧实例时，必须同时读取 overlay 和本勘误。新增记录仍需科学语义复核，不能因为修过一次就默认全部正确。
