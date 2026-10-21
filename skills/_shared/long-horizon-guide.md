# 长程科研运行手册

长程项目在现有完整 Agent 上增加持久目标、共享预算和科学动作检查。普通会话仍可独立使用。只加载本技能包中的科研技能；图节点是科研条目，边是有类型的关系，OpenViking 的检索结果不替代本地图快照。

## 创建与续接

在 `/agent` 的“跨会话长期研究”填写项目 ID、目标、约束和总预算，先创建项目，再创建关联会话。不同会话可以关联同一个项目；项目总预算不会因新会话、fork 或上下文交接而重置。

CLI 的所有 JSON 操作用 `research.py --store <目录> tool <操作> <请求.json>`。创建项目：

```json
{
  "identity": "information-analysis",
  "objective": "研究来源相关且会修订的信息下的动态事件研判",
  "constraints": ["保存反例和负结果", "转载不能自动算独立证据"],
  "budget": {"model_calls":120,"tool_calls":400,"active_seconds":14400,"output_tokens":240000,"input_chars":12000000,"external_cost":0},
  "actor": "researcher"
}
```

保存为 `project.json` 后运行 `tool long-create project.json`。会话请求增加 `"long_project":"information-analysis"`：

```json
{
  "identity":"analysis-session-1",
  "long_project":"information-analysis",
  "objective":"先梳理背景、代表方案和未解决问题，逐阶段保存报告",
  "config":{"provider":"codex-config","max_output_tokens":2000,"max_input_chars":120000,"timeout":120},
  "budget":{"model_calls":120,"tool_calls":400,"active_seconds":14400,"output_tokens":240000},
  "policy":{"network":true,"review_mode":"milestones"}
}
```

`agent-create session.json` 后用 `agent-run analysis-session-1` 执行。两层预算同时生效；达到任意上限停止。输入字符是可复核的控制额度，不是精确 tokenizer 账单。输出按每次请求的上限保守预留，失败也计数；worker 时长有可核实回执才退款，未知耗时保留预留。外部成本单位由项目自行约定，应覆盖工作流 manifest 的预算；不是云账单自动抓取。

## 研究条目与真实人工决定

Agent 可通过 `project_status` 查看项目，通过 `project_note` 记录 `goal/hypothesis/route/finding/negative_result/experience`。条目需要 `expected_revision`，冲突后先重读。`prediction` 写入后不可改；观察结果写 `outcome`，证据使用真实 CAS 哈希。修改条目保留前版指纹和项目快照，不称为已验证收益。

研究者在工作台选择条目并提交方向意见，或调用：

```json
{"project":"information-analysis","text":"暂停图像分支，先验证来源依赖假设","actor":"researcher","target":"route-text-first","expected_hash":"实际显示的条目指纹"}
```

操作名为 `long-decide`。省略 target/expected_hash 表示整个项目。决定使旧动作绑定和旧科学审阅失效，并暂停相关会话、撤回未执行调用。不会假装撤销已发生的远程副作用。

## MemTX 与证据图

MemTX 核心已复制在 `_shared/vendor/memtx/`。每次运行检查 [上游文件清单](vendor/memtx/UPSTREAM.json)，采用独立 JSON 子进程处理其绝对导入。来源和许可见 [第三方说明](THIRD_PARTY.md)。不用安装同名 PyPI 包，也不运行上游 mock 工具。

`memory_transaction` 原生工具支持 `status/begin/stage/commit/abort/retrieve/view`。每次写操作需要实际当前 `expected_revision`；事务限定当前项目及当前 Agent。`begin` 的 `risk_level` 可为 low/medium/high/external_action。`stage` 使用原 MemTX 字段：

```json
{
  "tx_id":"begin 返回的真实事务 ID",
  "observation":{"source":"实际工具回执"},
  "extracted_memory":[{
    "memory_id":"source-result-v1",
    "entity":"某个独立实验的结果",
    "attribute":"estimate",
    "value":"与科研图节点 text/value 完全相同的内容",
    "confidence":0.7,
    "evidence_ids":["实际存在的 CAS 哈希"],
    "derived_from":[],
    "scope":"本实验适用范围"
  }]
}
```

这是字段形状，示例占位值不能作为证据。`commit` 只接收真实 tx_id；结论所用记录需经 upstream external_action 事务检查达到 action_safe。Agent 的 source.type/id/authority 由适配层固定，不能冒充导师或给自己高权威免检。置信度必须明确给出，**不代表专家审核或语义蕴含**。每版 memory_id 必须新建，避免覆盖旧记录。

研究图仍用 `memory-put/get/neighbors/search/invalidate`。科学动作声明 `requires={node_id:完整节点 fingerprint}`；`project_status` 提供当前指纹。节点应有明确可用状态（current/active/supported/validated/verified/committed）。相关状态是研究记录，不自动证明其内容正确。

依赖边方向为前提 → 使用者。`related_to/same_topic/cites/motivates/supersedes` 不触发依赖级联。其余边按依赖处理；同一结论的多个 supports 默认共同需要。确有不同替代支持路径时，在结论节点声明 `support_sets`，例如 `[["source-a"],["source-b","measurement-c"]]`，并覆盖全部 supports 前提。

`memory-invalidate` 实际调用上游 MemTX 级联，把受影响科研节点标为 needs_review，撤下旧边裁决但保留历史；可替代支持仍成立的结论标记 support_changed。这个声明不证明来源真的独立，研究者仍须检查范围。原文件不会删除，上游 compensation 日志也不表示实际远程回滚。

## 绑定动作与科学审阅

长程会话中的 `run_command`、`report_stage`、RSI 评估及能力改进提案先调用 `bind_action`。它绑定未来调用的**同一组完整参数**，加上：

- purpose：explore / experiment / conclude / learn。
- requires_json：实际使用的全部科研节点及当前指纹。
- conditions_json：实际人群、版本、测量条件等对象。
- reason：为什么需要这个动作。

explore 允许暂缺证据的探索，但报告保持 provisional。其他目的必须有明确前提；每条前提的 MemTX 值与图节点 text/value/sha256 对应，状态及祖先可用。图变化、记忆变化、人工方向变化、条件或版本失配时重新绑定。执行器在排队检查和 worker 执行前各检查一次；可信本机命令仍需原有精确审批。

默认 `require_review=true`：等待真实研究者审核当前前提与条件。工作台展示绑定内容，接受通过原 `agent-feedback` 保存。CLI 也可用 `long-review`，字段为 project、requirements、conditions、actor、reason。模型不能调用人类审阅／采用接口。

每个阶段调用 `report_stage`，包括原因、方法、发现、易懂解释、证据、限制与审阅问题。最终科学交付需要一个当前有效的 conclude 报告；仅有模型 final 文本或探索报告不会绕过这一检查。

## 上下文交接与恢复

达到上下文额度后，在所有调用结算且没有待审问题的边界自动交接。历史完整进入 CAS；项目约束、实际反馈、未报告动作、材料哈希与近两份报告传入新上下文。`read_context` 或工作台可分页读取每次归档。预算和原回执不重置，工具不因交接而重放。

默认最多 20 次交接。必保留信息装不下时进入 context_exhausted，交给研究者缩小任务或增加新会话额度。`agent-fork` 保留项目身份、原会话归档、实际反馈和所有材料；待审决定、未结算动作或外部等待不能借 fork 绕过。崩溃仍使用 `agent-recover`，未知外部副作用先实际对账。

续接会话可用 `read_context(epoch=0)` 分页读取父会话完整状态与原始历史；epoch≥1 为当前会话的自动交接归档。普通记忆 retrieve/view/gate 是只读查询，不更换快照、不触发无谓的重新审阅。

## 等待实验

先用既有 manifest 创建授权的 ready DAG。工作台“登记并执行工作流”会绑定 manifest 和预留成本；CLI 可分别执行：

```text
research.py --store <目录> tool long-track-job job.json
research.py --store <目录> run <已创建的工作流 ID>
research.py --store <目录> long-watch information-analysis --seconds 60 --resume
```

`job.json` 为 `{"project":"information-analysis","run":"真实 run ID","actor":"researcher","cost":0}`。涉及收费实验须填写实际约定的预留成本，并事先设置项目预算。Agent 用 `await_job` 挂起，不自行新建远程提交协议。

观察器读取真实工作流状态。完成后导入 `jobs/<run>/<receipt-prefix>/...`，按回执版本保存，不覆盖旧产物；先检查配额。失败、blocked、paused 或 awaiting_review 会转交人类处理，实际继续工作流后可再次等待。研究者暂停／取消的会话不会被结果擅自唤醒。观察器或浏览器服务重启后，可再次运行 long-watch／点击“检查结果并继续观察”。

## 从经验到受控改进

项目条目有真实 outcome 和证据后，`capability-propose.sources` 可使用：

```json
{"project":"information-analysis","note":"experience-1","note_hash":"实际条目指纹","snapshot":"包含该条目的项目快照"}
```

它只建立溯源，仍须 capability-freeze/evaluate/review/activate；不会自动晋升。新的 runtime 模块、工具和原全部技能继续可作为改进目标。

`doctor` 列出未结算项目预留和待完成任务。`verify` 检查快照／引用／归档链；`backup` 包含项目报告、图版本、MemTX 状态和上下文原文。它们核验完整性，不是敌对同权限进程隔离或科研真理认证。
