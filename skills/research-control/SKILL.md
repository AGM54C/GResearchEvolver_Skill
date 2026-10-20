---
name: research-control
description: 让研究者查看原始证据并暂停、单步、批注、修改配置、分支重跑和比较科研工作流。
---

用 `serve` 启动仅监听 127.0.0.1 的控制台，或 CLI `status/events/control/annotate/fork/compare`。运行→科学阶段→事件层次应能回到输入/输出、原始日志及来源，而不是把模型摘要当隐藏思维链。

先显示阶段 report.md 中的目标、选择依据、方法、结果和待决定问题，再按研究者需要展开直观讲解、技术细节和原文。使用 stage-feedback 对当前报告提交 approve/revise/explain/stop/comment；不要把一般批注当作接受。待审报告阻止后续执行，修改请求通过 stage-revise 形成有具体配置变更的分支，原轨迹保留。用户新选的介入强度优先于默认每阶段审阅。

stage-memory 可将选定报告、讲解论断、引文与真实反馈合并为图谱 nodes/typed edges；expected_revision 防止覆盖并发修改。cites/responds_to 表示来源关系，不自动宣称科学支持。是否同步 OpenViking 由现有 memory-sync 配置和授权决定。

pause 在阶段边界生效；step 执行一阶段；cancel 终止受管本地进程树。host skill 进入 awaiting_artifact，由宿主交付后 finish；恢复前核查输入哈希。外部 SSH、数据库、仪器或服务状态不能假定已经回滚。

崩溃后先 `doctor/status/events`，再 `recover`；资源队列用 `queue-recover`。不删除锁文件、清空失败历史或跳过 cleanup_pending。失去回执时保留未知状态，实际核对后记录 reconciliation。严格复现用 environment-lock，迁移前用完整 backup/restore-backup；操作格式见 [运维手册](../_shared/harness-operations.md)。

SSH Linux 监督器提供取消、超时、心跳租约和后代清理回执；断线而未取到回执时，界面应显示清理未确认。研究 HCI 效果时使用 `study-plan` 冻结平衡交叉分配、`study-analyze` 分析真实观测；便利样本、专家审查和软件操作测试分别报告，空观测不能产生研究结果。

fork 从干预点前的文件 checkpoint 创建新 run，修改受影响阶段的 command/requires/optional/outputs/instructions/milestone/milestone_id，并重跑下游；原轨迹保留。跨运行先用唯一稳定 milestone_id 对齐，无 ID 时可匹配相同标签，再回退到 stage ID；显式 ID 冲突输出 alignment_conflicts 并保留未匹配项。声明匹配不证明语义等价，人工仍需核对科学目标。

人工批注可以挑战/修正/接受模型判断，附对象与理由；人为接受不等同科学正确。验证干预时另做重复未修改对照、遵循检查、环境与测量契约可比性检查（`intervention`）。更换均值/中位数、评价任务或指标口径不能直接认定改进。已授权的本地可逆操作不重复审批。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。

受管阶段遵循 [阶段报告、科研讲解与受控进化协议](../_shared/human-guided-research.md)：说明为什么这样做、具体方法与结果；由 runtime 保存版本化 report.md，按需调用 research-explainer，记录研究者的实际反馈并落实到暂停、修改分支或后续执行。改进本技能时使用 `capability-freeze/propose/evaluate/review/activate`，目标为 `skill:research-control`；未经冻结评估及研究者接受，不把候选标记为已采用或能力提升。
