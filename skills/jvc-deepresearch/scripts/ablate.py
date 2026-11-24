#!/usr/bin/env python3
"""ablate — quantify how much each factor is worth in a hypothesis model.

Usage
  python3 ablate.py --model model.py --params params.json [--samples 20000] [--seed 7] [--out experiments/ablation]

model.py must define:   def model(p: dict) -> float
params.json:
  {"metric": "levelized cost, USD/kWh",
   "params": {
     "capex":   {"base": 120, "low": 90, "high": 160, "null": 120, "dist": "tri"},
     "cycles":  {"base": 6000, "low": 4000, "high": 9000, "null": 3000, "dist": "uniform"},
     ...}}
  base  : best estimate (cite ledger ids in an optional "src" field)
  low/high : plausible range (P10/P90 spirit)
  null  : value meaning "this factor contributes nothing" (the ablated state). Defaults to low.
  dist  : tri | uniform | lognorm  (for Monte Carlo)

Outputs (stdout markdown + <out>.json):
  1. Ablation  : model(base) - model(base with factor i set to null)   -> value of factor i
  2. Tornado   : swing between low and high, others at base
  3. Monte Carlo: P5 / P50 / P95 of the metric
  4. Variance share: first-order share of output variance per factor (squared rank correlation, normalised)
  5. Pairwise interaction for the top-3 factors: f(both null) - f(i null) - f(j null) + f(base)
Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import statistics


def load_model(path):
    spec = importlib.util.spec_from_file_location("drmodel", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "model"):
        raise SystemExit("model.py must define model(p: dict) -> float")
    return mod.model


def draw(spec, rng):
    lo, hi, b = spec["low"], spec["high"], spec["base"]
    d = spec.get("dist", "tri")
    if d == "uniform":
        return rng.uniform(lo, hi)
    if d == "lognorm":
        # lo/hi treated as P10/P90
        mu = (math.log(lo) + math.log(hi)) / 2
        sigma = (math.log(hi) - math.log(lo)) / (2 * 1.2816)
        return rng.lognormvariate(mu, sigma)
    return rng.triangular(lo, hi, min(max(b, lo), hi))


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for k, i in enumerate(order):
        r[i] = k
    return r


def corr(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def pct(xs, q):
    s = sorted(xs)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def fmt(x):
    return f"{x:,.4g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    f = load_model(a.model)
    cfg = json.load(open(a.params, encoding="utf-8"))
    P = cfg["params"]
    names = list(P)
    base = {k: v["base"] for k, v in P.items()}
    y0 = f(dict(base))

    abl = {}
    for k in names:
        p = dict(base); p[k] = P[k].get("null", P[k]["low"])
        abl[k] = y0 - f(p)

    tor = {}
    for k in names:
        lo = dict(base); lo[k] = P[k]["low"]
        hi = dict(base); hi[k] = P[k]["high"]
        ylo, yhi = f(lo), f(hi)
        tor[k] = (ylo, yhi, abs(yhi - ylo))

    rng = random.Random(a.seed)
    X = {k: [] for k in names}
    Y = []
    for _ in range(a.samples):
        p = {k: draw(P[k], rng) for k in names}
        try:
            y = f(p)
        except (ZeroDivisionError, ValueError):
            continue
        if not math.isfinite(y):
            continue
        Y.append(y)
        for k in names:
            X[k].append(p[k])
    ry = rank(Y)
    rho = {k: corr(rank(X[k]), ry) for k in names}
    tot = sum(r * r for r in rho.values()) or 1.0
    share = {k: rho[k] ** 2 / tot for k in names}

    top = sorted(names, key=lambda k: -abs(abl[k]))[:3]
    inter = {}
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            ki, kj = top[i], top[j]
            pi = dict(base); pi[ki] = P[ki].get("null", P[ki]["low"])
            pj = dict(base); pj[kj] = P[kj].get("null", P[kj]["low"])
            pij = dict(base); pij[ki] = pi[ki]; pij[kj] = pj[kj]
            inter[f"{ki}×{kj}"] = f(pij) - f(pi) - f(pj) + y0

    metric = cfg.get("metric", "metric")
    print(f"## 消融记分卡 · {metric}\n")
    print(f"基线值：**{fmt(y0)}**；蒙特卡洛 {len(Y)} 次：P5 {fmt(pct(Y, .05))} / P50 {fmt(pct(Y, .5))} / P95 {fmt(pct(Y, .95))}\n")
    print("| 因素 | 基线 | 置零状态 | 消融价值（基线−拿掉后） | 龙卷风 低→高 | 摆幅 | 方差贡献 | 来源 |")
    print("|---|---|---|---|---|---|---|---|")
    for k in sorted(names, key=lambda k: -tor[k][2]):
        print(f"| {k} | {fmt(P[k]['base'])} | {fmt(P[k].get('null', P[k]['low']))} | {fmt(abl[k])} | "
              f"{fmt(tor[k][0])} → {fmt(tor[k][1])} | {fmt(tor[k][2])} | {share[k]:.0%} | {P[k].get('src', '')} |")
    if inter:
        print("\n交互项（≠0 说明两个因素不能分开算）：")
        for k, v in inter.items():
            print(f"- {k}: {fmt(v)}")
    out = {"metric": metric, "base": y0, "mc": {"n": len(Y), "p5": pct(Y, .05), "p50": pct(Y, .5), "p95": pct(Y, .95)},
           "ablation": abl, "tornado": {k: list(v) for k, v in tor.items()}, "variance_share": share,
           "interactions": inter, "seed": a.seed}
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(out, open(a.out + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
