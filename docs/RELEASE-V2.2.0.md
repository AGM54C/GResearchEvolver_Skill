# v2.2.0 — Human-supervised research and visual workflows

本版汇总 v2.1.0 之后的执行可靠性、人机协作、科研记忆与视觉工具改进。研究者掌握科学方向、证据取舍和版本采用；AI 负责提出候选、执行和报告可核查结果。

## 主要变化

- **执行与恢复**：进程托管、崩溃后代清理、分类失败与有界重试、环境漂移检查、队列恢复和完整备份。
- **科研记忆**：OpenViking 适配保留科研条目节点、typed edges、版本与证据历史，支持同步和回执对账。
- **阶段报告与讲解**：版本化 report.md/report.json、分层知识解释、绑定当前版本的反馈，以及暂停、解释、修订分支和停止。
- **受控能力进化**：技能、工具和模块可提交候选，经过冻结评估、研究者审阅、显式采用和整包回滚；新版本不替换旧运行中固定的包。
- **科研绘图**：多面板 CSV 图、给定区间与缺失值处理、中文字体检查、PNG/PDF/SVG/TIFF，以及可编辑节点关系图。
- **科研 PPT**：原生文字/图表、讲稿、逐页证据表、精确文字修改、实际 PowerPoint 渲染、逐页预览和来源哈希。

两个视觉技能继续使用 figure-mimic / slides-builder 名称。来源副本和可移植 spec 随产物归档；视觉阶段与其他科研阶段共用人工介入和能力进化协议。

## 验证与边界

本地 127 项测试通过，包括 13 项视觉测试。中文图、示意图及 5 页合成 PPT 已实际生成；原稿和精确修改后的 PPT 均经 Microsoft PowerPoint 16.0 打开、导出。安装后的示例实际停在 awaiting_review，没有合成人工批准。

所有示例均明确标为合成软件测试材料。测试和渲染通过不能证明科学结论正确、科研能力提升或用户理解改善；本版没有新增用户研究，也没有无人监管的持续自进化器。复杂模板、动画/SmartArt、Beamer/Marp 和其他高级路线的支持及未实测范围见调研报告。

默认本地 reviewer 是可信流程中的身份标签。对抗性隔离仍依赖可信的评估/签名权限域与人工控制面，不能把哈希或身份字符串当作完整安全边界。

## 下载与使用

下载 GResearchEvolver-v2.2.0.zip，并使用 SHA256SUMS.txt 核对。解压后：

```text
python install.py --dest /your/host/skills
python -m pip install -r skills/_shared/visual-requirements.txt
python skills/_shared/examples/visual_research.py --output visual-demo
python skills/_shared/runtime/research.py --store visual-demo/state serve
```

已有安装使用 --force 进行带备份的整包替换。输出目录应为新目录。PowerPoint 或 LibreOffice 渲染依赖本机实际安装；没有渲染器时不能声称视觉检查完成。

- [科研视觉调研与改造](https://github.com/AGM54C/GResearchEvolver_Skill/blob/v2.2.0/docs/VISUAL-SKILLS-REVIEW.md)
- [视觉验证记录](https://github.com/AGM54C/GResearchEvolver_Skill/blob/v2.2.0/docs/validation-visual/report.md)
- [人机协作协议](https://github.com/AGM54C/GResearchEvolver_Skill/blob/v2.2.0/skills/_shared/human-guided-research.md)
- [Harness 验证与部署边界](https://github.com/AGM54C/GResearchEvolver_Skill/blob/v2.2.0/docs/HARNESS-RELIABILITY.md)
