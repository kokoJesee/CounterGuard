# 数据契约与摘要边界

本文说明当前持久化接口，字段校验以 `src/evidenceguard/models.py`、`predicates.py`、`features.py`、`baselines.py` 和 `protocol.py` 为准。JSON Schema 位于 `schemas/`，业务跨字段不变量另由严格模型与 verify 检查。

## Guard 的 semantic_digest

`semantic_digest` 使用当前固定的 `guard-semantic.v1` 投影规则，由 `protocol.guard_semantic_digest` 计算。它绑定**指定身份和版本的 Guard 执行内容**；不同 Guard ID 即使断言相同，也不共享此摘要。

精确字段集合为下表的 9 个顶层字段，不通过动态排除字段的方式生成：

| 字段 | 包含内容 |
|---|---|
| `guard_id` | Guard 身份 |
| `guard_version` | Guard 整数版本 |
| `contract_id` | 原业务契约身份 |
| `target_interface` | `contract_family`、`contract_version`、`interface_kind`、`symbol_signature` 四个字段 |
| `argument_types` | 完整参数名与类型映射 |
| `return_type` | 返回类型 |
| `cases` | 全部最小 case；每项包括 `case_id`、`args` 以及恰好一个 `expected` / `raises` |
| `generator_version` | 确定性测试生成器版本 |
| `test_digest` | 生成的 `test_guard.py` 原始字节摘要 |

算法：取上述字段的实际值，将嵌套模型转为 JSON 值，使用 UTF-8、键排序、紧凑分隔符、禁止 NaN 的规范 JSON，计算 SHA-256，输出 `sha256:<64 位小写十六进制>`。字段值与 case 数组顺序均参与摘要；`test_ref` 路径不参与。`guard-semantic.v1` 是这套规则的名称，**不是额外加入摘要载荷的第十个字段**。

明确排除：`schema_version`、`created_at`、`source_evidence_id/ref/digest`、`contract_digest`、`source_buggy_digest`、`source_fixed_digest`、`validation_run`（含 run ID、日志和时间）、`test_ref`、`state` 和 `artifact_digest`。完整 source contract 内容仍由协议的 source pin 和来源审核检查；最小执行内容则在 cases、接口、类型与测试摘要中固定。

排除运行期字段，使相同源码在新的可信工作区重新捕获后仍符合实验协议。它不证明来源记录有效，也不证明 Guard 适用，更不单独证明任意目标正确。

Registry / CI 的使用顺序：

1. `guard verify` 审核实际 Guard 自摘要、测试字节、Evidence、输入及日志来源链。
2. 比较协议要求的 `semantic_digest`，确认执行内容与冻结版本一致。
3. Scope 的 `guard_digest` 仍绑定本次实际 Guard 的 `artifact_digest`；新工作区重新捕获后必须重新生成该 Scope。
4. CI 仍需独立做作用域判断、执行和生命周期检查；不能只比较语义摘要就启用或放行。

增加、删除或改变投影字段必须升级投影规则和协议；不得改 `scope_v1` 的已冻结摘要或 golden 期望来消除失败。当前协议 digest 保持 D5 的 `sha256:1f401186a3f51c17e582dbbdc96f9324e47e128f90fcb91f29594690bc8daa3a`。

## FeatureVector 与 AST token

FeatureVector 只包含五个标量字段和 `ast_features`。前四项从可信契约元数据取得；`module_group` 来自显式上下文；只有 AST 集合从源码生成。目标名称、路径、case、Oracle 和标签均在模型之外。

`branch:none` 的历史名称表示 **Python None 身份检查**：`ast.If` 或 `ast.IfExp` 的 test 内，一个正式参数与 `None` 通过 `is` / `is not` 比较，允许左右交换。它不表示缺少分支。

| 代码形态 | `branch:none` |
|---|---|
| `if raw is None:`，raw 是参数 | 有 |
| `x if raw is not None else y` | 有 |
| `if None is raw:` | 有 |
| `if raw == None:` | 无 |
| 局部变量 `other is None`，other 不是参数 | 无 |
| `return raw is None`，未作为 If/IfExp test | 无 |
| `return x + 1` 或只有 `if x > 0` | 无 |

`branch:is_member` 同样只检查 If/IfExp test 对正式参数 `is_member` 的引用。函数体其他地方出现名字或字符串均不算。没有符合条件的分支时可以没有任何 branch token；合法的纯计算目标可以产生空 AST 集合。失败或不支持的结构则抛 `FeatureExtractionError`，不能返回空集。

保持现有 token 字符串以兼容 `scope_v1` 的冻结标注；任何将名称改成 `branch:none_check` 的迁移都留给新的词汇/协议版本。

剩余词汇的具体边界：

- `decimal:multiply/subtract` 是目标函数体中的 `BinOp(Mult/Sub)`，名字不承诺完成 Decimal 类型推导。
- `int:parse` 为未被局部/模块绑定遮蔽的内建 `int` 调用，也支持显式导入 `builtins.int` 的别名。
- `regex:ascii_digits` 只认已解析的 `re.fullmatch` 调用与字符串字面量 `[0-9]` / `[0-9]+`；显式 import 别名可识别。`\d+`、`re.match`、动态 pattern 不算。
- `range:check` 要求同一个 If/IfExp test 中，对同一个 Name/Attribute/Subscript 表达式出现两个方向的数值上下界比较。支持 `< <= > >=`、链式比较和正负数值字面量；不同值、单边比较、分别位于不同 test 的比较、动态界变量都不算。它是语法存在性特征，不证明区间逻辑正确。
- `round:half_up` 为加载已解析的 `decimal.ROUND_HALF_UP`，支持显式 import 别名，排除遮蔽。
- `str:isascii/isdecimal` 为对应 attribute 的 Call；仅引用方法不算，也不承诺推导接收对象的类型。

`ast-features.v1` 只支持唯一、无装饰器的同步顶层函数。只遍历它的函数体，不读其他函数体、默认参数或模块表达式作为特征。嵌套作用域、lambda、推导式、async、yield、循环、with、try、match、函数内 import、global/nonlocal 等明确拒绝；扩展支持时需增加边界验收，必要时升级提取器版本。全过程只读并解析 AST，不导入或执行目标模块。

## FeatureRecord 与对账报告

`feature-extraction.v1` 外层记录 extractor/vocabulary 版本与摘要、TargetRef、目标原始字节摘要、契约引用与原始字节摘要、FeatureVector 和自身摘要。外层身份/来源不传入学习器。没有生成时间字段，相同输入可得到相同字节；同提取器版本和 sample ID 的不同输入不能原地覆盖。

`feature-audit.v1` 报告记录数据文件摘要、每个样本的 expected/actual、AST `missing/unexpected`、标量 `metadata_diff`、来源 feature 引用和摘要。错误行单独保留原因，不伪造 actual。审计不读取适用性、违规或 compliance 标签来提取特征；已公开 holdout 的源码与手工 AST 可以用于 D6 对账，不进入 D7 拟合。

退出 0 要求所有行 matched；差异返回 1，配置或词汇错误返回 2，提取失败返回 3，不可变资产冲突返回 5。混合失败时优先级为 5、3、2、1。错误和差异都会先写出报告。
