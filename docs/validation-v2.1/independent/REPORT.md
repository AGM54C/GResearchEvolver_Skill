# v2.1 独立前向验收

本次完成了候选隔离、签名晋升、语义证据接口及人工分析相关接口的独立行为验收。初检实际发现五组问题，对应九个失败输入案例；实现者修订后，我使用保留的原始案例另建源码快照复核，全部已修复。真实容器隔离与签名晋升流程也已实际跑通。

这个结论限于本报告执行的本地边界与接口行为。本次没有模型服务调用、真实编码器推理或外部语义测试集，不证明语义正确率、校准性能或科研能力提升。

## 输入、权限与独立性

- 阅读了 `skills/rsi-evolver/SKILL.md`、`skills/research-control/SKILL.md`，以及 `isolation.py`、`container_worker.py`、`attestation.py`、`semantic.py`、`evolution.py`、`representations.py` 和必要依赖。
- 自行构造合成文本、手工向量、微型预测策略、错误回执与故障注入，没有使用产品测试断言作为答案。
- 没有修改产品源码。初检快照为 `runtime-snapshot`，修订复核快照为 `regression/runtime-fixed-snapshot`，分别保留文件 SHA-256。
- 没有访问网络、拉取镜像或调用模型。真实 Docker 测试使用本机已有的固定镜像 `sha256:e91c87665910d2f7979f01464eb9fc8205550b1e4e64cebdca96ef5a746e65fb`，容器网络为 none。
- Docker 客户端使用本目录的空配置，签名仅使用新生成的专用测试密钥，没有使用用户凭据。`test-keys/public.json` 与签名回执足以独立验证签名；这里的签名密钥只用于此合成测试。
- CLI/文档接线并非本次否定依据；直接使用相同运行模块的公开函数检验已实现行为。

## 实际完成的使用

本地初检包含 43 个接口/行为案例。这是测试案例数，不是独立科学样本量。其中正常行为包括：有效 Ed25519 回执验签、修改签名内容拒绝、调用者固定上下文不符拒绝、重复接受回执拒绝、非 audit 或未晋升回执拒绝、来源哈希错误拒绝、无法绑定原文或低置信度时弃答、模型响应未完成时弃答、分组跨数据划分泄漏拒绝、编码器身份与向量维数不符拒绝，以及人工更改 estimand 后不认定改进。

实际执行了一个微型本地策略评估：首个候选以退出码 17 失败，消耗 fresh audit batch 0；后一个正确候选使用独立 batch 1 并晋升。另一个评分成功但签名配置暂不可用的运行没有晋升，active 保持原值。证据在 `fresh-batch-runs.json` 与 `local-cases/evolution-*.json`。

真实 Docker 隔离执行包括：

| 案例 | 实际观察 |
|---|---|
| 权限探测 | 候选 uid/gid 为 65534；没有继承控制器的测试环境变量或签名路径环境变量；看不到 scorer 与 private task |
| 文件边界 | 对 `/state/result.json`、策略目录和输入文件的写入均失败；可读取本次明确提供的合成 public input |
| 网络配置 | 候选只观察到 loopback 网卡；没有尝试任何外部连接 |
| 符号链接输出 | 指向 `/etc/passwd` 的 prediction 被拒绝，没有导出内容 |
| FIFO 输出 | 非普通文件被拒绝，没有阻塞等待或导出 |
| 脱离进程组的子进程 | 子进程未能延迟替换导出的父进程结果 |
| 超时 | 候选失败并记录回执，所属容器删除成功 |

这些容器均由本次测试创建，五个探测案例的回执均记录删除成功。

随后执行了真正隔离的三任务 audit：候选与基线的六次策略进程均在 Docker 中，评分与签名在容器外。冻结门槛通过后 active 实际切换，生成的 Ed25519 回执在调用者独立构造的预期上下文下被接受；`result_hash` 与签名前结果内容重算一致。该过程使用简单的合成倍增任务，只验证运行链条。

证据：`docker-summary.json`、`docker-results.json`、`isolated-signed-evolution.json`，以及 `docker-runs`、`docker-evolution-store/rsi/isolated-signed` 的逐次原始日志和预测。

## 发现、修订与独立复核

初检失败记录没有覆盖。下表描述修复前实际返回，以及修订后相同接口输入的复核结果。

| 问题组 | 修复前观察 | 独立复核 |
|---|---|---|
| 签名上下文缺少值验证 | 已签名 receipt 与 expected 的五个固定字段均为 null 时，`accept` 返回 `accepted:true, candidate_hash:null` | 相同空上下文现在被拒绝；正常固定上下文仍可验签 |
| 评价标签与 ID 校验 | 未知标签得到 accuracy=1、coverage=1，但 confusion 全零；gold=abstain 得到“弃答计错准确率”1；重复 ID 被重复计数；critic 训练 A/B/C 类时继承该错位 | 未知标签、gold abstain、重复 ID、critic 的未知目标类均拒绝；合法混合弃答输入仍得到正确结果 |
| 诊断模型参数校验 | 把三类模型的 intercept 截成一个元素，预测静默变成单类别 confidence=1；NaN 系数产生 NaN 置信度与概率 | 截断模型及非有限参数均拒绝；合法原模型仍产生完整三类有限概率 |
| Docker 错误路径清理 | 模拟 Docker logs 传输异常后，finally 再次抛出，未调用 rm，也没有保存 receipt | 原故障输入现在尝试清理并保存 failed receipt；新增的创建回执超时也保留清理与回执 |
| 不确定的反驳结论 | 高置信度 contradicts，但六项 aspects 全为 uncertain，仍输出 contradicts，problems 为空 | 原响应现在 abstain；有明确 polarity inconsistency 的正常反驳仍可输出 contradicts |

上述空上下文问题是签名授权接口的输入验证缺口，不是破解 Ed25519 或无私钥伪造签名。测试使用了自建的可信测试签名者来产生格式不合格的有效签名回执。

清理问题的初检使用明确标注的模拟传输，不声称当时真的留下了容器。修订后又进行了两项**真实容器**故障注入：

1. 容器正常启动、候选完成后，在客户端日志读取适配器抛出异常。
2. Docker 实际创建容器成功后，在客户端模拟创建确认消息丢失。

两项均返回 failed receipt、尝试且成功删除容器；之后使用未打补丁的真实 Docker inspect 独立确认容器不存在。没有为测试停止 Docker 服务或影响其他容器。

修订复核的 15 个针对性案例全部通过，包括正常正例以排除“一律拒绝”的伪修复；另两个真实容器故障案例也全部通过。修订未由本评估者编写，复核没有修改产品文件。

证据：`regression/summary.json`、`regression/results.json`、`regression/real-docker-fault-summary.json`、`regression/real-docker-fault-results.json`。

## 科学与部署边界

- **语义不是由字符匹配证明的。** 我故意将一个儿童受益论断配上成人无效果原文，构造一个“所有 aspects 一致、高置信度”的错误模型回答；验证器仍可返回 supports，但明确 `human_adjudicated:false`。这说明精确原文绑定和格式审查不能替代语义模型的外部准确率评估或人工裁决。此次没有真实模型调用，不能从这些 fixtures 推断模型实测效果。
- **置信度没有得到概率校准证明。** 自报置信度阈值、少量 calibration 样本上选择的诊断阈值，均不能被表述为经过保证的正确概率。模型输出保留相关边界字段，这是必要的。
- **手工向量不是实际隐层。** 本次对 `train_critic`/`predict_critic` 的分析使用标注为合成的二维向量，只检验划分、训练接口与参数验证。没有运行 `encode`，没有声称复现隐层方法或测量真实编码器表现。
- **人工干预结论仍有条件。** 相同 measurement_contract 的合成正例能分析，更换平均/中位 estimand 会被阻断；但合同内容、控制重复和环境可比性仍由调用方如实声明，不由这次接口测试证明。
- **容器不是独立信任机构。** 实际候选隔离有效，但仍信任 Docker 守护进程、内核、控制器、评分器和签名者。签名证明指定评价方签了该结果，不证明评分器科学有效或审计样本无污染。
- 本次没有覆盖所有恶意内核利用、长期并发恢复、所有 OOM/磁盘配额边界或跨主机签名信任配置。没有把本次成功描述为完整安全证明。

在本次给定接口范围内，所有实际报告的实现缺陷均已得到修复并通过独立复核；未产生新的未解决实现缺陷。上述边界应继续保留在产品解释与实证报告中。

## 证据位置与复现

全部产物根目录：

`C:\Users\ROG\Downloads\LLM-hallucination\.tmp-ai4research-v21\forward-v21`

主要入口：

- `local_checks.py`：43 个独立本地初检案例。
- `local-results.json`、`local-summary.json`、`local-cases`：初检观察及九个原始失败记录。
- `tested-source-hashes.json`、`runtime-snapshot`：初检被测源码身份。
- `semantic-source-fixtures.json`、`critic-fixture.json`：合成原始输入及明确标注的离线响应 fixture。
- `docker_checks.py`、`docker-summary.json`、`isolated-signed-evolution.json`：真实隔离与签名晋升使用证据。
- `regression_checks.py`、`regression/results.json`、`regression/summary.json`：原失败案例修订复核。
- `regression/tested-source-hashes.json`、`regression/runtime-fixed-snapshot`：修订复核被测源码身份。
- `docker_fault_recheck.py`、`regression/real-docker-fault-results.json`：真实容器故障注入与独立删除核查。

脚本按一次性工作区编写，固定路径用于可审阅性。重做应使用新目录并修正对应根路径，避免覆盖本次历史或复用原验收次数。产品仍在继续接线，因此本报告的结论绑定于记录的源码哈希，而非对任何未来版本的无条件保证。
