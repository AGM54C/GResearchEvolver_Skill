# Harness 可靠性与 OpenViking 科研图谱

本轮将 v2.1 的单机科研 runtime 加固为有明确恢复、对账和复现检查边界的实现。目标不是靠增加 HARNESS.md 的篇幅证明可靠性；验收依据是实际进程故障、持久化故障、跨平台回归及真实 OpenViking 服务往返。绘图和 PPT 不在范围内。v2.1 科学基准和 HCI 状态未改写，本轮工程验证不证明科研能力提升。

## 对照上游

审阅固定于 2026-10-19；以下是实际读取的上游资料和代码，不是对它们作完整安全审计。

| 项目 | 固定提交与实现依据 | 采用方式 |
|---|---|---|
| DeepSeek Harness | [`687f282`](https://github.com/deepseek-ai/deepseek-harness/tree/687f282e8625c6b8d11ff58211a90524be2e4317)，[架构](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/docs/architecture.md)、[agent 状态与失败收尾](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/core/agent-loop/src/agent.ts)、[工具调度](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/core/agent-loop/src/tool-calls.ts) | 借鉴持久化事实、调用/结果配对、开始前/结果未知的区别、取消后等待已开始工作结清，以及 provider 与状态编排分离。科研 DAG 保留自己的协议、预算和证据校验，未迁移整套 Cordis/Web 产品。 |
| OpenViking | [`e855796`](https://github.com/volcengine/OpenViking/tree/e855796c83f9eb575d9b0f3082926660730f6a63)，[Python HTTP SDK](https://github.com/volcengine/OpenViking/blob/e855796c83f9eb575d9b0f3082926660730f6a63/sdk/python/openviking_sdk/client.py)、[内容路由](https://github.com/volcengine/OpenViking/blob/e855796c83f9eb575d9b0f3082926660730f6a63/openviking/server/routers/content.py)、[处理模式](https://github.com/volcengine/OpenViking/blob/e855796c83f9eb575d9b0f3082926660730f6a63/openviking/resource/processing_mode.py) | 通过 HTTP 原文存取和 find 接口接入，默认 vectors_only；科研节点、边和整体图均显式保存为不可变版本文件，服务检索结果需回到原始节点验证。 |

DeepSeek 固定版本 README 明确为 developer preview，可能出现不兼容变更；MIT。OpenViking 固定版本主项目为 AGPL-3.0，镜像标记 v0.5.1，不能沿用其他版本可能采用的许可描述。本项目实现独立 HTTP 客户端，不复制、打包服务器源码，也不以集成代替服务部署的许可要求。用户最终选择 OpenViking，未安装 agent-memory 或宿主记忆 hooks。

## 已补齐的缺口

| v2.1 的缺口 | 当前机制 | 行为验证 |
|---|---|---|
| PID 无法表达完整所有权/处理 PID 复用 | OS 运行、队列、RSI 锁；worker token、generation、heartbeat；旧数据保守兼容 | 并发运行/恢复拒绝；锁释放后无需依赖旧 PID |
| 控制进程死亡可能遗留本地子进程；RSI 有独立弱执行路径 | 统一受管进程 transport，Windows Job Object 启动闸门、Linux subreaper、私有控制管道 | 强制杀死控制器、脱离会话的后代、正常退出遗留后代、RSI scorer 清理 |
| 无限日志与不充分失败收尾 | 有界 stdout/stderr、输出大小校验、结构化失败、attempt 历史、监督器清理回执 | 日志洪泛、无效 JSON、过大输出、超时/取消与未结清状态阻断 |
| 队列 worker 崩溃后长期占用资源 | 独立队列锁、持久化占用、queue-recover 对账并释放 | 控制进程死亡后任务记为 interrupted，不自动重复执行 |
| 重试与远端派发存在未知结果窗口 | 阶段共同截止时间、幂等退出码门槛、有限退避；SSH 派发前记录意图 | 不足预算不启动重试；未知清理结果阻止 retry，需人工对账 |
| CAS 半写可能占据正确哈希名；只检查现存对象 | staging/fsync/原子发布；SQLite FULL；引用完整性检查、未来 schema 拒绝 | 写入失败后可再次发布；丢失引用对象被检出 |
| 全 Store 迁移与环境比较不足 | SQLite backup API、静止运行与哈希清单、新目录恢复；解释器/包/runtime/声明文件环境锁 | 备份恢复多个图版本，篡改拒绝；严格模式漂移时命令不启动 |
| 缺少可互操作、保留关系的跨会话记忆后端 | 节点/边属性图、版本 CAS、来源失效传播、本地 BM25；OpenViking 不可变副本、outbox、完整提交标记 | 修订冲突、悬空边、失效传播、无损导入、断网恢复、丢失回执、部分提交、跨项目命中拒绝 |

## 验证与复现

最终机器回执保存在 `validation-harness/`，测试代码保存在 `tests/`。完整离线 suite 包含既有 v2/v2.1 回归以及新增的故障测试；`test_memory.py` 的本地 HTTP 服务明确是合同 fixture，不能当成真实 OpenViking 实测。

| 最终本地验证 | 结果与回执 |
|---|---|
| Windows 11 / Python 3.13.3 | 92 项通过，零跳过；[回执](validation-harness/windows-offline.json) |
| Linux 容器 / Python 3.11.10 | 92 项通过，零跳过；[回执](validation-harness/linux-offline.json) |
| 真实 OpenViking + MiniLM | 首次同步、重复同步、原图往返、向量查询、服务重启全部通过；[回执](validation-harness/openviking-live.json) |
| 独立安装目录 | 25 个技能、全部新 runtime 模块、已安装 CLI 的节点/边往返与 doctor 通过；[回执](validation-harness/install-smoke.json) |

[回执索引](validation-harness/index.json) 记录文件摘要和真实集成的源码关联；离线回执逐文件记录 runtime 与测试源码 SHA-256。Linux 本地验证在 WSL2 承载的 Docker 中完成，与 GitHub 托管 Linux runner 的 CI 分开记录。

开发中保留的失败发现：最初 Linux 的耗时断言把环境采集也算进阶段期限，整次调用为 4.108 秒、断言阈值 4 秒；测试改为检查真实启动次数及是否越预算启动重试，不宣称性能达标。随后 Windows RSI 回归在原 30 秒预算下失败，诊断捕获到 Python `_enter_buffered_busy` 致命退出：后台线程阻塞读取 stdin 缓冲区，在解释器关闭时争用锁。改用原始文件描述符读取，并把监督器自身退出码纳入验收、保留诊断日志。原 RSI 预算未放宽；新增检查拒绝只凭子命令成功就忽略监督器异常。最终回执仅对应修复后的源文件哈希。

最后一轮 Windows 故障测试还发现：取消可能发生在启动握手之前，向已退出的监督器写管道会遗失已完成的清理状态。现已停止在取消后发放启动信号，分别记录取消和控制器丢失，并在管道提前关闭时核对监督器回执。新增测试确认启动前取消不会执行命令。另将 Windows 测试目录清理同步到监督器退出，避免诊断文件仍被占用；备份恢复拒绝带路径穿越的 run ID，即使备份清单哈希匹配也不能绕过。

真实集成使用以下固定镜像，二者共享独立的无外网 network namespace，未调用收费模型服务：

- OpenViking `ghcr.io/volcengine/openviking@sha256:cbdca179a2101cf5cd6a3455c769875fca37a0e2a09cc834807371df675bc061`，OCI revision 与上述源码一致。
- 本地 encoder 环境 `sha256:e91c87665910d2f7979f01464eb9fc8205550b1e4e64cebdca96ef5a746e65fb`；真实 all-MiniLM-L6-v2，revision `8b3219a92973c328a8e22fadcfa821b5dc75636a`，safetensors SHA-256 `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`。

`tests/live_openviking.py` 创建独立服务和带 3 个节点、2 条边的测试项目，检查首次同步、重复同步、原始图/节点/边逐字核对、实际向量查询及服务重启后恢复。测试文本为标注的集成 fixture；向量由真实模型生成，未用随机向量假装线上行为。检索返回的目录项不能直接当节点，适配器核对项目/快照和原始内容后才返回。没有 VLM 请求，也没有以这些样本估计检索或科研质量提升。

```text
python -m pip install -r tests/requirements.txt
python -B tests/run_checks.py --report validation.json
python -B tests/live_openviking.py --report openviking-live.json
```

第二条是离线测试；第三条要求 Docker 和已在本地的固定镜像/模型缓存。所有测试容器、临时目录由脚本清理。CI 使用固定 action 提交并声明 Windows/Linux × Python 3.10/3.13；实际 CI 状态与本地回执分别报告，未运行的矩阵不冒充通过。

## 适用边界

当前是单机、本地文件系统、合作式任务的可靠性加固，不是已认证的工业级平台。没有完成长时间 soak、高并发吞吐、磁盘断电/损坏注入、多机共识/高可用、生产 OpenViking 账户/ACL 权限矩阵或大规模图库评估。Linux supervisor 自身被 SIGKILL 时，强后代约束仍需要外部 cgroup/容器；本地可信命令和同权限存储不是恶意代码安全边界。

OpenViking 通过不可变版本与 commit 标记提供完整图读取，未声称跨 HTTP 服务原子事务或 exactly-once 外部效果。历史版本保留修订来源；真实隐私删除需覆盖备份与所有远端版本。环境哈希一致也不核验所有系统库/驱动/仪器状态，更不证明结果正确或必然相同。

具体操作与恢复决策见 [harness-operations.md](../skills/_shared/harness-operations.md)。
