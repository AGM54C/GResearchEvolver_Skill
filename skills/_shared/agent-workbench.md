# 完整 Agent 工作台

跨会话项目、自动上下文交接、实际 MemTX、科学前提检查、外部实验等待和人工监督经验改进见 [长程运行手册](long-horizon-guide.md)。保留全部原有功能，新增项目／记忆操作后共有 90 个科研操作、17 个原生 Agent 工具。此前文档写作 18 个是计数错误，按 `agent_tools.TOOLS` 核对修正，未删除工具。

## 启动与范围

源码根目录执行 `python launch_agent.py --store .research-agent --port 8765`，浏览器打开 `http://127.0.0.1:8765/agent`。安装为宿主技能后，仍可运行 `_shared/runtime/research.py --store <目录> serve` 并访问 `/agent`。原工作流控制台、26 个 Skill、82 个科研操作及视觉工具均保留。

模型可用 `responses`、`chat-completions`、`ollama` 或现有 `codex-config`。`codex-config` 使用现有 API-key 配置，不承诺兼容仅网页登录的 OAuth 账户。例：

```json
{"provider":"codex-config","max_output_tokens":2000,"timeout":120}
```

或显式配置，密钥放环境变量：

```json
{"provider":"chat-completions","model":"your-pinned-model","base_url":"https://your-provider.example/v1","key_env":"RESEARCH_MODEL_KEY","max_output_tokens":2000,"timeout":120}
```

Ollama 本地示例：`{"provider":"ollama","model":"your-installed-tool-capable-model","base_url":"http://127.0.0.1:11434","context_tokens":16384}`。模型须真实支持函数调用；没有把文本猜测转换为伪造工具调用。三种协议有离线 fixtures；具体服务的线上兼容性以实测回执为准。

## 一次研究怎样运行

1. 填写目标、成功标准、预算和介入方式，创建会话。材料通过文件选择器复制导入；单文件浏览器限制 16 MB，整个工作区默认 100 MB、2000 文件。
2. Agent 读取能力目录、相关 SKILL.md 与接口手册，调用科研操作。说明与资源按需读取，所有能力仍可发现。
3. 模型/工具各自进入独立监督进程，先保留执行意图，再启动进程，保存响应、日志和结算回执。工具顺序执行；不进行未获授权的并行副作用调用。
4. 每个科学阶段调用 `report_stage`，提供理由、方法、观察、浅显解释、证据、局限和问题。保存版本化 `reports/<stage>/<report-id>/report.md`，证据保存到 CAS。完整运行另有根 `report.md`。模型未提交阶段报告，或报告后又做了新操作，控制器会要求补报告再完成。
5. 可选择“关键取舍介入”或“每阶段审阅”。报告内容是 Agent 的解释，不是专家判定；`ask_researcher` 等待真人回答。反馈绑定显示的具体报告/请求；不会由模型自填“已接受”。
6. 运行中可补充研究方向。请求先进入持久收件箱，当前调用结束后暂停，撤回未执行的旧计划；继续后让模型按新方向调整。修改已发生的外部副作用仍需单独处理。

文件大小/数量为导入、自动写入和调用边界的检查上限，不是操作系统磁盘配额。人工批准的任意命令可能在检查间产生较大文件；不可信实验应使用已有隔离适配器及外部资源限制。

## 全能力工具入口

| 入口 | 内容 | 默认执行边界 |
|---|---|---|
| `capability_catalog` / `read_skill` | 全部技能、操作、手册、视觉与演示脚本 | 只读、分页、内容视为数据 |
| `operation_help` | 单个科研操作的实际分发字段、默认值和常用请求示例 | 从可信源码读取；不必为一个参数加载整份手册 |
| `list_files` / `read_file` / `write_file` | 材料与产物 | 项目范围；禁止穿越、隐私配置路径和链接；覆盖需匹配旧哈希 |
| `read_receipt` | 完整工具结果分页 | 只读当前会话已提交回执；长结果不丢失 |
| `research_operation` | 所有原有科研 CLI 操作 | 常规统计、文献、局部检索与科研图谱自动执行；高级/外部适配需精确审阅 |
| `run_command` | 既有 DAG、实验、绘图、PPT、独立工具与扩展程序 | 精确 argv、工作区快照、可执行文件哈希绑定的人工批准；本机可信执行 |
| `report_stage` / `ask_researcher` | 阶段交付、浅显解释与科学判断 | 实际报告/问题驱动停顿及反馈 |

`research_operation` 使用原 CLI 文档字段，`arguments_json` 是严格 JSON 对象。例如 Holm 校正：

```json
{"operation":"adjust","arguments_json":"{\"pvalues\":[0.01,0.03,0.2],\"method\":\"holm\"}"}
```

自动科研操作中的文件路径须相对当前工作区，`root` 写 `.`。记忆写入限于会话指定 project，actor 固定为本 Agent，保留 node/typed-edge 数据模型。OpenViking、SSH、Lean、隔离执行、训练/表示适配等仍使用原 API，可通过受审阅调用执行。画图/PPT 的脚本与 SKILL.md 完整保留，可生成可编辑产物并通过工作台下载。

人类审阅、裁决、签名密钥、冻结评估权限、能力采用与回滚不会交给模型自行调用。它们保留在可信 CLI/原控制台；这是权限边界，不是删除功能。批准任意本机命令相当于信任该命令，不能据此声称形成安全沙箱或防住同权限恶意进程。

## 持久化、预算与恢复

会话存在同一 SQLite 事务库的 `agent:<id>` 中；审计链、CAS、OS 会话锁与现有备份功能复用。完整调用目录在 `agents/<id>/attempts/`；工具返回与报告还保留 CAS 哈希。包代码、Python 可执行文件、选定依赖、白名单环境变量和导入材料固定到会话；恢复发现源码或环境变化会拒绝悄悄切换版本。新的版本应新建会话，显式传入需要沿用的材料。

安装到包含其他宿主 Skill 的目录时，仅加载、固定和读取 GResearchEvolver 注册的技能及 `_shared`，不会把旁边的其他研究技能隐式启用。

默认预算：24 次模型请求、80 次工具进程、1800 秒活动执行、48000 个**输出预留 token**；单模型调用默认最大输出 2000 token；失败模型请求也计数，最多 2 次瞬时错误重试。尊重 Retry-After；超过剩余活动预算时停止。输入按总上下文字符上限管理，供应商报告的 token 用量另记，未知用量明确累计。以上不是货币费用上限；人工批准的嵌套模型/远程命令可能另有费用或资源消耗，必须审阅其具体请求。

每轮模型请求会附剩余预算，提醒为实际计算、产物和阶段报告留出轮次。达到上下文上限会停止并保留完整原轨迹，没有用不透明摘要覆盖原始证据。工作台“按左侧预算续接新会话”或 CLI `agent-fork` 会复制材料、绑定父会话与报告哈希，并使用人明确设置的新预算；原始轨迹保留。续接是带来源的交接，不是无限上下文或无损自动压缩。

暂停在调用边界生效；取消请求由监督器终止本地进程树。远程请求若已发送，终止本地进程不代表远程效果已撤销。重试仅针对可分类的瞬时**模型传输**错误；不自动重放状态不明的工具副作用。

恢复先取得 OS 所有权锁，再核查监督器匹配的清理回执及工作进程结果。若结果已落盘但控制器未提交，导入原结果；不重新执行工具。若清理/结果缺失，需真人实际检查后提交 `actor`、`reason`、`effects_checked`。这种对账不是 exactly-once 外部执行保证。

## CLI

保存 `session.json`：

```json
{
  "identity":"my-research",
  "objective":"比较不可靠信息分析的代表性方法，解释来源依赖问题并设计验证实验。",
  "config":{"provider":"codex-config","max_output_tokens":2000,"timeout":120},
  "policy":{"review_mode":"milestones","project":"information-analysis"},
  "budget":{"model_calls":24,"tool_calls":80},
  "inputs":{"inputs/notes.md":"/absolute/path/to/notes.md"}
}
```

路径例子需改为本机实际位置。执行：

```text
python skills/_shared/runtime/research.py --store .research-agent agent-create session.json
python skills/_shared/runtime/research.py --store .research-agent agent-run my-research
python skills/_shared/runtime/research.py --store .research-agent agent-status my-research
python skills/_shared/runtime/research.py --store .research-agent agent-control my-research pause
python skills/_shared/runtime/research.py --store .research-agent agent-steer my-research "先解释来源依赖，再决定是否引入图像。"
python skills/_shared/runtime/research.py --store .research-agent agent-control my-research resume
python skills/_shared/runtime/research.py --store .research-agent agent-run my-research
```

`agent-feedback <session> feedback.json` 的字段为 `reference, actor, decision, reason`。`reference` 必须与当前 waiting.id 一致；decision 可为 answer/approve/reject/revise/comment/stop，具体请求另有约束。继续后再 `agent-run`；工作台回答问题后会自动启动已就绪会话。

`agent-recover <session> --reconciliation checked.json` 用于明确对账。`agent-run` 执行完成返回 0；待审、预算耗尽、失败等返回 3；无效命令/状态返回 2，不能把“待审”伪装成任务完成。

`agent-fork <session> continuation.json` 可提供新的 `identity/objective/config/budget/policy`；未提供项沿用父会话。尚有未对账活动调用时不能用续接绕过恢复。

## 人工监督的能力进化

新模块自动进入 `capability-list` 的 `runtime:*` 目标；既有 `skill:*` 与 `tool:*` 全部保留。改进提案可引用 Agent 的真实报告：

```json
{"agent":"my-research","report_id":"report-0001","feedback_id":"feedback-actual-id"}
```

`feedback_id` 可省略，若填写必须与该报告匹配。沿用 `capability-freeze/propose/evaluate/review/activate`，冻结标准、独立验收、实际研究者接受后才在后续运行采用。Agent 报告可说明哪里需要改进；本轮没有让运行中的 Agent 改写自己的权限、评估器或代码，也没有声称自动提升科学能力。

## 交付、验证与边界

`python build_agent.py --output dist/GResearchEvolver-Agent.zip` 生成包含全部技能、运行器、手册、例子和测试的确定性 ZIP，附文件哈希并检查 200 MB 上限；同一份源码重复构建得到相同 ZIP。依赖及模型按需外接，不把权重/环境/个人数据打进源码包。该 ZIP 是 Agent 项目包；比赛所需真实视频、PPT、码道证明仍须单独准备。

离线：`python -B tests/run_checks.py`。仅 Agent：`--pattern test_agent.py`。真实模型：`python -B tests/live_agent.py --output <新目录>`，会按脚本预算实际调用已配置模型，不能把这个小型流程检查当科研基准。

工作台只绑定 loopback，保留 Host/Origin/CSRF 检查，所有模型内容以文本显示。它不是多用户认证系统；不能直接暴露公网。当前实现为 Windows/Linux 单机持久化 Agent；高可用、租户隔离、公开服务认证、长时间压力测试与科学能力收益仍需独立验证。
