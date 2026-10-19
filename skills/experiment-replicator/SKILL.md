---
name: experiment-replicator
description: 实际运行受预算约束的本地或 SSH 计算实验，记录环境、输入、命令、原始结果与失败；支持排队、监控和取消。
---

先区分 protocol_only 与 executed。锁定代码版本、数据哈希、环境依赖、测量口径和预算；小型 smoke run 通过后再扩展。不要把已有结果文件当成新执行。

用 runtime `init/run` 或 enqueue/queue-next；显式提供 command、requires、outputs、timeout、cost_estimate。只有声明幂等和可重试退出码的操作才有限重试。记录原始 stdout/stderr 和所有失败，不把无指标执行失败当负科学结果。

SSH 使用授权主机及专用远程目录；上传显式输入、运行、取回输出。远端 Linux 监督器通过取消标记、心跳租约和后代清理回执处理失联；派发意图在网络调用前持久化。没有对应清理回执时保持 cleanup_pending，实际核对远端再恢复。云计费仍不能由本地估算强制控制。

跨机器复现需保存依赖锁及声明输入，并使用 `environment-lock` 与 strict 模式阻止未解释的漂移。本地任务由独立监督器管理，恢复和完整备份步骤见 [运维手册](../_shared/harness-operations.md)。

报告论文值与复现值的口径差异、配对不确定性、运行成本、成功率/任务覆盖及不可比项。结果分析转 statistical-analyst。新数据与补实验通过版本化 retest 阶段回接论文及评审。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
