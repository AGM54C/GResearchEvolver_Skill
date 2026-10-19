import json, re, glob, os
from collections import Counter

RAW = os.path.join(os.path.dirname(__file__), "..", "..", "..", "literature", "inbox", "raw")

def norm_aid(s):
    return re.sub(r"v\d+$", "", s.strip())

entries = []
for f in glob.glob(os.path.join(RAW, "arxiv-*.xml")):
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in ET.parse(f).getroot().findall("a:entry", ns):
        id_el = e.find("a:id", ns).text
        m = re.search(r"abs/(.+)$", id_el)
        raw_key = m.group(1)
        entries.append({"src": "arxiv", "raw_key": raw_key, "norm": norm_aid(raw_key),
                        "title": re.sub(r"\s+", " ", e.find("a:title", ns).text.strip())})

for f in glob.glob(os.path.join(RAW, "oa-*.json")):
    d = json.load(open(f, encoding="utf-8"))
    for r in d.get("results", []):
        doi = (r.get("ids") or {}).get("doi", "") or ""
        m = re.search(r"arxiv\.(\S+)$", doi)
        if m:
            entries.append({"src": "oa", "raw_key": "doi:" + doi, "norm": norm_aid(m.group(1)),
                            "title": re.sub(r"\s+", " ", (r.get("display_name") or "")[:80])})

for f in glob.glob(os.path.join(RAW, "cr-*.json")):
    d = json.load(open(f, encoding="utf-8"))
    items = d.get("message", {}).get("items", []) if isinstance(d, dict) and "message" in d else (d.get("items") or [])
    for r in items:
        doi = r.get("DOI", "") or ""
        m = re.search(r"arxiv\.(\S+)$", doi, re.I)
        if m:
            title = (r.get("title") or [""])
            title = title[0] if title else ""
            entries.append({"src": "cr", "raw_key": "doi:" + doi, "norm": norm_aid(m.group(1)),
                            "title": re.sub(r"\s+", " ", title[:80])})

print(f"total_entries_with_arxiv_identity: {len(entries)}")
print(f"  by_source: {dict(Counter(e['src'] for e in entries))}")

strat_a_keys = [e["raw_key"] for e in entries]
dup_a = {k: c for k, c in Counter(strat_a_keys).items() if c > 1}

true_groups = Counter(e["norm"] for e in entries)
overlap = {k: c for k, c in true_groups.items() if c > 1}

a_ids = set(strat_a_keys)
b_ids = set(e["norm"] for e in entries)
cross_src_overlap = 0
for k, c in overlap.items():
    srcs = {e["src"] for e in entries if e["norm"] == k}
    if len(srcs) > 1:
        cross_src_overlap += 1

print(f"STRATEGY_A(no_norm): raw_keys={len(a_ids)}, dup_same_rawkey={len(dup_a)}")
print(f"  true_unique_papers={len(true_groups)}, papers_in_multiple_entries={len(overlap)}")
print(f"  cross_source_overlaps(arxiv_vX vs doi_extracted)={cross_src_overlap}")
print(f"  duplicate_identities_under_A={len(entries) - len(a_ids) if False else len(entries) - len(true_groups) + (len(entries)-len(a_ids))*0}")
a_count = sum(c - 1 for c in true_groups.values() if c > 1)
print(f"  redundant_entries_A(need_merge)={a_count}")
print(f"STRATEGY_B(norm): unique_keys={len(b_ids)}, redundant_entries_B={max(0, len(entries) - len(b_ids)) if len(b_ids) < len(true_groups) else 0}")
b_count = sum(c - 1 for c in Counter(e["norm"] for e in entries).values() if c > 1)
print(f"  merged_by_norm(exact_duplicates)={b_count}")

print("\noverlap_samples:")
for k, c in sorted(overlap.items(), key=lambda x: -x[1])[:8]:
    srcs = Counter(e["src"] for e in entries if e["norm"] == k)
    ex = [e for e in entries if e["norm"] == k][0]
    print(f"  {k} x{c} srcs={dict(srcs)} title={ex['title'][:60]}")
