#!/usr/bin/env python3
"""style-mimic Phase 0 机械特征统计（style_stats.py）

用法: python style_stats.py <input.txt> <start_line> <end_line>   # 1-based, 含 start 不含 end
口径: 行区间 = Abstract 正文起, References 止; 剔除导航噪音/目录/图注/公式/孤立符号行
输出: JSON (stdout)。数值特征全部来自本脚本, 禁止凭印象填数（P1 可复现）。
"""
import sys, re, json, statistics

ABBRS = ["et al.", "e.g.", "i.e.", "Fig.", "Figs.", "vs.", "cf.", "approx.", "Eq.", "Sec.", "Sect.", "No."]

def clean_latex(s: str) -> str:
    s = s.replace("​", "")
    s = re.sub(r'\\displaystyle.*', ' ', s)
    s = re.sub(r'\\mathrm\{[^}]*\}', '', s)
    s = re.sub(r'\\text\{[^}]*\}', '', s)
    s = re.sub(r'\\tfrac\{[^}]*\}\{[^}]*\}', ' ', s)
    s = re.sub(r'[_^]\{[^}]*\}', '', s)
    s = re.sub(r'\\(geq|leq|approx|times|cdot|sim)\b', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s

def is_noise(s: str) -> bool:
    if len(s) < 4:
        return True
    if re.match(r'^\d+(\.\d+)*\s+[A-Z]', s):
        return True
    if s in ("Abstract", "References"):
        return True
    if re.match(r'^(Figure|Table)\s+\d+\s*:', s):
        return True
    if s in ('•', '-', '--', '−'):
        return True
    if re.match(r'^[A-Z][A-Za-z\- ]+:\s*$', s) and len(s.split()) <= 4:
        return True
    if re.match(r'^(License|arXiv|Email|Affiliation|Title|Description|Submit|Back to|Report|Why HTML|Download PDF)', s):
        return True
    return False

def words_of(s: str):
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", s)

def sentences(par: str):
    tmp = par
    for ab in ABBRS:
        tmp = tmp.replace(ab, ab.replace(".", "\x00"))
    out = []
    for s in re.split(r'(?<=[.!?])\s+', tmp):
        s = s.replace("\x00", ".")
        if len(words_of(s)) >= 4:
            out.append(s)
    return out

def main():
    path, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    lines = open(path, encoding="utf-8").read().splitlines()
    paras = [clean_latex(ln.strip()) for ln in lines[start-1:end-1]]
    paras = [p for p in paras if not is_noise(p) and len(words_of(p)) >= 8]

    all_sents = []
    para_sent_counts = []
    for p in paras:
        ss = sentences(p)
        para_sent_counts.append(len(ss))
        all_sents.extend(ss)

    full = " ".join(paras)
    n_words = len(words_of(full))
    slens = [len(words_of(s)) for s in all_sents]
    k_words = n_words / 1000.0

    def freq(pat, flags=re.IGNORECASE):
        return len(re.findall(pat, full, flags))

    hedging = {
        "suggest": freq(r"\bsuggest(s|ing|ed)?\b"),
        "indicate": freq(r"\bindicate(s|ing|d)?\b"),
        "show": freq(r"\bshow(s|ing|ed)?\b|\bshown\b"),
        "demonstrate": freq(r"\bdemonstrate(s|ing|d)?\b"),
        "prove": freq(r"\bprove(s|d)?\b|\bproven\b"),
        "establish": freq(r"\bestablish(es|ed|ing)?\b"),
        "reveal": freq(r"\breveal(s|ing|ed)?\b"),
    }
    connectives = {c: freq(r"\b" + c + r"\b") for c in
                   ["However", "Yet", "Nevertheless", "Moreover", "Furthermore",
                    "Additionally", "Instead", "Therefore", "Thus", "While"]}
    passive = freq(r"\b(is|are|was|were|be|been|being)\s+[a-z]+(ed|en)\b")
    nominal = freq(r"\b\w+(tion|sion|ment|ance|ence|ity|ness)\b")
    fig_refs = freq(r"\b(Fig\.|Figs\.|Figure|Table)\b")

    ai_tel = {
        "delve": freq(r"\bdelve(s|d)?\b"), "underscore": freq(r"\bunderscor(e|es|ing|ed)\b"),
        "intricate": freq(r"\bintricate(ly)?\b"), "tapestry": freq(r"\btapestry\b"),
        "pivotal": freq(r"\bpivotal\b"), "showcase": freq(r"\bshowcas(e|es|ing|ed)\b"),
        "foster": freq(r"\bfoster(s|ing|ed)?\b"), "leverage": freq(r"\bleverag(e|es|ing|ed)\b"),
        "realm": freq(r"\brealm\b"), "seamless": freq(r"\bseamless(ly)?\b"),
        "landscape": freq(r"\blandscape\b"),
        "paves_the_way": freq(r"paves? the way"), "opens_avenues": freq(r"opens? new avenues"),
        "sheds_light": freq(r"sheds? light on"), "bridges_gap": freq(r"bridg(e|es|ing) the gap"),
        "paramount": freq(r"\bparamount\b"),
        "novel": freq(r"\bnovel(ty)?\b"), "first_time": freq(r"for the first time"),
        "best_knowledge": freq(r"to the best of our knowledge"),
        "extensive": freq(r"\bextensive(ly)?\b"), "comprehensive": freq(r"\bcomprehensive(ly)?\b"),
        "numerous": freq(r"\bnumerous\b"), "various": freq(r"\bvarious\b"),
        "wide_range": freq(r"a wide range of"),
        "em_dash": full.count("—") + full.count(" – "),
        "worth_noting": freq(r"it is worth noting"), "in_order_to": freq(r"\bin order to\b"),
        "not_just_but": freq(r"not (only|just) .{1,40} but"),
    }
    first_person = freq(r"\b(we|our|us)\b")
    this_np_v = freq(r"\bThis\s+\w+\s+(suggests|indicates|shows|demonstrates|emphasises|emphasizes|underscores|reveals|implies|provides|introduces|leaves)\b")
    however_sent_initial = sum(1 for s in all_sents if re.match(r'^\s*However\b', s))
    however_total = connectives["However"]
    delta_form = freq(r"\bby (approximately |around |roughly )?\d") + freq(r"\bfrom \d+(\.\d+)?%? to \d+")
    absolute_form = freq(r"\b(achieving|achieves|reaching|reaches|obtaining|obtains|of) \d+(\.\d+)?%")
    british = freq(r"\b(utilis|organis|analys|emphasis|recognis|summaris|dynamis)\w*\b")
    american = freq(r"\b(utiliz|organiz|analyz|emphasiz|recogniz|summariz)\w*\b")

    q = statistics.quantiles(slens, n=4) if len(slens) >= 8 else [0, 0, 0]
    out = {
        "corpus": {
            "path": path, "line_range": [start, end],
            "words_clean": n_words, "sentences": len(all_sents),
            "paragraphs": len(paras),
        },
        "S1_sent_len": {
            "mean": round(statistics.mean(slens), 1),
            "sd": round(statistics.pstdev(slens), 1),
            "p25": round(q[0], 1), "p50": round(q[1], 1), "p75": round(q[2], 1),
        },
        "S2_hedging_spectrum": hedging,
        "S3_connectives": {c: {"n": n, "per_k": round(n / k_words, 2)} for c, n in connectives.items()},
        "S4_passive": {"n": passive, "ratio_vs_sents": round(passive / max(len(all_sents), 1), 3)},
        "S5_nominalization": {"n": nominal, "per_k": round(nominal / k_words, 1)},
        "S6_fig_table_refs": {"n": fig_refs, "per_k": round(fig_refs / k_words, 2)},
        "S7_ai_tel": ai_tel,
        "S8_first_person": {"n": first_person, "per_k": round(first_person / k_words, 1)},
        "S9_number_style": {"delta_form": delta_form, "absolute_form": absolute_form},
        "S10_para_sents": {
            "mean": round(statistics.mean(para_sent_counts), 1),
            "sd": round(statistics.pstdev(para_sent_counts), 1),
            "max": max(para_sent_counts), "n_paras": len(para_sent_counts),
        },
        "S11_pivot": {"however_sent_initial": however_sent_initial, "however_total": however_total,
                      "initial_ratio": round(however_sent_initial / max(however_total, 1), 2)},
        "S12_this_np_v": {"n": this_np_v, "examples_pattern": "This + NP + reporting-verb"},
        "S13_spelling": {"british_ise": british, "american_ize": american},
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
