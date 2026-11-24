#!/usr/bin/env python3
"""querygen — expand a research question into a search-query matrix.

  python3 querygen.py --topic "solid-state battery" --facets "sulfide electrolyte,lithium metal anode,dendrite" \
      [--zh "固态电池"] [--extra-lang ja:全固体電池] [--tier deep] [--out queries.jsonl]

Matrix = (topic + each facet) × lenses (history, failure, first-principles, frontier, data, practitioner,
contrarian, patents/standards) × eras × languages. Output is JSONL ready to plan rounds; it is a plan, not a
log — record each query you actually run with `drctl.py add query`.
"""
from __future__ import annotations

import argparse
import json
import random

LENSES = {
    "history": ["history of {t}", "{t} origins invention timeline", "{t} review {era}"],
    "failure-postmortem": ["why {t} failed", "{t} postmortem", "{t} bankruptcy OR abandoned OR recall",
                           "{t} negative results", "{t} retracted"],
    "first-principles": ["{t} theoretical limit", "{t} cost floor analysis", "{t} thermodynamic OR physical limit",
                         "{t} scaling law learning curve"],
    "academic": ["{t} review article", "{t} meta-analysis", "{t} survey arxiv"],
    "primary-data": ["{t} dataset statistics", "{t} production volume capacity data", "{t} 10-K OR prospectus"],
    "practitioner-blog": ["{t} engineering blog lessons learned", "{t} what we learned building",
                          "{t} hacker news discussion"],
    "patent-standard": ["{t} patent landscape", "{t} standard IEC OR ISO OR JEDEC"],
    "report-news": ["{t} market report 2026", "{t} latest news 2026"],
    "contrarian": ["{t} is overhyped", "{t} skeptic critique", "case against {t}"],
}
ZH = {
    "history": ["{t} 发展史", "{t} 技术演进"],
    "failure-postmortem": ["{t} 失败 原因", "{t} 项目 下马 OR 暴雷 OR 破产", "{t} 复盘"],
    "first-principles": ["{t} 理论极限", "{t} 成本 拆解"],
    "academic": ["{t} 综述"],
    "primary-data": ["{t} 产能 出货量 数据", "{t} 招股书"],
    "practitioner-blog": ["{t} 工程师 经验 踩坑"],
    "report-news": ["{t} 行业报告 2026"],
    "contrarian": ["{t} 泡沫 质疑"],
}
ERAS = {"pre1950": "1900..1949", "1950-1974": "1950..1974", "1975-1999": "1975..1999",
        "2000-2014": "2000..2014", "2015-now": "2015..2026"}
CAP = {"quick": 60, "deep": 220, "max": 600}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--facets", default="")
    ap.add_argument("--zh", default="")
    ap.add_argument("--extra-lang", default="", help="lang:term, e.g. ja:全固体電池")
    ap.add_argument("--tier", default="deep", choices=list(CAP))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    terms = [a.topic] + [f"{a.topic} {x.strip()}" for x in a.facets.split(",") if x.strip()]
    rows = []
    for t in terms:
        for lens, pats in LENSES.items():
            for p in pats:
                if "{era}" in p:
                    for era, rng in ERAS.items():
                        rows.append({"text": p.format(t=t, era=rng), "lens": lens, "era": era, "lang": "en"})
                else:
                    rows.append({"text": p.format(t=t), "lens": lens, "era": "any", "lang": "en"})
    if a.zh:
        zterms = [a.zh] + [f"{a.zh} {x.strip()}" for x in a.facets.split(",") if x.strip()]
        for t in zterms:
            for lens, pats in ZH.items():
                for p in pats:
                    rows.append({"text": p.format(t=t), "lens": lens, "era": "any", "lang": "zh"})
    if a.extra_lang:
        lang, term = a.extra_lang.split(":", 1)
        for lens in ("history", "failure-postmortem", "academic"):
            rows.append({"text": term, "lens": lens, "era": "any", "lang": lang})
    # keep every failure/contrarian query, sample the rest down to the tier cap
    must = [r for r in rows if r["lens"] in ("failure-postmortem", "contrarian", "first-principles")]
    rest = [r for r in rows if r not in must]
    random.Random(7).shuffle(rest)
    rows = must + rest[: max(0, CAP[a.tier] - len(must))]
    for i, r in enumerate(rows):
        r["round"] = i // 40 + 1
    out = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out + "\n")
        print(f"{len(rows)} planned queries -> {a.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
