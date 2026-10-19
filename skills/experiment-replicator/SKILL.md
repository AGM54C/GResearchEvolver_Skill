---
name: experiment-replicator
description: 实际运行受预算约束的本地或 SSH 计算实验，记录环境、输入、命令、原始结果与失败；支持排队、监控和取消。
---

先区分 protocol_only 与 executed。锁定代码版本、数据哈希、环境依赖、测量口径和预算；小型 smoke run 通过后再扩展。不要把已有结果文件当成新执行。

用 runtime `init/run` 或 enqueue/queue-next；显式提供 command、requires、outputs、timeout、cost_estimate。只有声明幂等和可重试退出码的操作才有限重试。记录原始 stdout/stderr 和所有失败，不把无指标执行失败当负科学结果。

SSH 使用授权主机及专用远程目录；上传显式输入、运行、取回输出。真实远程运行前确认环境与调度器取消方式。当前适配器停止 SSH 客户端不能保证远程后代已终止，云计费也不是本地预估成本能强制控制的。

报告论文值与复现值的口径差异、配对不确定性、运行成本、成功率/任务覆盖及不可比项。结果分析转 statistical-analyst。新数据与补实验通过版本化 retest 阶段回接论文及评审。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
