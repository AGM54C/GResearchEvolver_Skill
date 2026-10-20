# 阶段协作与受控能力进化：实现及验证

2026-10-20。本轮将阶段报告、科研讲解和研究者反馈接入执行状态，并为所有范围内技能、工具操作和 runtime 模块增加统一的受控改进接口。绘图/PPT 未扩展。用户研究仍使用 [现有方案](HCI-STUDY.md)，本次没有生成或宣称真实用户研究结果。

## 可使用的流程

新增 research-explainer，技能总数为 26。它围绕研究者的理解或决策问题，提供直观解释、技术细节、成立前提、限制与讨论问题；论文报告、解释、假设和未知项分开标注。引用核验绑定输入/输出的 SHA-256、UTF-8 文本与精确字符位置。

每个受管阶段都有版本化 report.md/report.json。报告记录选择理由、备选方案、执行方法、结果/日志哈希、失败与阻塞、讲解、待决定问题和实际反馈；缺少说明时直接标明尚未记录。创建、执行、恢复、人工提交和反馈产生相应版本；心跳不反复生成相同报告。分支复用的上游阶段注明 inherited_from，不能当作新重复实验。

新编排建议每阶段审阅，也支持指定检查点或仅观察；旧 manifest 保持 observe 兼容行为。接受、修改、解释请求、停止和评论有不同执行效果。待审或修改请求不能通过 run/resume/step 绕过；接受前复核产物、输入、可选输入的原始缺席状态、引用来源和能力包。修改以分支保存具体变化，取消状态不能被反馈或重试重新启动。

能力目录包含 24 个范围内技能、82 个工具操作和 30 个 runtime 模块。每个对象可冻结专属任务、指标、失败定义、预算和评分器，提出绑定报告/反馈的候选。通过实际 audit 后仍需研究者明确接受，才能原子选择新版本。旧运行、分支及归档导入固定原能力包；新运行显式采用新版本。回滚恢复整包且增加版本号，后续比较需新 epoch。runtime/内置工具代码变化通过导出、独立审查、测试和发布集成。

stage-memory 将报告、讲解、论断、引文与反馈合并为科研图谱节点，使用 cites、span_of、responds_to 等关系边；保留既有条目并检查 revision。它可沿用 OpenViking 同步接口，引用关系本身不自动变为科学支持关系。

详细接口和可运行示例见 [人机协作协议](../skills/_shared/human-guided-research.md)。默认示例等待真实反馈；只有显式 `--scripted-demo` 才执行标记为脚本测试的反馈、采用与回滚。

## 已执行检查

| 检查 | 实际结果 | 原始记录 |
|---|---|---|
| Windows 11 / Python 3.13.3 离线全量 | 114 项通过，0 跳过 | [windows.json](validation-human-guided/windows.json) |
| Linux / Python 3.11.10 离线全量 | 114 项通过，0 跳过 | [linux.json](validation-human-guided/linux.json) |
| 真实 Docker 与 Ed25519 采用流程 | 6 次隔离候选/基线运行；测量篡改拒绝、采用签名、防重放通过 | [signed-adoption.json](validation-human-guided/signed-adoption.json) |
| 安装与技能元数据 | 26 个技能通过；安装后能力目录及两种示例通过 | [installation.json](validation-human-guided/installation.json) |
| 控制台 | 真实 HTTP 报告读取、鉴权、过期反馈、执行门控测试通过；JavaScript 语法检查通过 | 全量及安装回执；未进行浏览器用户测试 |

Windows 依赖为 cryptography 46.0.3、NumPy 2.2.6、PyMuPDF 1.26.5；Linux 使用缓存镜像的 cryptography 43.0.1、NumPy 1.26.3，并离线安装 PyMuPDF 1.26.5。两端具体依赖记录在回执中；这里验证了这两个环境，不宣称它们是相同环境。Linux 测试在只读挂载源码的本地副本上运行，禁用网络。镜像固定为 `sha256:e91c87665910d2f7979f01464eb9fc8205550b1e4e64cebdca96ef5a746e65fb`。

本轮新增 22 项离线检查，涵盖反馈状态转换、过期/篡改拒绝、真实修改分支、历史报告恢复、图谱保留、候选冻结、直接晋升绕过拒绝、平局保留、旧基线/旧审查拒绝、采用后实际执行新版本、旧版本迁移、原子注册和签名区分。全量回归还发现 Windows 短超时可能以 EINVAL 返回已关闭的启动管道；现已统一结算监督器回执并确保等待退出，增加真实进程加故障注入的回归检查。

可查看 [默认待审报告](validation-human-guided/manual-report.md) 和 [脚本反馈后的阶段报告](validation-human-guided/scripted-report.md)。报告原始 JSON 与对应 summary 同目录保存；summary 中本地路径是执行时的位置，临时工作目录在验证后可清理。报告正文、回执和哈希保留，未把脚本标签改成人类观测。

```text
python -B tests/run_checks.py --report validation.json
python -B tests/live_capability.py --image sha256:e91c87665910d2f7979f01464eb9fc8205550b1e4e64cebdca96ef5a746e65fb --report signed-adoption.json
```

离线回执记录 runtime/tests 的源文件哈希；安装回执记录实际安装字节。GitHub Actions 在 push/PR 后运行独立矩阵，配置存在不等于该提交已通过，应查看对应提交的检查记录。

首次云端运行发现测试依赖清单漏了诊断器边界检查导入的 scikit-learn；本机预装环境掩盖了这个缺口。现将兼容 Python 3.10/3.13 的 scikit-learn 1.7.2 加入 CI 清单，保留原测试要求，不跳过失败项。Windows/Python 3.10 又检出了旧 pathlib 对带扩展前缀路径的解析差异；safe_path 现先显式拒绝根路径及所有父目录段，再检查解析后的路径归属。本地回执已按此最终 runtime 更新。

## 结论范围

这些结果支持已测状态协议、恢复行为、版本固定和签名接口可执行。整数预测分数只是集成测试，不能证明讲解能力、通用科研能力或人类学习效果提高。每种能力的真实评估契约仍需相应领域任务与测量；“可提出并验证改进”也不等于每个对象已经改善。

审阅者名字是合作式审计标签，不是多人身份认证。同权限本地候选仍能访问宿主资源；不可信候选需启用隔离，并将评分、隐藏数据和签名密钥保留在可信权限域。Docker 的宿主内核/daemon 仍受信任。引用结构与哈希核验不证明 entailment，研究者接受也不替代领域判断。本轮没有改写历史验证结果，未重复宣称 OpenViking、远程 SSH、模型或 Lean 在新条件下的线上实测。
