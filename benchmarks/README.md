# 基准数据契约

每个样本都把「作用域分类」和「契约执行」分开。

- `features` 是作用域学习**唯一允许**的完整特征输入。
- `guard_applicable` 作为监督目标单独提供，**永远不会是特征**。
- `contract_ref` 和 `target` 是执行与溯源元数据。
- `labels.guard_applicable` 表示该 guard 是否可在样本上下文运行。
- `labels.guard_violation` 只在 guard 适用时才是 `true`/`false`，否则是 `null`。
- `labels.contract_compliant` 描述目标相对于**它自己声明的契约**是否符合。它是评测标签，**绝不能传给作用域学习器**。
- `labels.basis` 记录已确认标签的可读理由。

作用域学习器**不得**拿到样本 ID、路径、模块/符号名、契约 ID、契约示例、期望输出、违规/合规标签、或 basis 文本。这些字段里有 `buggy`、`fixed`、`v1`、`legal` 之类的词，会泄露答案。

`ast_features` 目前是**人工确认、仅记录存在性**的摘要，用测试套件强制受控词表。它不是序列化的 AST。词表里每个操作只要在目标里出现就应该列出。AST 特征审计器现在自动提取同一受控词表，并要求与冻结标注**完全一致**；它绝不改写标注去迁就实现。

基准**故意包含**四种有意义的组合：

| Guard 适用 | 目标符合自己契约 | Guard 违规 |
|---|---|---|
| 是 | 是 | false |
| 是 | 否 | true |
| 否 | 是 | null |
| 否 | 否 | null |

训练和留出文件分开。留出样本只能用于评测，**不得**参与谓词生成、选择、平手裁决或阈值调优。

当前基准把 `contract_family` 当作可信预筛，并在**一个族内**学边界。所以它测的是 version 和 interface 谓词能否区分合法反例。跨族负样本需要同一批样本上的 per-guard 标签，留给后续 schema 修订。

Guard 编译器只选源 Evidence 里失败的 case：两条折扣断言 + 零值拒绝。当前独立身份是 `grd_discount_member_rate_regression_v2` 和 `grd_query_limit_zero_regression_v2`。适用 Guard 的违规由这些最小断言度量，与完整契约合规分开。迁移后 15 个标签值不变；完整性测试显式检查最小断言。

协议冻结把四个方法定义冻结在 `experiments/scope_v1.json`，两阶段训练和留出成员关系在 `benchmarks/splits/scope_v1.json`。B1 总是跑；B2 只读 `interface_kind` 并与冻结的 Guard 接口比较。协议冻结命令只执行训练行，拒绝 `--split holdout`。协议验证可以审计留出元数据和来源 pin；这些公开 fixture 是工程检查，不是盲测。

`branch:none` 是历史 token 名，指「用 `is` / `is not` 把形参与 Python `None` 比较的 If/IfExp 条件」。没有符合条件的条件就是没有这个 token；它从来不是「没有分支」的回退。完整边界在 `docs/data-contracts.md`。九行手工基线推导在 `docs/results/scope-v1/expected-train-derivation.md`。

`module_group` 独立地从 `context/scope_v1.json` 里已审核的架构包映射派生；冻结的 group pin 在作用域学习拟合前被验证。期望的 group 标注与这个来源比对，而不是复制。改动需要新的 context/protocol 版本。`docs/module-context-policy.md` 记录了特征审计修正，`docs/feature-adjudication.md` 定义如何在不改写冻结结果的前提下独立审核标注错误。
