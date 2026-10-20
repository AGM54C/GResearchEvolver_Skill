# 本地工具接口

```text
python skills/figure-mimic/scripts/build_figure.py figure-spec.json --output figure-v1
python skills/figure-mimic/scripts/build_diagram.py diagram-spec.json --output diagram-v1
```

输出目录必须不存在，失败不会发布半套结果。工具只读声明的来源，结束前再次检查来源哈希。每包包含 spec.json、inputs 中的来源副本、artifact-manifest.json、report.md/report.json；spec 的来源路径指向包内副本，便于移走原目录后重建。manifest 记录代码与依赖、输入输出哈希和可用的字体指纹，human_review 始终 pending。分享产物包之前检查其中的来源副本是否适合分享。

## 共同字段

```json
{
  "version": 1,
  "purpose": "比较测量值及其不确定性",
  "audience": "本领域研究者",
  "rationale": "保留原始值和缺失位置，便于核对",
  "evidence_status": "research",
  "sources": [{"id":"data","path":"results.csv","sha256":"实际文件的 SHA-256","label":"实验 run 标识"}],
  "claims": [{"id":"c1","text":"这里填写实际论断","status":"unknown","evidence":[]}]
}
```

来源路径相对 spec 文件。示例哈希不是有效输入；宿主先从真实字节计算。claims 状态为 source_reported/interpretation/hypothesis/unknown/illustrative。source_reported 必须有 evidence，每项为 source、locator；可附 UTF-8 文本的 start/end/quote 进行精确引文核验。locator 可以指向 PDF 页/图/表或 CSV 行列；它本身不是语义证明。

## 数据图字段

- `size_mm:[width,height]`、`dpi`、`font`、`font_size`、`formats:["png","pdf","svg","tiff"]`、`columns`、`caption`。
- `panels[]`：`kind/source/title/xlabel/ylabel/claims`。
- line/scatter/bar 使用 `x` 列和 `series:[{y,label,color?}]`。bar 基础工具支持单系列；复杂分组/堆叠图用专用代码并保留来源契约。
- line/scatter/bar 的 `interval:{low,high,definition,sampling_unit}` 指向原 CSV 的区间列，不重新估计。line 显示区间带，scatter/bar 显示误差棒。其他图型拒绝 interval，避免静默丢弃。
- histogram：`series` 同上，`bins` 给出覆盖所有观测的明确递增边界。
- box/violin：每个 series 是一组原始观测列，显示所有点；不做统计推断。
- heatmap：`columns` 为矩阵数值列，可给 `row_labels`；必填 `colorbar`。可指定 `vmin/vmax/cmap`。
- 可选 `xscale/yscale` 为 linear/log、`xlim/ylim`。对数图拒绝非正观测。CSV 空字符串/NA/NaN/null 记缺失；线保持缺失间断，不插值。

自定义图不受上述类型限制。宿主可编写普通 Matplotlib/Seaborn/Plotly 脚本，使用 `_shared/visual_artifacts.py` 的来源核验、目录发布与 finalize，并保留原始数据和变换。不要为适配工具而改变科学问题。

## 示意图字段

- `size:[width,height]` 像素画布；`alt_text` 为图的描述。
- `nodes:[{id,label,box:[x,y,w,h],fill?,claims?}]`；label 用换行分行。ID 不得为 0/1 或使用预留的 edge- 前缀。
- `edges:[{from,to,label,kind,claims?}]`，kind 为 flow/association/causal/planned。association 无箭头，planned 为虚线，类型由证据及研究者判断。
- 输出 SVG、draw.io XML、PDF、PNG；节点和文字可编辑。预览的 PyMuPDF 转换器可能替换字体，必须查看实际结果。简单连线不会自动解决所有路由/文字冲突，自环需要专用路由。复杂拓扑使用专用编辑器/代码，保留同一节点和关系清单。

运行 `skills/_shared/examples/visual_research.py` 可获得完整且可运行的示例 spec。示例明显标为 illustrative，不能替换成真实结果标签。
