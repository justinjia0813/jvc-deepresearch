# 研究台账（ledger）

`ledger.jsonl` 是整个研究唯一的事实来源。报告、表格、实验结论都从它派生；报告里引用的每个 ID 都必须能在台账里找到（`gate --phase report` 会查"幽灵 ID"）。

## 规则

- **只追加**。每条记录带 `prev`（上一条指纹）和 `fp`（本条指纹），手改历史会让 `load` 报 chain broken。
- **更正 = 追加同类型新记录**，带 `"supersedes": "<旧ID>"`；旧记录自动失效但保留。
- 同一网页/数据集的转载、通稿用同一个 `independence_key`（如 `kpmg-venture-pulse-2026q3`），只算一个独立来源。
- 失败案例来源加 `"failure": true`。
- 公司/作者自述的数字加 `"stance": "self-report"`；对应 claim 用 `kind: "self-report"`。

## 记录类型与必填字段

| 类型 | ID | 必填 | 常用可选 |
| --- | --- | --- | --- |
| scope | SC | question, decision | tier, in_scope, out_of_scope, horizon, geography, user_bias |
| question | QN | text, priority(high/medium/low), would_change_answer | state(open/answered/evidence-gap), answer_ids |
| query | Q | text, round, source_class_target, result_count | tool, lang, era_target, question_id, outcome |
| source | S | title, url_or_path, source_class, era, date, independence_key | round, failure, stance, excerpt, publisher |
| claim | C | text, source_ids, kind(fact/estimate/self-report/opinion/inference) | question_id, counter_source_ids, confidence |
| constraint | K | text, value, unit, basis | source_ids, derivation |
| baserate | B | reference_class, rate, n, source_ids | window, caveats |
| hypothesis | H | text, prediction, falsifier, metric | contrarian, prior, dropped |
| debate | D | round, role(P/S/H/E), stage(opening/cross-exam/rebuttal/closing), text, cites[], credences{H#:0..1} | would_change_mind, anti_echo_rewrite |
| crux | X | text, hypothesis_ids[], cheapest_test | owner_roles |
| experiment | E | hypothesis_id, method, metric, threshold, prediction, decision_rule, budget | ablation, script_path, crux_id |
| result | R | experiment_id, observed, passed, effect, confidence, hypothesis_state | surprise, artifacts |
| loop | L | iteration, target, change, score_before, score_after, kept, voi, cost | evaluator, stop_reason(plateau/voi/budget/refuted) |
| waiver | W | rule, reason, residual_risk | approved_by |

`source_class` 取值：academic, failure-postmortem, practitioner-blog, primary-data, patent-standard, report-news, book-history, code-dataset, expert, user-material。
`era` 取值：pre1950, 1950-1974, 1975-1999, 2000-2014, 2015-now（指来源所讲事件/数据的年代，不是网页发布日期；同时跨多个年代时取最主要的一个，另记 `era_also`）。

## 门槛（`gate`）

| 阶段 | 检查 |
| --- | --- |
| search | 查询数、独立来源数、失败案例数、来源类型数、年代桶数达到档位下限；最近 N 轮新增率 < 10%；高优先子问题无 open |
| fp | 约束数、基准率数达标；≥3 条假设且至少一条 contrarian |
| debate | 四角色完整轮数达标；≥1 个 crux；首轮可信度 σ 全部 < 0.10 时必须有反回音室重写 |
| exp | 每条未放弃假设都有预注册实验和结果；结果时间晚于注册；至少一个消融实验 |
| loop | 迭代数达标；有合法停机理由；评估器全程不变 |
| report | report.md 存在、无幽灵 ID、引用 ≥10 个 ID、带 `研究状态：` 标签 |

退出码：0 ready，10 partial（只剩豁免项），20 blocked，1 命令或数据错误。豁免（`waive`）只能把 blocked 降成 partial，永远到不了 ready。
