# 阶段报告、科研讲解与受控进化

本协议用于受管科研阶段。报告记录可核查的选择依据与执行事实，不记录隐藏思维链。人的反馈可改变执行方向；接受意见不等于科学论断成立。绘图/PPT 同样遵循该协议，专属要求见 [视觉工作的人类监督协议](visual-research.md)。

快速体验（输出目录需尚不存在）：

```text
python skills/_shared/examples/human_guided_research.py --output teaching-demo
python skills/_shared/runtime/research.py --store teaching-demo/state serve
```

默认示例生成报告和讲解，然后等待真实意见。使用 `--scripted-demo` 可运行明确标记的模拟反馈、修改分支、图谱保存、候选评估、采用和回滚；其中整数预测成绩只验证接口，不评价讲解能力，不构成用户研究。CLI 的 run 在等待审阅时返回状态 awaiting_review 和退出码 3，表示尚未完成。

## 建立协作流程

新科研编排默认建议 `hci.mode: every-stage`；用户希望减少中断时选 checkpoints 或 observe。沿用用户已明确选择的模式与授权，不反复询问同一事项。缺少 hci 字段的旧 manifest 保持 observe 兼容行为，但同样生成报告。

```json
{
  "version":2,
  "objective":"复现论文的主要统计结论",
  "authorization":{"effects":["local"]},
  "budget":{"seconds":300,"cost":0},
  "hci":{"mode":"every-stage","reviewers":["researcher"],"require_explanation":true},
  "stages":[{
    "id":"design","skill":"experiment-designer","goal":"确定独立研究单位和对照",
    "rationale":"先固定测量和比较条件，避免根据结果改变指标",
    "alternatives":["可先做探索分析，但其发现须用独立数据确认"],
    "instructions":"阅读绑定的研究材料，写出可证伪的研究协议与不足",
    "review_questions":["研究单位和主要指标是否符合科学问题？","有哪些现实约束需要修改？"],
    "outputs":["protocol.json"]
  }]
}
```

checkpoint 模式用 `hci.checkpoints` 声明 stage ID。observe 仍允许评论、要求修改、解释与停止；修改请求会建立明确的暂停状态。reviewers 是合作式操作者标签校验，不是远程身份认证；同权限恶意宿主不在本地协议的安全保证内。

## 每个阶段的 report.md

创建阶段、启动、完成、失败、取消、恢复、人工提交和反馈时，runtime 保存 `work/_reports/STAGE/attempt-N/REVISION-ID/report.md` 与 `report.json`。旧版本保持不变。自动重试的每次退出码/日志位于报告 facts.attempt_history；人工重试产生新的 attempt 周期。

报告包含目标、选择理由和备选方案、执行方法、输入/输出与日志哈希、完成情况、知识解释、待决定问题、真实反馈和下一步条件。缺失方法说明或讲解时如实显示“尚未记录”，不从成功退出编造科学发现。宿主应在建阶段时填写 rationale/instructions/alternatives/review_questions，并按需补充证据绑定的讲解。

分支复用的上游产物在 facts.inherited_from 中注明来源 run，不能当作新执行的重复实验。能力包检查包含文件集合，新增文件或执行中改写同样会拒绝接受；缓存与输出应写在包目录之外。

磁盘写入失败不能保证生成文件；数据库未提交的报告不作为成功记录。控制器意外死亡后先恢复运行，恢复会记录中断；`reports-rebuild` 只能从已有 CAS 恢复报告视图，不补造丢失的执行事实。备份和归档保留报告及反馈历史。

以下均为 `tool OPERATION request.json`，可用全局 `--output` 保存 JSON。

| 操作 | 请求 |
|---|---|
| stage-report | run、stage；可选 report_id 查看历史 |
| stage-feedback | run、stage、report_id、actor、decision、reason |
| stage-explain | run、stage、report_id、actor、bundle |
| stage-revise | run、stage、feedback_id、changes；可选 child |
| stage-memory | run、stage、report_id、project、expected_revision、actor、reason |
| reports-rebuild | run |

反馈绑定最新 report_id。approve 只接受空闲且完成、产物未变化、清理已确认的阶段；require_explanation 为 true 时还需要讲解。revise 保持暂停，用 stage-revise 建立具体修改分支，原运行和反馈保留；comment 只记录意见，不假装落实；explain 记录理解请求；stop 请求取消。resume/step 不绕过待审报告。新讲解使已审阅内容改变时会重新要求审阅。不存在自动代填研究者同意的接口。

控制台 `serve` 可阅读当前报告、提交上述反馈和建立修改分支。报告以纯文本显示，原始内容不会作为 HTML 执行。研究者不需要编辑数据库；CLI 与控制台使用同一状态协议。

`stage-memory` 将指定报告、讲解、原子论断、精确引文和反馈合并到项目图谱。保留现有节点/边，重复投影无变化时不增版本，并拒绝过期 revision。边使用 cites、span_of、responds_to 等来源关系，不自动生成“支持论断”的语义判定；随后可按原有流程 memory-sync 到 OpenViking。该操作自身只写本地 Store。

## 讲解格式

由宿主的 research-explainer 生成内容，runtime 核查结构和引用。不额外调用未经配置的模型或将正文上传至服务。

```json
{
  "topic":"为什么相关性不能直接证明因果",
  "audience":"beginner",
  "intuition":"两个量一起变化可能来自共同原因，需要排除其他解释。",
  "technical":"观察性关联需要额外的识别假设；随机化也需检查依从和测量。",
  "relevance":"决定本项目可以报告关联，还是可以提出因果解释。",
  "assumptions":["需要明确变量定义及数据生成过程"],
  "limitations":["本段是方法解释，尚未核验当前项目的识别条件"],
  "questions":["哪些变量可能同时影响处理和结果？"],
  "claims":[{"id":"claim-1","text":"本项目因果识别条件尚待检查","status":"unknown","citations":[]}]
}
```

source_reported 论断必须给出 citations：`path/sha256/start/end/quote`，path 必须属于记录的 inputs/outputs。字符位置针对 UTF-8 解码后的 Unicode 文本（去除 BOM），不是 PDF 字节偏移。原文字节与引文吻合不等于 entailment；解释中的事实、数字、否定、范围仍需语义检查。没有材料时用 unknown/hypothesis 明确缺口，不把未引用内容伪装成已证实事实。

## 所有科研能力的改进接口

`capability-list` 枚举注册 skill、CLI tool 和 runtime 模块。每个对象可绑定自己的任务、指标、失败定义、保护检查、成本与回归门槛。没有预置的万能分数，也没有声称所有对象已经完成能力提升。

1. capability-freeze：target、name、protocol、evaluator_dir、incumbent_dir、incumbent_command、actor、reason、reviewers。protocol 沿用 RSI 协议，另需 metric_description 和 failure_definition。任务/评分器/预算冻结；候选不能自行降低门槛。
2. capability-propose：target、epoch、candidate_dir、candidate_command、actor、reason、sources。sources 引用真实 run/stage/report_id，可附与该报告一致的 feedback_id。候选整包保存到 CAS，提出之后修改原目录不会偷偷改变被测候选。
3. capability-evaluate：identity、split。复用 RSI 的独立评分、配对比较、fresh audit batches、失败保留和超时清理；仅 audit 通过可进入采用审查。
4. capability-review：identity、trial_id、actor、decision、reason。研究者须在冻结 reviewers 中，标签不同于提案者；approve/reject 均保存。标签独立不是安全权限域，恶意候选应使用原有 Docker 与外部可信评分/签名边界。
5. capability-activate：identity、expected_revision、actor、reason。再次核对候选、基线、评分器、审查回执和清理状态；旧批准、负结果、final 成绩或过时基线不能激活。带签名的隔离协议生成独立的采用回执。
6. capability-rollback：target、index、expected_revision、actor、reason。恢复完整历史包并增加 revision，后续比较需冻结对应基线的新 epoch。历史失败、反馈和审计次数不清零。

capability-status / proposal-status 查询；capability-export 导出到新目录供宿主安装或独立代码发布。安装目录、运行中的 runtime、评分器和权限规则不会在进化循环内被覆盖。

阶段可显式声明 `capability: "skill:research-explainer"`（或其他已注册对象），command 中用 `{bundle}/agent.py` 等路径；占位符展开为相对运行工作区的固定目录。init 将当前活动包固化为 run 输入；未来激活/回滚不改变已有 run，分支和归档导入也保持原包。使用新版本需建立新 run。命令仍受原授权和预算约束，执行前后检查包字节。无 command 的宿主技能从 capability_pin 指向的目录读取提示/配置。SSH 使用显式导出部署，不隐式上传包。

已采用版本代表在声明任务上的证据和研究者选择，不代表普遍进步。人类理解效果要收集真实观测；本协议的状态测试与演示不能替代 HCI 用户研究。
