#!/usr/bin/env python3
"""drctl — research ledger, phase gates and report skeleton for jvc-deepresearch.

Standard library only. One append-only ledger per run: <run-dir>/ledger.jsonl.

Commands
  init     --run-dir D --question Q --decision X [--tier quick|deep|max]
  add      --run-dir D TYPE (--json '{...}' | --file records.jsonl)
  novelty  --run-dir D --round N
  status   --run-dir D
  gate     --run-dir D [--phase search|fp|debate|exp|loop|report|all]
  waive    --run-dir D --rule R --reason TEXT --residual-risk TEXT
  report   --run-dir D            (writes report.skeleton.md)
  export   --run-dir D            (writes sources.csv, hypotheses.csv)

Exit codes for gate: 0 ready, 10 partial (only waived failures), 20 blocked, 1 usage/data error.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

TIERS = {
    "quick": dict(queries=40, sources=25, failures=3, source_classes=4, eras=3, debate_rounds=2,
                  constraints=3, baserates=1, loop_iters=3, novelty_rounds=1),
    "deep": dict(queries=150, sources=70, failures=10, source_classes=6, eras=4, debate_rounds=3,
                 constraints=5, baserates=3, loop_iters=8, novelty_rounds=2),
    "max": dict(queries=400, sources=180, failures=25, source_classes=7, eras=5, debate_rounds=4,
                constraints=8, baserates=5, loop_iters=15, novelty_rounds=2),
}
ERAS = ["pre1950", "1950-1974", "1975-1999", "2000-2014", "2015-now"]
SOURCE_CLASSES = ["academic", "failure-postmortem", "practitioner-blog", "primary-data", "patent-standard",
                  "report-news", "book-history", "code-dataset", "expert", "user-material"]
ROLES = ["P", "S", "H", "E"]
HYP_STATES = ["open", "supported", "weakened", "refuted", "inconclusive"]

PREFIX = {"scope": "SC", "question": "QN", "query": "Q", "source": "S", "claim": "C", "constraint": "K",
          "baserate": "B", "hypothesis": "H", "debate": "D", "crux": "X", "experiment": "E", "result": "R",
          "loop": "L", "waiver": "W", "note": "N"}

REQUIRED = {
    "scope": ["question", "decision"],
    "question": ["text", "priority", "would_change_answer"],
    "query": ["text", "round", "source_class_target", "result_count"],
    "source": ["title", "url_or_path", "source_class", "era", "date", "independence_key"],
    "claim": ["text", "source_ids", "kind"],
    "constraint": ["text", "value", "unit", "basis"],
    "baserate": ["reference_class", "rate", "n", "source_ids"],
    "hypothesis": ["text", "prediction", "falsifier", "metric"],
    "debate": ["round", "role", "stage", "text", "cites", "credences"],
    "crux": ["text", "hypothesis_ids", "cheapest_test"],
    "experiment": ["hypothesis_id", "method", "metric", "threshold", "prediction", "decision_rule", "budget"],
    "result": ["experiment_id", "observed", "passed", "effect", "confidence", "hypothesis_state"],
    "loop": ["iteration", "target", "change", "score_before", "score_after", "kept", "voi", "cost"],
    "waiver": ["rule", "reason", "residual_risk"],
    "note": ["text"],
}
ENUMS = {
    ("question", "priority"): ["high", "medium", "low"],
    ("query", "source_class_target"): SOURCE_CLASSES + ["mixed"],
    ("source", "source_class"): SOURCE_CLASSES,
    ("source", "era"): ERAS,
    ("claim", "kind"): ["fact", "estimate", "self-report", "opinion", "inference"],
    ("debate", "role"): ROLES,
    ("debate", "stage"): ["opening", "cross-exam", "rebuttal", "closing"],
    ("result", "hypothesis_state"): HYP_STATES,
}


class DataError(Exception):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def ledger_path(run_dir: str) -> str:
    return os.path.join(run_dir, "ledger.jsonl")


def load(run_dir: str) -> list[dict]:
    p = ledger_path(run_dir)
    if not os.path.exists(p):
        raise DataError(f"no ledger at {p}; run init first")
    out, prev = [], ""
    with open(p, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("prev") != prev or fingerprint(r) != r.get("fp"):
                raise DataError(f"chain broken at line {n} ({r.get('id')}); ledger was edited by hand")
            prev = r["fp"]
            out.append(r)
    return out


def fingerprint(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "fp"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def effective(recs: list[dict]) -> list[dict]:
    """Drop records superseded by a later record."""
    dead = {r["supersedes"] for r in recs if r.get("supersedes")}
    return [r for r in recs if r["id"] not in dead]


def by_type(recs, t):
    return [r for r in effective(recs) if r["type"] == t]


def append(run_dir: str, rtype: str, payload: dict) -> dict:
    recs = load(run_dir)
    ids = {r["id"] for r in recs}
    validate(rtype, payload, ids, recs)
    n = sum(1 for r in recs if r["type"] == rtype) + 1
    rec = {"id": f"{PREFIX[rtype]}{n}", "type": rtype, "ts": now(), **payload,
           "prev": recs[-1]["fp"] if recs else ""}
    rec["fp"] = fingerprint(rec)
    with open(ledger_path(run_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def validate(rtype, p, ids, recs):
    if rtype not in REQUIRED:
        raise DataError(f"unknown type {rtype}; one of {sorted(REQUIRED)}")
    miss = [k for k in REQUIRED[rtype] if k not in p or p[k] in ("", None)]
    if miss:
        raise DataError(f"{rtype} missing fields: {miss}")
    for (t, k), allowed in ENUMS.items():
        if t == rtype and p.get(k) not in allowed:
            raise DataError(f"{rtype}.{k}={p.get(k)!r} not in {allowed}")
    if p.get("supersedes") and p["supersedes"] not in ids:
        raise DataError(f"supersedes unknown id {p['supersedes']}")
    refs = []
    for k in ("source_ids", "cites", "hypothesis_ids"):
        if k in p:
            if not isinstance(p[k], list):
                raise DataError(f"{rtype}.{k} must be a list")
            refs += p[k]
    for k in ("hypothesis_id", "experiment_id", "question_id"):
        if p.get(k):
            refs.append(p[k])
    bad = [x for x in refs if x not in ids]
    if bad:
        raise DataError(f"{rtype} references unknown ids {bad}")
    if rtype == "debate":
        if not p["cites"]:
            raise DataError("debate turn must cite at least one ledger id (no uncited assertions)")
        if not isinstance(p["credences"], dict):
            raise DataError("debate.credences must be {hypothesis_id: 0..1}")
        for h, v in p["credences"].items():
            if h not in ids or not (0 <= float(v) <= 1):
                raise DataError(f"bad credence {h}={v}")
    if rtype == "result":
        exp = next((r for r in recs if r["id"] == p["experiment_id"]), None)
        if not exp or exp["type"] != "experiment":
            raise DataError("result.experiment_id must point to an experiment (pre-registered first)")
    if rtype == "claim" and p["kind"] in ("fact", "estimate") and not p["source_ids"]:
        raise DataError("fact/estimate claims need at least one source id")


# ───────────────────────── metrics & gates ─────────────────────────

def metrics(recs):
    cfg = by_type(recs, "scope")
    tier = cfg[0].get("tier", "deep") if cfg else "deep"
    T = TIERS[tier]
    q, s, c = by_type(recs, "query"), by_type(recs, "source"), by_type(recs, "claim")
    indep = {x["independence_key"] for x in s}
    m = dict(tier=tier, T=T, queries=len(q), sources=len(s), independent_sources=len(indep), claims=len(c),
             failures=sum(1 for x in s if x.get("failure")),
             classes=Counter(x["source_class"] for x in s), eras=Counter(x["era"] for x in s),
             rounds=sorted({int(x["round"]) for x in q}),
             zero_result_queries=sum(1 for x in q if int(x["result_count"]) == 0))
    m["novelty"] = {r: novelty_rate(recs, r) for r in m["rounds"]}
    return m


def novelty_rate(recs, rnd):
    """Share of sources+claims first introduced in round rnd vs all items added that round.
    A source is 'new' when its independence_key was never seen in an earlier round."""
    s = by_type(recs, "source")
    seen, new, total = set(), 0, 0
    for x in s:
        r = int(x.get("round", 0))
        if r < rnd:
            seen.add(x["independence_key"])
    for x in s:
        if int(x.get("round", 0)) == rnd:
            total += 1
            if x["independence_key"] not in seen:
                new += 1
                seen.add(x["independence_key"])
    q_round = [x for x in by_type(recs, "query") if int(x["round"]) == rnd]
    denom = max(total, 1)
    return dict(round=rnd, queries=len(q_round), sources=total, new_sources=new,
                rate=round(new / denom, 3) if total else 0.0)


def gate(recs, phase):
    m = metrics(recs)
    T = m["T"]
    waived = {w["rule"] for w in by_type(recs, "waiver")}
    fails = []

    def need(rule, ok, msg):
        if not ok:
            fails.append((rule, msg))

    if phase in ("search", "all"):
        need("search.queries", m["queries"] >= T["queries"], f"queries {m['queries']} < {T['queries']}")
        need("search.sources", m["independent_sources"] >= T["sources"],
             f"independent sources {m['independent_sources']} < {T['sources']}")
        need("search.failures", m["failures"] >= T["failures"], f"failure cases {m['failures']} < {T['failures']}")
        need("search.classes", len(m["classes"]) >= T["source_classes"],
             f"source classes {len(m['classes'])} < {T['source_classes']} ({dict(m['classes'])})")
        need("search.eras", len(m["eras"]) >= T["eras"], f"era buckets {len(m['eras'])} < {T['eras']} ({dict(m['eras'])})")
        last = [m["novelty"][r]["rate"] for r in m["rounds"][-T["novelty_rounds"]:]]
        need("search.saturation", len(last) >= T["novelty_rounds"] and all(x < 0.10 for x in last),
             f"not saturated: last-round novelty {last} (need {T['novelty_rounds']} rounds < 0.10)")
        open_hi = [x["id"] for x in by_type(recs, "question") if x["priority"] == "high" and
                   x.get("state", "open") == "open"]
        need("search.questions", not open_hi, f"high-priority questions still open: {open_hi} "
             "(close as answered or evidence-gap via a superseding question record)")
    if phase in ("fp", "all"):
        need("fp.constraints", len(by_type(recs, "constraint")) >= T["constraints"],
             f"constraints {len(by_type(recs, 'constraint'))} < {T['constraints']}")
        need("fp.baserates", len(by_type(recs, "baserate")) >= T["baserates"],
             f"base rates {len(by_type(recs, 'baserate'))} < {T['baserates']}")
        hyps = by_type(recs, "hypothesis")
        need("fp.hypotheses", len(hyps) >= 3, f"hypotheses {len(hyps)} < 3")
        need("fp.contrarian", any(h.get("contrarian") for h in hyps), "no contrarian hypothesis (contrarian: true)")
    if phase in ("debate", "all"):
        d = by_type(recs, "debate")
        rounds = defaultdict(set)
        for x in d:
            rounds[int(x["round"])].add(x["role"])
        full = [r for r, roles in rounds.items() if roles >= set(ROLES)]
        need("debate.rounds", len(full) >= T["debate_rounds"],
             f"complete 4-role rounds {len(full)} < {T['debate_rounds']}")
        need("debate.cruxes", len(by_type(recs, "crux")) >= 1, "no crux recorded")
        if full:
            r1 = min(full)
            spread = []
            for h in by_type(recs, "hypothesis"):
                vals = [float(x["credences"].get(h["id"])) for x in d if int(x["round"]) == r1
                        and h["id"] in x["credences"]]
                if len(vals) >= 2:
                    spread.append(statistics.pstdev(vals))
            echo = spread and max(spread) < 0.10
            forced = any(x.get("anti_echo_rewrite") for x in d)
            need("debate.anti_echo", not echo or forced,
                 "round-1 credence spread < 0.10 on every hypothesis: same-model echo chamber; "
                 "force S/H to rewrite openings from opposing premises (anti_echo_rewrite: true)")
    if phase in ("exp", "all"):
        hyps = [h for h in by_type(recs, "hypothesis") if not h.get("dropped")]
        exps, res = by_type(recs, "experiment"), by_type(recs, "result")
        exp_by_h = defaultdict(list)
        for e in exps:
            exp_by_h[e["hypothesis_id"]].append(e)
        res_by_e = {r["experiment_id"]: r for r in res}
        for h in hyps:
            need(f"exp.{h['id']}.registered", bool(exp_by_h[h["id"]]), f"{h['id']} has no pre-registered experiment")
            for e in exp_by_h[h["id"]]:
                r = res_by_e.get(e["id"])
                need(f"exp.{e['id']}.result", r is not None, f"{e['id']} has no result")
                if r:
                    need(f"exp.{e['id']}.order", r["ts"] >= e["ts"], f"{e['id']} result predates registration")
        need("exp.ablation", any(e.get("ablation") for e in exps),
             "no ablation experiment (mark ablation: true on the ablate.py run)")
    if phase in ("loop", "all"):
        loops = by_type(recs, "loop")
        need("loop.iters", len(loops) >= T["loop_iters"], f"loop iterations {len(loops)} < {T['loop_iters']}")
        stop = [x for x in loops if x.get("stop_reason")]
        need("loop.stop", bool(stop) and stop[-1]["stop_reason"] in ("plateau", "voi", "budget", "refuted"),
             "loop has no stop_reason in {plateau, voi, budget, refuted}")
        ev = {x.get("evaluator") for x in loops if x.get("evaluator")}
        need("loop.fixed_evaluator", len(ev) <= 1, f"evaluator changed mid-loop: {ev}")
    if phase in ("report", "all"):
        rp = os.path.join(RUN_DIR, "report.md")
        ok = os.path.exists(rp)
        need("report.exists", ok, "report.md missing")
        if ok:
            txt = open(rp, encoding="utf-8").read()
            import re
            cited = set(re.findall(r"\b(?:S|C|K|B|H|E|R|L|X)\d+\b", txt))
            ids = {r["id"] for r in recs}
            ghost = sorted(cited - ids)
            need("report.ghost_ids", not ghost, f"report cites ids not in ledger: {ghost[:15]}")
            need("report.cites", len(cited & ids) >= 10, "report cites fewer than 10 ledger ids")
            state = "研究状态：" in txt
            need("report.status_label", state, "report lacks a 研究状态：ready/partial/blocked line")

    hard = [f for f in fails if f[0] not in waived]
    soft = [f for f in fails if f[0] in waived]
    return m, hard, soft


RUN_DIR = "."


def cmd_status(recs):
    m = metrics(recs)
    print(f"tier={m['tier']} queries={m['queries']} sources={m['sources']} (independent {m['independent_sources']}) "
          f"claims={m['claims']} failures={m['failures']} zero-result queries={m['zero_result_queries']}")
    print("eras:", dict(m["eras"]))
    print("classes:", dict(m["classes"]))
    for r in m["rounds"]:
        print("round", r, m["novelty"][r])
    for t in ("constraint", "baserate", "hypothesis", "debate", "crux", "experiment", "result", "loop", "waiver"):
        print(f"{t}: {len(by_type(recs, t))}")
    states = {}
    for r in by_type(recs, "result"):
        e = next(x for x in recs if x["id"] == r["experiment_id"])
        states[e["hypothesis_id"]] = r["hypothesis_state"]
    for h in by_type(recs, "hypothesis"):
        print(f"  {h['id']} [{states.get(h['id'], 'open')}] {h['text'][:80]}")


def credence_table(recs):
    d = by_type(recs, "debate")
    if not d:
        return "（无辩论记录）"
    last = max(int(x["round"]) for x in d)
    hyps = by_type(recs, "hypothesis")
    rows = ["| 假设 | " + " | ".join(ROLES) + " | 均值 | 分歧（σ） |", "|---|" + "---|" * (len(ROLES) + 2)]
    for h in hyps:
        vals = []
        cells = []
        for role in ROLES:
            t = [x for x in d if int(x["round"]) == last and x["role"] == role and h["id"] in x["credences"]]
            v = float(t[-1]["credences"][h["id"]]) if t else None
            cells.append(f"{v:.2f}" if v is not None else "—")
            if v is not None:
                vals.append(v)
        mu = f"{statistics.mean(vals):.2f}" if vals else "—"
        sd = f"{statistics.pstdev(vals):.2f}" if len(vals) > 1 else "—"
        rows.append(f"| {h['id']} {h['text'][:40]} | " + " | ".join(cells) + f" | {mu} | {sd} |")
    return "\n".join(rows)


def cmd_report(recs, run_dir):
    m = metrics(recs)
    sc = by_type(recs, "scope")[0]
    res = by_type(recs, "result")
    exps = {e["id"]: e for e in by_type(recs, "experiment")}
    score = ["| 假设 | 实验 | 方法 | 预测 | 实测 | 通过 | 效应量 | 状态 |", "|---|---|---|---|---|---|---|---|"]
    for r in res:
        e = exps[r["experiment_id"]]
        score.append(f"| {e['hypothesis_id']} | {e['id']}/{r['id']} | {e['method'][:30]} | {e['prediction']} | "
                     f"{r['observed']} | {'是' if r['passed'] else '否'} | {r['effect']} | {r['hypothesis_state']} |")
    loops = by_type(recs, "loop")
    lt = ["| 轮 | 目标 | 改动 | 前 | 后 | 保留 | VOI | 成本 |", "|---|---|---|---|---|---|---|---|"]
    for x in loops:
        lt.append(f"| {x['iteration']} | {x['target'][:24]} | {x['change'][:36]} | {x['score_before']} | "
                  f"{x['score_after']} | {'keep' if x['kept'] else 'discard'} | {x['voi']} | {x['cost']} |")
    stop = next((x["stop_reason"] for x in reversed(loops) if x.get("stop_reason")), "（未停机）")
    cruxes = "\n".join(f"- {x['id']}：{x['text']}（判决实验：{x['cheapest_test']}）" for x in by_type(recs, "crux"))
    fails = [x for x in by_type(recs, "source") if x.get("failure")]
    ft = "\n".join(f"- {x['id']} {x['title']}（{x['date']}，{x['era']}）" for x in fails[:30])
    _, hard, soft = gate(recs, "all")
    status = "ready" if not hard and not soft else ("partial" if not hard else "blocked")
    txt = f"""# {sc['question']}

研究状态：{status}  ｜ 档位：{m['tier']} ｜ 生成：{dt.date.today().isoformat()}

> 服务的决策：{sc['decision']}

## 一页结论
<!-- ≤5 条；每条：判断 + 可信度(0–1) + 撑住它的关键 ID（S#/K#/R#）+ 最可能错在哪 -->

## 1. 研究问题与范围

## 2. 第一性原理：不变量与"必须为真"
<!-- 引用 K#、B# -->

## 3. 百年史与失败教训（{m['failures']} 个失败案例）
{ft}

## 4. 假设记分卡（预注册实验与消融）
{chr(10).join(score)}

## 5. 四人辩论：终轮可信度与未决分歧
{credence_table(recs)}

{cruxes}

## 6. 自动研究循环轨迹（停机理由：{stop}）
{chr(10).join(lt)}

## 7. 证据缺口与下一步最值钱的三件事

## 附录 A 检索统计
- 查询 {m['queries']} 条（零结果 {m['zero_result_queries']}），来源 {m['sources']} 个（独立 {m['independent_sources']}），论断 {m['claims']} 条
- 年代分布：{dict(m['eras'])}
- 来源类型：{dict(m['classes'])}
- 各轮新增率：{[m['novelty'][r]['rate'] for r in m['rounds']]}

## 附录 B 未过门槛
{chr(10).join(f'- [{r}] {msg}' for r, msg in hard) or '- 无'}
{chr(10).join(f'- [豁免 {r}] {msg}' for r, msg in soft)}

## 附录 C 来源表
见 sources.csv（`drctl.py export`）。
"""
    out = os.path.join(run_dir, "report.skeleton.md")
    open(out, "w", encoding="utf-8").write(txt)
    print(out)


def cmd_export(recs, run_dir):
    s = by_type(recs, "source")
    with open(os.path.join(run_dir, "sources.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "url_or_path", "source_class", "era", "date", "failure", "stance", "independence_key"])
        for x in s:
            w.writerow([x["id"], x["title"], x["url_or_path"], x["source_class"], x["era"], x["date"],
                        x.get("failure", False), x.get("stance", ""), x["independence_key"]])
    with open(os.path.join(run_dir, "hypotheses.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "text", "prediction", "falsifier", "metric", "contrarian"])
        for h in by_type(recs, "hypothesis"):
            w.writerow([h["id"], h["text"], h["prediction"], h["falsifier"], h["metric"], h.get("contrarian", False)])
    print("wrote sources.csv, hypotheses.csv")


def main(argv=None):
    global RUN_DIR
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--run-dir", required=True); p.add_argument("--question", required=True)
    p.add_argument("--decision", required=True); p.add_argument("--tier", default="deep", choices=list(TIERS))
    p = sub.add_parser("add"); p.add_argument("--run-dir", required=True); p.add_argument("type", choices=list(REQUIRED))
    g = p.add_mutually_exclusive_group(required=True); g.add_argument("--json"); g.add_argument("--file")
    p = sub.add_parser("novelty"); p.add_argument("--run-dir", required=True); p.add_argument("--round", type=int, required=True)
    for name in ("status", "report", "export"):
        p = sub.add_parser(name); p.add_argument("--run-dir", required=True)
    p = sub.add_parser("gate"); p.add_argument("--run-dir", required=True)
    p.add_argument("--phase", default="all", choices=["search", "fp", "debate", "exp", "loop", "report", "all"])
    p = sub.add_parser("waive"); p.add_argument("--run-dir", required=True); p.add_argument("--rule", required=True)
    p.add_argument("--reason", required=True); p.add_argument("--residual-risk", required=True)
    a = ap.parse_args(argv)
    RUN_DIR = a.run_dir
    try:
        if a.cmd == "init":
            os.makedirs(os.path.join(a.run_dir, "experiments"), exist_ok=True)
            if os.path.exists(ledger_path(a.run_dir)):
                raise DataError("ledger exists; resume instead of re-init")
            open(ledger_path(a.run_dir), "w").close()
            r = append(a.run_dir, "scope", {"question": a.question, "decision": a.decision, "tier": a.tier})
            print(json.dumps({"ok": True, "id": r["id"], "tier": a.tier, "floors": TIERS[a.tier]}, ensure_ascii=False))
        elif a.cmd == "add":
            items = [json.loads(a.json)] if a.json else [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
            ids = [append(a.run_dir, a.type, it)["id"] for it in items]
            print(json.dumps({"ok": True, "ids": ids}))
        elif a.cmd == "novelty":
            print(json.dumps(novelty_rate(load(a.run_dir), a.round)))
        elif a.cmd == "status":
            cmd_status(load(a.run_dir))
        elif a.cmd == "gate":
            m, hard, soft = gate(load(a.run_dir), a.phase)
            for r, msg in hard:
                print(f"FAIL  [{r}] {msg}")
            for r, msg in soft:
                print(f"WAIVED [{r}] {msg}")
            code = 20 if hard else (10 if soft else 0)
            print({0: "ready", 10: "partial", 20: "blocked"}[code], f"(phase={a.phase})")
            return code
        elif a.cmd == "waive":
            append(a.run_dir, "waiver", {"rule": a.rule, "reason": a.reason, "residual_risk": a.residual_risk})
            print("waiver recorded; affected gate becomes partial, never ready")
        elif a.cmd == "report":
            cmd_report(load(a.run_dir), a.run_dir)
        elif a.cmd == "export":
            cmd_export(load(a.run_dir), a.run_dir)
    except (DataError, json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
