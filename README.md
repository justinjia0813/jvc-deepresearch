# jvc-deepresearch

一个让 AI 助手做**真正深度研究**的 Agent Skill：海量检索、百年史料与失败案例、第一性原理、四名同模型博士级辩手互相反驳、每条假设预注册并做小规模实验和消融拆解、最后在胜出路径上跑自动研究循环，直到边际价值耗尽。

它和一般 "deep research" 的区别不在搜得多，而在**每一步都留下可审计的台账，并由脚本卡门槛**：没搜够、没找失败案例、辩论没引证据、实验没先注册、循环没停机理由，都过不了 `gate`，不能说"完成"。

> 姊妹仓库：[jvc-analyst](https://github.com/justinjia0813/jvc-analyst)（早期股权投资的 12 个工作流 Skill）。jvc-deepresearch 可单独使用，也可作为其中赛道研究、技术尽调、投资论点的"深挖模式"。

## 流程

```
S0 定题 ─► S1 海量检索 ─► S2 第一性原理 ─► S3 四人辩论 ─► S4 验证与消融 ─► S5 自动研究循环 ─► S6 交付
            查询矩阵           不变量/成本地板      P 主张者            预注册实验           固定评估器
            5 个年代桶         参考类与基准率        S 怀疑者            回测/Fermi/蒙特卡洛   VOI 选题
            失败案例必搜       "必须为真"清单        H 历史学者          消融：每个因素值多少   变好才保留
            饱和检测           可证伪假设            E 第一性原理工程师   记分卡               停机理由
```

| 阶段 | 做什么 | 门槛（deep 档） |
| --- | --- | --- |
| S1 海量检索 | 子问题 × 视角 × 年代（pre1950 → 2015-now）× 语言 × 立场展开查询；读原文；失败案例单独标记 | ≥150 条查询、≥70 个独立来源、≥10 个失败案例、≥6 类来源、≥4 个年代桶、连续两轮新增率 <10% |
| S2 第一性原理 | 拆到物理/经济不变量与成本地板；用历史参考类定基准率；形成可证伪假设 | ≥5 条约束、≥3 个基准率、≥3 条假设且含反向假设 |
| S3 四人辩论 | 同一模型四个子代理：主张者、怀疑者、历史学者、第一性原理工程师；盲写开场 → 交叉质询 → 钢人后反驳 | 3 轮完整四角色、每个发言引用台账 ID、记录分歧点；首轮可信度过于一致时强制反回音室重写 |
| S4 验证与消融 | 每条假设先注册指标/阈值/预测再跑；`ablate.py` 给出消融价值、龙卷风、蒙特卡洛、方差贡献、交互项 | 每条假设有实验和结果、结果晚于注册、至少一个消融 |
| S5 自动研究循环 | 借鉴 karpathy/autoresearch 的棘轮：固定评估器、每轮固定预算、按价值信息量（VOI）选题、变好才保留 | ≥8 轮、评估器不变、有停机理由（plateau / voi / budget / refuted） |
| S6 交付 | 一页结论（带可信度与证据 ID）→ 约束 → 失败教训 → 记分卡 → 辩论分歧 → 循环轨迹 → 缺口 | 报告无"幽灵 ID"、带 `研究状态：` 标签 |

三个档位：`quick`（40 查询 / 2 轮辩论 / 3 轮循环）、`deep`（默认）、`max`（400 查询、并行检索子代理、4 轮辩论、循环到停机）。

## 安装

需要支持本地 Agent Skills 的 AI 助手（Claude Code、Codex、Cursor 等）和 Python 3.10+（脚本只用标准库）。

```bash
git clone https://github.com/justinjia0813/jvc-deepresearch.git ~/.agents/sources/jvc-deepresearch
cd ~/.agents/sources/jvc-deepresearch
./setup --global
python3 evals/smoke_test.py   # 可选：自检
```

## 使用

```text
/jvc-deepresearch 硫化物固态电池 2030 年前电芯成本能否低于 60 美元/kWh？
服务的决策：要不要在 2027 年前布局硫化物电解质上游。档位 deep。

/jvc-deepresearch max：AI for Materials 能否把新材料从发现到量产的周期缩短一半？
历史参考类至少覆盖 1950 年以来的半导体材料和电池材料。
```

## 脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/drctl.py` | 研究台账：`init / add / novelty / status / gate / waive / report / export`。只追加、哈希链防篡改；`gate` 退出码 0 ready / 10 partial / 20 blocked |
| `scripts/querygen.py` | 把研究问题展开成查询矩阵（失败、反方、第一性原理视角全保留） |
| `scripts/ablate.py` | 对假设模型做消融、龙卷风敏感性、蒙特卡洛、方差贡献和交互项，输出记分卡 |

```bash
S=skills/jvc-deepresearch/scripts
python3 $S/drctl.py init --run-dir dr-sse-20261124 --question "…" --decision "…" --tier deep
python3 $S/drctl.py add --run-dir dr-sse-20261124 source --json '{"title":"…","url_or_path":"…","source_class":"failure-postmortem","era":"1975-1999","date":"1991-06-01","independence_key":"…","failure":true,"round":1}'
python3 $S/drctl.py gate --run-dir dr-sse-20261124 --phase search
python3 $S/ablate.py --model examples/ablation-toy/model.py --params examples/ablation-toy/params.json
```

## 仓库结构

```
skills/jvc-deepresearch/
  SKILL.md                    主流程与硬规则
  references/                 ledger / search-sweep / first-principles / debate / experiments / autoloop
  templates/                  辩手提示词、实验卡、program.md（循环说明书）、报告模板
  scripts/                    drctl.py, querygen.py, ablate.py
  agents/interface.yaml
evals/                        smoke_test.py, trigger_cases.json
examples/ablation-toy/        消融用法示例（玩具模型，数字不代表研究结论）
```

## 设计依据

- 多智能体辩论提升事实性与推理：Du et al., *Improving Factuality and Reasoning in Language Models through Multiagent Debate* (2023)。
- 以辩论做可扩展监督：Irving, Christiano & Amodei, *AI safety via debate* (2018)。
- 自动研究循环：Andrej Karpathy, [karpathy/autoresearch](https://github.com/karpathy/autoresearch)（2026-03）——固定评估器、固定预算、只保留变好的改动。
- 参考类预测与基准率：Kahneman & Lovallo 的 outside view；Tetlock 的超级预测者研究。
- 预注册：先写指标与阈值再看结果，防止事后找理由。

## 局限

Skill 提供方法、门槛和脚本；检索、阅读、推理与实验由所用 AI 助手执行，质量受模型、工具与网络条件影响。门槛通过只说明流程没有偷工，不代表结论正确。不给投/不投或做/不做的终局结论，最终决定由使用者作出。

## License

MIT
