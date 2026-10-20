# PPTX 工具

```text
python skills/slides-builder/scripts/build_deck.py deck-spec.json --output deck-v1
python skills/slides-builder/scripts/deck_tools.py inspect deck-v1/slides.pptx --output inventory.json
python skills/slides-builder/scripts/deck_tools.py edit edit-spec.json --output deck-v2
```

共同的 version/purpose/audience/rationale/evidence_status/sources/claims 与 [图表 spec](../../figure-mimic/references/tools.md) 相同。SHA-256 绑定原始文件，来源关联不等于语义验收。每个新目录有 spec、artifact-manifest、report.md/report.json。基础构建器生成 16:9；其他比例、复杂母版或布局使用专用代码并保留同一证据/审阅契约。

## 创建

`slides[]` 每项：

- `title`、`notes`、`seconds` 必填；`claims` 引用论断 ID；可选 `backup:true`，备份页不计入主报告时长。
- `layout` 为 title/evidence/comparison/figure/discussion；`body` 为段落列表。
- `image:{source,alt_text}` 插入来源图片并保持比例；figure 布局整页给图，解释放 notes。
- `chart:{kind,source,x,xlabel,ylabel,series:[{y,label}]}` 从原 CSV 创建可编辑图表，kind 为 bar/line/scatter。line 为等间隔类别轴；非等间隔连续 x 应使用 scatter 或来源绘图。缺失和区间不被静默丢弃，改走明确绘制的来源图。
- comparison 用 `columns:[{title,body},{title,body}]`。

顶层可选 `font`、`presenter`、`duration_seconds`。不凭空补人名机构。输出 slides.pptx、speaker-notes.md 和 slides-ledger.json。文本布局检查是保守启发式，不证明实际字体渲染没有溢出。

## 原稿精确修改

先 inspect 得到真实页序、XML part 和 shape id。edit spec 增加 `deck_source`（共同 sources 中的 ID），以及：

```json
{"edits":[{"part":"ppt/slides/slide1.xml","shape_id":2,"run":0,"before":"原文字节对应的文本","after":"修改后的文本"}]}
```

`run` 是该对象内的 a:t 索引；inspect 的 text_runs 给出相同顺序，复杂对象可再读取 XML 确认。原文不匹配或形状不唯一时拒绝。多 run 不自动合并，保持排版语义。所有未改 ZIP 部件保留，源文件不覆盖。

## 实际渲染

Windows 安装 PowerPoint 时可使用：

```powershell
powershell -NoProfile -File skills/slides-builder/scripts/render_powerpoint.ps1 -InputFile deck-v1/slides.pptx -OutputDirectory deck-v1-render
```

工具以无窗口方式打开指定文件，生成 PDF、逐页 PNG 和引擎/源哈希回执；不关闭其他打开的演示稿、不修改插件或应用设置。受管运行应设置超时，并在 COM 失败时检查残留进程，不能随意结束用户已有 Office 进程。

Linux/其他环境可用已安装 LibreOffice 的 `--headless --convert-to pdf --outdir NEW_DIRECTORY INPUT.pptx`；使用隔离的临时 user profile 以免与现有实例冲突。缺少渲染器时不自动安装大型软件，也不宣称已完成视觉检查。

已有真实 PDF 后生成全页预览和 contact sheets：

```text
python skills/slides-builder/scripts/deck_tools.py preview-pdf deck-v1-render/slides.pdf --output deck-v1-preview
```

contact sheet 用于整体布局检查，文字/公式必须查看单页图；其输出不代表自动审美或科学审查通过。
