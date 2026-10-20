# 科研绘图与科研演示：调研、实现与人工监督

调查日期：2026-10-20。目标是扩展 GResearchEvolver 的科研视觉能力，同时保留研究者对问题、证据解释、叙事方向和版本采用的决定权。

本轮从技能合集发现候选，检查了 10 个仓库的树及所选原文，并对其中部分工具源码做静态阅读。没有执行上游工具、遍历每个合集的全部技能，或进行同任务的跨工具能力竞赛。“相对完整”仅指本轮检查到的功能覆盖，不能推成全球最佳。

固定提交、所读文件、SHA-256、许可元数据和链接保存在 [sources.json](validation-visual/sources.json)。本项目新增实现没有复制上游代码、提示文件或素材。

## 哪些仓库值得用

| 仓库 | 本轮所见长处 | 限制与本项目的选择 |
|---|---|---|
| [Auto-Research-Skills](https://github.com/brycewang-stanford/Auto-Research-Skills) | 大规模科研技能发现入口，汇集多种来源 | 子模块的许可、质量和名称冲突需要逐个核对；目录数量不等于统一运行能力。用来找候选，不整包叠加 |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) | 按工具和工作流发现专业技能 | 索引链接可能过时，必须回到实际仓库和文件核对 |
| [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | scientific-visualization 覆盖来源、采样单位、缺失、颜色、物理尺寸、期刊要求与多格式导出；另有 slides/schematics | 本轮科学绘图方法覆盖较完整的参考。科学示意图部分偏生成式位图；PPT 路线包含模型依赖。吸收科学约束和检查，不把生成式图像当作定量证据 |
| [Haojae/scipilot-figure-skill](https://github.com/Haojae/scipilot-figure-skill) | 数据剖析后选图，中文字体、缺字、裁切、刻度、灰度与实际预览 | 专注数据图；不能替代示意图或 PPT。吸收先理解数据再选择表达，以及中文与实际导出检查 |
| [Orchestra-Research/AI-Research-SKILLs](https://github.com/Orchestra-Research/AI-Research-SKILLs) | academic-plotting 区分数据图与概念图，提供 ML 论文表达经验 | 不将某个生图模型、固定重试次数或突出 ours 视为通用要求；保留宿主和领域适配空间 |
| [anthropics/skills 的 pptx](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/pptx) | 本轮检查中，PPTX 创建、编辑、OOXML、原生图表、模板与渲染检查的说明较完整 | 该目录 LICENSE.txt 有明确限制；仅作功能对照，没有复制、改编或分发其文件。本项目用公开库独立实现小型工具，并如实区分高级宿主操作 |
| [zLanqing/codex-claude-academic-skills](https://github.com/zLanqing/codex-claude-academic-skills) | 中文学术 Office 工作流、模板保留、PowerPoint COM、原文与解读区分、讲稿 | 适合补中文和原生 Office 验证；本轮未运行其实现。顶层许可不能替代对子目录的检查 |
| [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill) | 可编辑源、稳定节点 ID、局部编辑、源变化同步、导出和关系检查 | 适合作为复杂图的专用路线；完整同步、自动布局和交互编辑器没有整体移植。新增基础工具保留节点/边和可编辑 SVG/draw.io |
| [chuspeeism/dashi-ppt-skill](https://github.com/chuspeeism/dashi-ppt-skill) | 多主题、多方案、浏览器编辑及 HTML/PDF/PPTX 路线 | 泛演示功能丰富，但科研证据绑定不是核心；有前端依赖及 AGPL-3.0 许可。借鉴代表页方案比较，没有移植主题库或浏览器编辑器，也不强制每页固定四案 |
| [openai/skills](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431) | 官方技能仓库入口 | 本次检查的完整树里没有 slides SKILL.md；不能因合集列出链接就声称当前实现存在 |

选择是组合能力：科学图规范主要参考 K-Dense 与 scipilot；PPT 创建/模板/原生渲染以公共库和 Office 能力独立实现；复杂关系图保留 draw.io 路线；代表页方案比较用于让研究者表达偏好。合集负责发现，具体任务按需加载参考。

## 原有不足与已做修改

| 类别 | 原有不足 | 本次落地 |
|---|---|---|
| 功能缺失 | 主要是文字流程，缺少包内可运行的绘图与 PPT 工具 | 新增数据图、节点关系图、PPTX 构建、对象清点、精确文字修改、PowerPoint 渲染和 PDF 预览工具 |
| 功能缺失 | 两个视觉技能被排除在能力进化目录之外 | 删除排除标记，注册 skill:figure-mimic / skill:slides-builder，复用实际 capability 冻结、提案、评估、研究者审阅、采用与回滚 |
| 功能缺失 | 无可运行的视觉阶段介入例子 | 新增 brief→数据图→示意图→PPT 四阶段示例，默认每阶段等待审阅；每阶段保存版本化报告 |
| 完善程度不足 | 概念图依赖生图，精确关系和可编辑性较弱 | 优先 SVG/draw.io 等确定性路线；显式节点、关系类型、箭头和可编辑源。生成式工具仅用于合适的概念素材 |
| 完善程度不足 | 样本必填、页数与讲稿字数固定，适用面窄 | 以科研问题、受众和时长决定；参考风格可选；保留旧输入及论文账本衔接 |
| 完善程度不足 | 自评分和文件成功容易被当作内容合格 | 分开记录文件检查、实际视觉检查、科学判断和理解效果；未执行项保持 pending |
| 完善程度不足 | 重建与失败记录不够具体 | 输入哈希、来源副本、可移植 spec、代码/依赖/字体记录、新目录事务发布、失败不冒充成功、已有版本不覆盖 |

两个技能入口仍为 [figure-mimic](../skills/figure-mimic/SKILL.md) 和 [slides-builder](../skills/slides-builder/SKILL.md)，避免破坏现有路由。旧的论文图号/claim_id/run/数字账本、参考风格画像、讲稿和证据表继续按需衔接，不要求独立作图任务创建空论文状态。

## 实际能运行到什么程度

- **数据图**：CSV 驱动的 line/scatter/bar/histogram/box/violin/heatmap 与多面板；给定区间、缺失间断、对数域检查、物理尺寸、PNG/PDF/SVG/TIFF、灰度预览。工具不估计 CI、不做显著性检验。
- **示意图**：显式盒子、节点、typed edges；可编辑 SVG/draw.io，加 PDF/PNG。检查越界、节点重叠、悬空边和预留 ID；箭头使用导出兼容的显式几何。复杂自动路由、排版和自环交给宿主或专用编辑器。
- **PPTX**：基础 16:9 构建器，五类布局、可编辑文字和原生 bar/line/scatter、图片比例、alt text、逐页来源与 notes、主报告时长。复杂区间图嵌入来源图并附绘图源，不伪称原生图表。
- **原稿修改**：精确定位 slide part / shape id / text run，核对 before 后替换；未改 ZIP 部件保留原解压字节。它不是通用动画、SmartArt、图表数据或母版编辑器。
- **渲染**：已安装的 PowerPoint 无窗口导出实际 PDF/逐页 PNG，回执绑定输入、脚本、输出和引擎。PDF 预览工具生成全页图和 contact sheet。缺少渲染器时如实交付待审草稿。
- **高级路线**：Beamer、Marp、专用统计图、科学图像处理、交互图、复杂模板和生成式素材由宿主按需执行，并遵守同一来源/报告/审阅契约；本轮没有将这些全部实现成独立一键后端。

工具入口及字段见 [图表接口](../skills/figure-mimic/references/tools.md) 和 [PPTX 接口](../skills/slides-builder/references/tools.md)。工具是可复用基础组件，不能据此声称覆盖上游所有高级功能或已达到工业服务等级。

## RSI 与人的科研判断

科研 taste 包含什么问题值得研究、什么证据足够、何时需要改变方向，以及如何向特定读者解释。这些不会被替换成一个 AI 审美分数。

1. **人确定方向**：brief/storyboard 记录科学问题、目标读者、主张边界和取舍；已有明确指示直接沿用。改变研究问题或提高论断强度要重新交研究者判断。
2. **AI 提出有限改进**：从具体故障、误读或真实反馈提出候选，说明对象、理由、预期收益及代价。字体修复、图表布局和叙事偏好分开处理。
3. **冻结后比较**：固定基线、数据、模型/渲染器、预算、科学保护条件和评价方式；验收材料不能反复当作开发样例。既记录提升，也记录回归和失败。
4. **研究者审阅采用**：评估通过仍须 review/activate，不能自动批准自己、改评分器或将超时当成同意。版本用于显式绑定的新运行，保留旧运行与回滚。
5. **持续可介入**：brief、预览、交付均有 report.md；反馈绑定页/对象/论断及当前报告，可 revise/explain/stop。已有 stage-memory 将材料、反馈和版本投影为科研 nodes/edges，OpenViking 存储形式不变。

这是**人类监督的受控进化**。宿主负责提出实际候选；运行时没有新增无人监管的持续优化器，更没有证明开放式 RSI 或科研能力增长。本地部署的 reviewer 名称是身份标签，不能单靠它抵御同权限恶意进程冒充人；对抗隔离仍依赖可信外部评估/签名权限域与人工控制面。详细协议见 [visual-research.md](../skills/_shared/visual-research.md)。

## 验证与发现的缺陷

本机 Windows / Python 3.13.3 的 **127 项离线测试通过**，其中 13 项新增视觉测试。完整结果和运行源码哈希见 [checks.json](validation-visual/checks.json)。新依赖纳入现有 CI 测试安装清单；本报告不把本地通过称为云端 CI 已通过。

专项检查实际构建图和 PPT，核对原生图表值/notes、PDF 物理尺寸、缺失值线段、给定区间、源文件变化拒绝、原输入移走后的重建、旧输出保护、模板未改部件，以及真实渲染阶段的审阅暂停和修订阻断。共享测试继续覆盖提案不能直接晋升、过期批准、候选篡改、绑定与回滚。测试里的 scripted reviewer 不是用户研究数据。

开发过程中发现并修复：

- Matplotlib 预先生成但不绘制的离屏刻度造成越界误报；现在排除这些刻度，同时测试真正超长标题仍被拒绝。
- SVG marker 箭头在实际 PDF/PNG 转换中丢失；改为显式箭头几何，并检查导出的 PDF 确实保留箭头。
- Windows 的私有临时目录权限随改名保留，导致其他工具读不到已发布产物；暂存目录改为继承目标父目录权限，并验证普通文件工具可读取。
- 产物 spec 原先依赖原位置的来源路径；现在绑定包内来源副本，测试删除原输入后仍可重建。
- PowerPoint 初次执行被本机脚本策略阻止；实际验证使用获准的单次进程设置，没有更改系统执行策略。

两个 SKILL.md 已通过 skill-creator 的 quick_validate。另做安装后示例检查，初始状态确实停在 awaiting_review，没有合成人工批准。中文图、示意图和 5 页合成演示均已实际生成，PPT 使用 Microsoft PowerPoint 渲染后逐页检查；相关记录见 [验证报告](validation-visual/report.md) 与 [示例 PPTX](validation-visual/example/deck/slides.pptx)。

这些检查支持“工具在所测条件下工作、保留来源与介入机制”，不支持科研能力提升、读者理解提升或审美优于其他产品。未开展视觉工具对照能力基准和 HCI 用户研究；未实测复杂大学模板、SmartArt/动画编辑、Beamer/Marp 导出、外部生图服务、全色觉可访问性、draw.io 应用内编辑或 Linux Office 渲染。后续改进应由真实任务与研究者反馈驱动。

## 复现与反馈

```text
python -m pip install -r skills/_shared/visual-requirements.txt
python -X utf8 -B docs/validation-visual/reproduce.py --output visual-check
python -X utf8 -B skills/_shared/examples/visual_research.py --output visual-human-demo
python skills/_shared/runtime/research.py --store visual-human-demo/state serve
```

中文示例可加 --chinese，需要已安装相应中文字体。输出必须使用新目录。PowerPoint 渲染和预览命令见验证报告。跨环境需要核对字体与渲染器；保存配置与内容重建不等于文件字节完全一致。

研究者后续最有价值的反馈是具体对象与理由：哪张图造成误读、哪页加强了本不该加强的结论、哪个布局妨碍理解、哪项修订改变了自己的判断。意见进入新的报告/反馈记录后，才成为能力改进提案的依据；不会把本报告自动当作人工接受。
