# GResearchEvolver Agent 重型化

本轮把现有科研技能与运行器接成可持续运行的 Agent，保留全部 26 个技能和 82 个既有科研操作。原有绘图、PPT、证据、统计、记忆、RSI 及工作流仍在完整产品中。

运行 `python launch_agent.py`，打开 `http://127.0.0.1:8765/agent`。操作说明见 [工作台手册](../../skills/_shared/agent-workbench.md)。

- [设计及取舍](01-design/report.md)：为什么做、保留范围、模型/工具/人工边界。
- [实现记录](02-implementation/report.md)：协议、会话、恢复、交互、报告、进化来源与开发真实性。
- [验证报告](03-validation/report.md)：故障测试、完整回归、真实调用与打包检查。

科研阶段使用版本化 report.md。新增模块可进入现有受控能力进化机制，但运行中的 Agent 不自动改写自己的权限、评估器或已固定源码。未根据工程测试宣称科研收益、工业 SLA 或“最强”。
