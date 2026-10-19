---
name: research-control
description: 让研究者查看原始证据并暂停、单步、批注、修改配置、分支重跑和比较科研工作流。
---

用 `serve` 启动仅监听 127.0.0.1 的控制台，或 CLI `status/events/control/annotate/fork/compare`。运行→科学阶段→事件层次应能回到输入/输出、原始日志及来源，而不是把模型摘要当隐藏思维链。

pause 在阶段边界生效；step 执行一阶段；cancel 终止受管本地进程树。host skill 进入 awaiting_artifact，由宿主交付后 finish；恢复前核查输入哈希。外部 SSH、数据库、仪器或服务状态不能假定已经回滚。

SSH Linux 监督器提供取消、超时、心跳租约和后代清理回执；断线而未取到回执时，界面应显示清理未确认。研究 HCI 效果时使用 `study-plan` 冻结平衡交叉分配、`study-analyze` 分析真实观测；便利样本、专家审查和软件操作测试分别报告，空观测不能产生研究结果。

fork 从干预点前的文件 checkpoint 创建新 run，修改受影响阶段的 command/requires/optional/outputs/instructions/milestone/milestone_id，并重跑下游；原轨迹保留。跨运行先用唯一稳定 milestone_id 对齐，无 ID 时可匹配相同标签，再回退到 stage ID；显式 ID 冲突输出 alignment_conflicts 并保留未匹配项。声明匹配不证明语义等价，人工仍需核对科学目标。

人工批注可以挑战/修正/接受模型判断，附对象与理由；人为接受不等同科学正确。验证干预时另做重复未修改对照、遵循检查、环境与测量契约可比性检查（`intervention`）。更换均值/中位数、评价任务或指标口径不能直接认定改进。已授权的本地可逆操作不重复审批。

按需读取 [共享运行规则](../_shared/README.md) 与 [接口示例](../_shared/runtime-guide.md)。旧评分 rubric 是启发式质量清单，不能代替实际证据和独立验收。
