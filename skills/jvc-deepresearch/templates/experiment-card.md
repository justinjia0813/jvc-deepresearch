# 实验卡 E{n}（预注册，跑之前填完）

- 假设：H{k} — {一句话}
- 判决的分歧点：X{m}（可选）
- 方法：{回测 / Fermi / 蒙特卡洛 / 复现 / 代码实验 / 数据切片 / 专家问题}
- 指标（metric）：{名称，单位}
- 预测（prediction）：{假设为真时的预期值或区间}
- 阈值（threshold）：{过线标准}
- 判定规则（decision_rule）：{≥… 升级为 supported；介于…为 inconclusive；≤… 为 refuted}
- 预算（budget）：{时间 / 算力 / token}
- 输入与来源：{参数 = 值 [S#/K#]}
- 脚本：experiments/E{n}_{slug}.py（随机种子 = 7）

登记：`drctl.py add experiment --json '{...}'`

---
## 结果（跑完后填）
- 实测（observed）：
- 是否过线（passed）：
- 效应量（effect）：
- 置信度（confidence）：
- 假设状态：supported / weakened / refuted / inconclusive
- 意外发现（surprise）：

登记：`drctl.py add result --json '{...}'`
