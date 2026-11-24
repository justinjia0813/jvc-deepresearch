#!/usr/bin/env python3
"""End-to-end smoke test: builds a synthetic quick-tier run and checks every gate fails then passes.
Run from repo root: python3 evals/smoke_test.py"""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "skills", "jvc-deepresearch", "scripts")
D = tempfile.mkdtemp(prefix="dr-smoke-")


def run(*args, ok=(0,)):
    p = subprocess.run([sys.executable, os.path.join(S, "drctl.py"), *args, "--run-dir", D] if args[0] != "init" else
                       [sys.executable, os.path.join(S, "drctl.py"), *args], capture_output=True, text=True)
    if p.returncode not in ok:
        print(p.stdout, p.stderr); raise SystemExit(f"unexpected exit {p.returncode} for {args[:2]}")
    return p


def add(t, **kw):
    return json.loads(run("add", t, "--json", json.dumps(kw, ensure_ascii=False)).stdout)["ids"][0]


run("init", "--run-dir", D, "--question", "示例问题", "--decision", "示例决策", "--tier", "quick")
assert run("gate", "--phase", "search", ok=(20,)).returncode == 20
qn = add("question", text="子问题", priority="high", would_change_answer="x")
eras = ["pre1950", "1950-1974", "1975-1999", "2000-2014", "2015-now"]
classes = ["academic", "failure-postmortem", "practitioner-blog", "primary-data", "report-news"]
for r in (1, 2):
    for i in range(20):
        add("query", text=f"q{r}-{i}", round=r, source_class_target="mixed", result_count=0 if i == 0 else 5)
sids = []
for i in range(26):
    sids.append(add("source", title=f"s{i}", url_or_path=f"https://example.org/{i}", source_class=classes[i % 5],
                    era=eras[i % 5], date="2020-01-01", independence_key=f"k{i}", round=1, failure=i < 3))
add("source", title="dup", url_or_path="https://example.org/dup", source_class="report-news", era="2015-now",
    date="2026-01-01", independence_key="k1", round=2)
add("question", text="子问题", priority="high", would_change_answer="x", state="answered", supersedes=qn)
for i in range(3):
    add("claim", text=f"c{i}", source_ids=[sids[i]], kind="fact")
assert run("gate", "--phase", "search").returncode == 0, "search gate should pass"
# tamper detection
lp = os.path.join(D, "ledger.jsonl"); raw = open(lp).read()
open(lp, "w").write(raw.replace('"s5"', '"s5-edited"'))
assert run("status", ok=(1,)).returncode == 1, "tamper not detected"
open(lp, "w").write(raw)
for i in range(3):
    add("constraint", text=f"k{i}", value=1, unit="u", basis="derivation")
add("baserate", reference_class="rc", rate="30%", n=40, source_ids=[sids[0]])
hs = [add("hypothesis", text=f"h{i}", prediction="p", falsifier="f", metric="m", contrarian=(i == 2)) for i in range(3)]
assert run("gate", "--phase", "fp").returncode == 0
# uncited debate turn must be rejected
assert run("add", "debate", "--json", json.dumps({"round": 1, "role": "P", "stage": "opening", "text": "t", "cites": [],
           "credences": {hs[0]: .5}}), ok=(1,)).returncode == 1
import random
rnd = random.Random(1)
for r in (1, 2):
    for role in "PSHE":
        add("debate", round=r, role=role, stage="opening" if r == 1 else "rebuttal", text="t", cites=[sids[0]],
            credences={h: round(rnd.random(), 2) for h in hs})
add("crux", text="x", hypothesis_ids=hs[:2], cheapest_test="backtest")
assert run("gate", "--phase", "debate").returncode == 0
assert run("gate", "--phase", "exp", ok=(20,)).returncode == 20
for i, h in enumerate(hs):
    e = add("experiment", hypothesis_id=h, method="backtest", metric="m", threshold="t", prediction="p",
            decision_rule="r", budget="5m", ablation=(i == 0))
    add("result", experiment_id=e, observed="o", passed=i != 1, effect="+1", confidence="med",
        hypothesis_state="supported" if i != 1 else "refuted")
assert run("gate", "--phase", "exp").returncode == 0
for i in range(1, 4):
    add("loop", iteration=i, target=hs[0], change="c", score_before=1, score_after=1, kept=False, voi="low",
        cost="1", evaluator="crux-score", **({"stop_reason": "plateau"} if i == 3 else {}))
assert run("gate", "--phase", "loop").returncode == 0
run("report")
sk = open(os.path.join(D, "report.skeleton.md")).read()
assert "研究状态" in sk and "| H1" in sk
open(os.path.join(D, "report.md"), "w").write(sk + "\n" + " ".join(sids[:10]) + " H1 H2 H3\n")
assert run("gate", "--phase", "all").returncode == 0, run("gate", "--phase", "all", ok=(0, 10, 20)).stdout
open(os.path.join(D, "report.md"), "a").write("ghost S999\n")
assert run("gate", "--phase", "report", ok=(20,)).returncode == 20
# ablation
ex = os.path.join(ROOT, "examples", "ablation-toy")
p = subprocess.run([sys.executable, os.path.join(S, "ablate.py"), "--model", os.path.join(ex, "model.py"),
                    "--params", os.path.join(ex, "params.json"), "--samples", "3000"], capture_output=True, text=True)
assert p.returncode == 0 and "消融记分卡" in p.stdout, p.stderr
q = subprocess.run([sys.executable, os.path.join(S, "querygen.py"), "--topic", "solid-state battery", "--facets",
                    "sulfide,anode", "--zh", "固态电池", "--tier", "quick"], capture_output=True, text=True)
assert q.returncode == 0 and len(q.stdout.splitlines()) >= 40
shutil.rmtree(D)
print("smoke test passed")
