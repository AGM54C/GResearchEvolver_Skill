# 外部适配器与领域边界

宿主 LLM 调用应由具体 argv 或 host stage 记录：provider/model/version、输入材料哈希、temperature/seed（支持时）、调用 ID、实际输出、token/费用/耗时。不得声称 seed 保证语言模型确定。密钥走 env_from，日志分享前审查。

Latent Critic / ReCast 需要指定模型层的 hidden states、成功对照或监督训练、数据许可与计算预算。接口应提供 event IDs、features 的版本/哈希、候选参数/步骤、错误分数及校准报告；没有这些依赖时仅标 adapter_unavailable，不能用提示词评分冒充论文方法。

真值可得环境、DiscoveryWorld/领域模拟器、实验仪器、专业统计工具、定理证明器可作为 command stages 接入。区分执行成功、科学知识得分、机制解释和真实外部效度。湿实验/临床/法律等任务需领域适配与专业审核；通用编排不意味着覆盖所有学科方法。

外部可信 RSI scorer 要在不同权限域保管隐藏任务、评价代码和晋升密钥，仅返回带版本签名的成绩/失败摘要；本仓库不包含该部署。固定外部 anchor 的评分器校准由实际运行和人工审查完成，不能由本地哈希替代。
