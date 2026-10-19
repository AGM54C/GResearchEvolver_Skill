# 归档 v2

使用 `research.py --store PATH archive RUN`。归档前 worker 必须停止。保存 manifest/state/events、当前 artifacts 的原始字节，以及历史 checkpoint 引用的 CAS objects；.done 为 archive.json 的规范 JSON 哈希。相同科研状态重复归档不产生新版本。

使用 `verify` 验证源 Store 全事件链及对象；`verify-archive PATH` 验证可移植档。原字节哈希不做 CRLF 规范化；只有文本派生物另记哈希。单 run 的 events 是全局事件链片段，不宣称独立闭合链。

旧 research-instance/archives 保持不变，其已知缺失见仓库 docs/historical-errata.md。历史不完整不能通过补文件/改哈希冒充当时完整归档。
