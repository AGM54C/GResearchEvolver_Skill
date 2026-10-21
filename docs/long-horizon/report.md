# GResearchEvolver 长程科研能力

本轮将长程项目、自动上下文交接、跨会话预算、实际科学前提检查、外部实验等待和人工监督经验改进接入现有 Agent。按用户要求，**直接复制并调用 MemTX 上游核心代码**；没有自行重写它的事务状态机。

保留全部 26 个技能和原有 82 个科研操作，包括绘图／PPT、节点与关系边记忆、OpenViking、DAG／SSH 与受控 RSI。新增 8 个项目／MemTX 操作，合计 90 个；原生 Agent 工具由 11 个增至 17 个。勘误：拆分仓库时按 `agent_tools.TOOLS` 实际清单核对，原文的 12／18 是计数错误，工具没有删除。

- [设计与固定代码来源](01-design/report.md)
- [实现、介入入口与边界](02-implementation/report.md)
- [实测与失败记录](03-validation/report.md)
- [使用手册](../../skills/_shared/long-horizon-guide.md)
- [MemTX 原样源码清单](../../skills/_shared/vendor/memtx/UPSTREAM.json)

每个阶段保留 `report.md`，项目与会话分别留存实际反馈。研究者负责科学方向、条件与证据判断，策略采用继续走冻结评估和真实人工审阅。这是受控的长程 Agent，不是无监督、无限预算的开放式 RSI。

MemTX 固定提交没有声明许可证，复制文件保留原来源和 `NOASSERTION`，本项目 MIT 不覆盖它。这里交付本地集成，没有将它伪装成可按 MIT 任意再分发的第三方代码。

请优先在真实研究任务中反馈：介入是否太频繁、前提填写负担是否合适、何时需要解释、恢复后是否能顺利继续。工程测试和模型小检查不作为导师／同学用户研究，也不支持“最强”或科学收益声明。
