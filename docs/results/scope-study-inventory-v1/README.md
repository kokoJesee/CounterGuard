# 公开评测事实的独立盘点

本记录为[新作用域研究](../../experiments/scope-v2/design.md)提供工程参照。机器事实见 [inventory.json](inventory.json)，验收见 [validation.json](validation.json)。

入口是 `uv run python scripts/run_scope_study.py inventory`，只读取已经公开的 scope_v1 数据和结果，从原始预测重算计数。它未调用生产评测器/learner，未重新捕获 Evidence、编译 Guard 或执行目标，未读取 scope_v2 标签。

| 方法 | TP / FP / TN / FN | 历史执行数 | false_alert_rate | bug_recall |
|---|---|---:|---|---|
| B1 always | 2 / 4 / 0 / 0 | 6 | 2 / 5 | 1 / 1 |
| B2 interface | 2 / 2 / 2 / 0 | 4 | 1 / 5 | 1 / 1 |
| learned initial | 2 / 2 / 2 / 0 | 4 | 1 / 5 | 1 / 1 |
| learned refined | 2 / 0 / 4 / 0 | 2 | 0 / 5 | 1 / 1 |

训练 B1 为 4/5/0/0，B2 为 4/3/2/0，与冻结标准相符。留出 6 行 × 4 方法共 24 份预测；initial→refined 纠正 2 个错误应用、保留 2 个适用样本，没有新增错误应用/拒绝。input-limit 族的留出 Bug 分母仍为 0。

这些是**历史公开事实一致性**，不是当前实现下重跑的 16 次测试，不核验历史 Docker/授权来源，也不增加泛化证据。原 manifest 绑定旧实现；不重签、不覆盖。新研究数据与研究 Docker 桥接尚未交付，生产 standalone 仍限已审核精确快照。

本次仅新增仓库外研究入口/测试/说明，没有修改运行包源码、冻结口径或原始产物。首次专项在受限环境的默认临时目录创建失败（6 passed、6 setup errors），改用工作区新临时目录后通过；首个 uv 命令也遇到默认缓存权限问题，改用工作区缓存，未改全局设置。后续实测及未运行项如实保存在 validation.json。
