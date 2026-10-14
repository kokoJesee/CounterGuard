# module_group 来源与审计规则

`module_group` 是需要来源审核的架构元数据。它不能从适用性、违规、compliance 标签、case ID、样本名称或测试结果推导，也不能由 learner 临时创建。

当前唯一来源是版本控制中的 `benchmarks/context/scope_v1.json`：

| 架构包 | module_group | 责任依据 |
|---|---|---|
| `examples.discount` | `retail` | 各版本会员定价、应付金额和优惠金额接口 |
| `examples.validation` | `shared_validation` | 各版本 query 和 worker 输入校验接口 |

清单记录 owner、来源说明、每条包前缀映射的 basis 和自身摘要。依据是 D2 fixture 的包职责，覆盖 buggy、fixed、不同契约版本和不同接口；不根据训练类别分组。

```text
context_id: scope_v1_module_context
artifact_digest: sha256:08f548c920924dac44f2058014b64c79e6d18f348b820a6535be7b1795f1ad6a
```

规则使用点分包边界匹配，禁止重复或重叠前缀；未匹配或歧义时失败。`examples.discounted` 不属于 `examples.discount`。当前固定两条架构包规则；D7 同时核对 context 自摘要和固定摘要，因此修改值后重新计算自摘要也不能悄悄改变 scope_v1。

新增模块组时，项目维护者先记录已有架构职责或独立项目配置来源，再由数据审核者检查映射是否含目标状态/标签信息，并冻结新 context 与实验协议版本。禁止为提高拟合结果，把一个 buggy/fixed 文件或一类已知标签单独划成模块组。现有 scope_v1 不原地扩充。

如果同族出现另一个有独立架构依据的模块组，`module_group` 可以成为有信息量的特征；类型契约不禁止它参与学习。可信度来自独立来源、固定版本和审计，而不是“当前正好是常量”。

## D6 历史记录的更正

D6 v1 的 expected/actual 都从同一标注取得 module_group；其出现 30 次不能证明独立审计。历史报告保留，D6 的 15 matched 表示 AST 与契约字段一致，不应再解释成 module_group 来源审核通过。

D7 改成：expected 仍来自冻结标注，actual 从独立 context 解析，然后比较 module_group。新的 `feature-extraction.v2` 包含 context 引用与摘要；`feature-audit.v2` 记录 context 与差异。旧 v1 JSON 保持摘要兼容，但没有独立上下文证明，不能进入 D7 fit。

15 个样本重新核对后仍全部匹配，benchmark 标注值未改变。新记录按 context 摘要分目录，不覆盖原 D6 v1 记录。
