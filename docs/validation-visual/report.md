# 科研视觉工具验证报告

日期：2026-10-20。检查者：开发代理；**真实研究者审阅仍为 pending**。本目录的 CSV、图和演示稿全部是明确标识的合成软件示例，不代表科研结果、能力提升或用户研究。

## 为什么这样验证

文件能生成不足以证明实际显示正确，更不能代替科学审查。本次分别检查输入/文件保真、真实 Office 渲染、研究者介入机制，以及换目录后的重建能力。具体科研问题、图型取舍和叙事采用留给研究者。

## 实现了什么、怎么检查

| 检查 | 结果 | 证据 |
|---|---|---|
| 全部离线回归 | 127 项通过，无跳过；包含 13 项视觉测试 | [checks.json](checks.json) |
| 真实数据图产物 | 多面板中文图、给定区间、散点、灰度、PDF/SVG/PNG；通过来源和尺寸检查 | [图](example/figure/figure.png)、[包内 spec](example/figure/spec.json)、[manifest](example/figure/artifact-manifest.json) |
| 图型与失败用例 | histogram/box/violin/heatmap 实际构建；源变化、真越界、反向区间、非正对数值及静默丢弃被测试 | test_visual.py 与 checks.json |
| 缺失与可移植重建 | SVG 折线保留缺失间断；删除原输入后从包内来源重建成功；旧输出不会被覆盖 | test_visual.py |
| 可编辑关系图 | SVG/draw.io/PDF/PNG；中文可见，PDF/PNG 中两条有向边均保留箭头 | [预览](example/diagram/diagram.png)、[可编辑图](example/diagram/diagram.drawio) |
| PPTX 创建 | 5 页原生文字、原生柱图、来源图片、对照页、讨论页；每页 notes 和 ledger | [PPTX](example/deck/slides.pptx)、[notes](example/deck/speaker-notes.md)、[ledger](example/deck/slides-ledger.json) |
| 其他原生图表 | line/scatter 实际构建并重新读取，数值为 2/3/2.5/4；该补充检查没有单独做 Office 渲染 | [additional-checks.json](additional-checks.json) |
| PowerPoint 实际渲染 | Microsoft PowerPoint 16.0 成功导出 PDF 和 5 页 PNG；回执绑定当前输入和输出哈希 | [PDF](example/powerpoint/slides.pdf)、[回执](example/powerpoint/render.json) |
| 精确文字修改 | 仅指定 XML slide part 改变，其余部件原解压字节保留；修改后也经 PowerPoint 成功打开/导出 | [修订 PPTX](example/edited-deck/slides.pptx)、[修订渲染](example/edited-render/render.json) |
| 实际视觉复核 | 开发代理逐页查看真实 PowerPoint PNG；未发现本例中文字缺失、主要内容裁切或遮挡，柱图值与来源一致；数据图与关系图另行查看 | [全稿预览](example/preview/pages/contact-01.png)，单页 PNG 在 powerpoint/ |
| 安装与 HCI | 安装后的四阶段示例初始为 awaiting_review；没有生成批准。专项测试实际推进渲染阶段，并验证 revise 后不自动完成 | additional-checks.json / checks.json |
| 元数据 | 两个 SKILL.md 的 quick_validate 通过 | [summary.json](summary.json) |

逐页观察：第 1 页中文标题/正文完整；第 2 页单系列使用一致颜色、零基线，保留 2/3/2.5/4；第 3 页中文区间图保持比例和标注；第 4 页两列未重叠；第 5 页讨论文字完整。脚注适合来源定位，不能替代讲者主动交代限制。该结论仅覆盖此合成样例及此渲染环境，不等于所有模板或投影条件都通过。

开发中曾出现离屏刻度误报、转换后箭头丢失、Windows 暂存目录权限问题和首次 PowerShell 执行策略阻断。修复与范围见 [调研报告](../VISUAL-SKILLS-REVIEW.md)。最终目录保留修复后的产物；不把开发中的失败隐写成首次全通过。

## 重建

在仓库根目录运行，输出选用不存在的新目录：

```text
python -m pip install -r skills/_shared/visual-requirements.txt
python -X utf8 -B docs/validation-visual/reproduce.py --chinese --output visual-check
powershell -NoProfile -File skills/slides-builder/scripts/render_powerpoint.ps1 -InputFile visual-check/deck/slides.pptx -OutputDirectory visual-check/powerpoint
python -X utf8 -B skills/slides-builder/scripts/deck_tools.py preview-pdf visual-check/powerpoint/slides.pdf --output visual-check/preview
```

--chinese 的示意图示例指定 Microsoft YaHei；其他环境可以修改 spec 为已安装字体，或先运行英文示例。本机脚本策略默认阻止 .ps1，验证时使用了获准的单次进程 ExecutionPolicy 参数，没有修改系统策略；应遵守使用环境自己的执行授权。

每个 figure/diagram/deck 包里的 spec.json 指向自身 inputs 副本。保留代码、版本和已安装字体即可单独重建；字体指纹不等于分发字体授权，工具不拷贝字体文件。不同渲染器可能产生字体替代、布局或文件字节差异。具体环境与输出指纹在 manifest 和 render.json 中。

## 研究者意见与下一步

尚未收到针对这些示例的真实研究者审阅。建议在真实任务中反馈：科学问题是否表达准确、需要哪种取舍、哪处会误导读者、哪些检查造成不必要负担。意见绑定实际图/页/关系和报告版本，再提出受控改进候选。

本次没有实施用户研究、科学能力对照基准或无人监管自进化。高级模板、动画、SmartArt、draw.io 应用内编辑、Beamer/Marp、外部生图和全色觉可访问性仍需相应环境与专项验证。
