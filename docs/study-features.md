# 研究 fixture 的静态特征

`ast-features.study.v1` 可静态读取一个源码文件中的单个顶层同步函数，支持普通 `for` 和生成器表达式。
当前用途严格限定为 `tool_owned_research_fixture_only`，没有外部项目的学习或执行授权。
实现位于 [study_features.py](../src/counterguard/study_features.py)，
逐字段人工 golden 和拒绝案例见 [专项](../tests/unit/test_study_features.py)。

## 输入与审核

`StudyFeatureContext` 明确绑定源文件相对路径、原始字节摘要、函数名、真实 UTC 审核时间、操作者、原因和元数据依据。
`contract_family`、`contract_version`、`module_group`、`interface_kind` 来自可信本机操作者的独立审核，不能从 label、预期 AST 或运行成败推导。
接口目前只有 `value_return` 与 `stdout_write` 两项 fixture 类别；它们不同，B2 应按不同接口处理。
这些类别尚未成为外部项目的冻结分类标准。

提取调用必须另传 `context_anchor`，并同时检查 context 自摘要与源文件原始字节。
调用者在可变 context 之外保存可信摘要；重新签一份 context 不会匹配原摘要。
若主机、验证器和可信摘要都被控制，这种机制不能提供保护；操作者文本也不是身份认证。
审核本身是人工信任输入，当前不声称依据文本的语义已被自动证明。

`source_ref` 只标识本次读取的文件，不构成 Git 来源链或 B/F/H 核验。
这份记录不能代替研究 replay 的 source/target/review，也不能直接注册为生产 Scope。

## 精确的提取语义

提取器不 import、eval 或 exec 目标。它只解析源码，并编译 AST 检查语法与绑定是否合法，不运行生成的 code object。
只计所选函数体，默认值、注解、其他函数和模块级表达式不供应 token。
调用 helper 不会自动吸收 helper 的特征；闭包分析和特征分析是两件事。

研究词汇保留原 10 个 token 字符串，配独立 extractor 名称和 `vocabulary_digest`。
旧 `ast-features.v1` 仍拒绝循环和生成器，旧标注与摘要不改变。

| token | 本版本的静态含义 |
|---|---|
| `branch:is_member` | If/IfExp 条件或生成器 filter 引用名为 is_member 的形参；生成器局部重名不算形参 |
| `branch:none` | 上述条件中，对形参名使用 `is None` / `is not None`，包含反向写法；不表示无分支 |
| `range:check` | 同一 If/IfExp 条件、单个生成器 filter 或 Compare/BoolOp 生成器产出式中，同一语法表达式出现数值上下界 |
| `decimal:multiply` / `decimal:subtract` | 函数体中的乘法 / 减法语法，不推断数值类型 |
| `int:parse` | 未被局部或模块名字遮蔽的 builtin int，或有限解析的 builtins.int 导入 |
| `regex:ascii_digits` | 有限解析的 re.fullmatch，模式为字面量 `[0-9]` 或 `[0-9]+` |
| `round:half_up` | 有限解析的 decimal.ROUND_HALF_UP 读取 |
| `str:isascii` / `str:isdecimal` | 对相应同名属性的调用，不推断接收者类型 |

范围 token 只证明语法出现，不证明运行时会拒绝、夹紧、遍历所有值或满足契约。
不跨独立条件、filter 或生成器作用域拼接上下界。不做控制流、类型、任意别名或动态模块变更的语义分析。
模块条件分支中的 import/定义会保守遮蔽同名库绑定，不能冒充确定的 builtin 或标准库调用；模块 star import 明确拒绝。

For 的普通 name/tuple/list 绑定属于函数局部；生成器的绑定只属于生成器作用域，不向外泄漏。
生成器第一个 iterable 按外层名字解析，后续 iterable、filter 和产出式使用生成器局部名字。
支持嵌套生成器；属性、下标或 starred 迭代绑定明确拒绝。
其余 nested 函数/类、lambda、list/set/dict comprehension、walrus、async/yield、try/with/while、
函数内 import/global/nonlocal/delete、type alias 和函数类型参数等保持 unsupported。

参数签名独立使用 `parameter-shape.study.v1`：只记 posonly/poskw/kwonly 个数、位置默认参数个数、
关键字默认参数位图，以及 vararg/varkw 是否存在。忽略参数名、注解、默认字面量和返回类型。
这表示调用形状，不能证明实际映射兼容；研究 call map 仍需单独核验。

预算为每文件 256 KiB、16000 AST 节点、深度 80、8 层生成器。
不支持或超限时不返回一份看起来成功的空特征。

## 提取、对账与核验

Python Interface：

```python
record = extract_study_features(source_bytes, context, context_anchor=trusted_digest)
audit = audit_study_features(source_bytes, context, expected_vector, context_anchor=trusted_digest)
verify_study_feature_record(record, source_bytes, context, context_anchor=trusted_digest)
verify_study_feature_audit(audit, source_bytes, context, context_anchor=trusted_digest)
example = study_training_example(record.features, reviewed_applicability)
```

每个 token 带源码起止行与 AST 节点类别见证；没有 token 的普通计算函数可以得到空集合。
record 保存 context/source/vocabulary/全包实现摘要，内层只含精确 `FeatureVector`。
verify 独立重新提取并比较全部事实；改行号、元数据、词汇或实现摘要后重签，也不能通过。

对账保留完整 expected/actual、missing/unexpected 和元数据差异，不自动判任一侧正确。
不一致时停止消费，保留双方与依据，交维护者裁决；更改已冻结标注或算法须新版本。
对账一致只证明注释与提取器一致，不证明标签和行为正确。

从源码仓库根，可对已经人工审核的自有 fixture 运行：

```powershell
uv run python scripts/audit_study_features.py --workspace <workspace> --context <context.json> --context-digest <trusted-context-digest> --expected <manual-vector.json> --output <new-audit.json>
uv run python scripts/export_study_feature_schemas.py --check
uv run pytest tests/unit/test_study_features.py -q
```

所有输入相对路径按 workspace 解析。输入使用安全文件读取；输出也必须在该目录内，不覆盖不同内容。
省略 `--expected` 时输出提取 record。CLI 返回 0 表示成功提取/对账一致；4 表示明确不支持或对账不一致；
5 表示来源摘要/路径/输入损坏，文件读取预算超限也拒绝；argparse 参数错误为 2。
错误诊断只输出有限原因，不回显本机路径或任意源码。

## learner 与执行的界限

显式投影只接受精确 `FeatureVector` 与 bool，不接受外层 record、dict、子类或带来源字段的扩展。
复用原 `learn_scope` 的 `conjunction.v1`：至少 2 个正样本与 1 个负样本、1–3 条合取的 eager 搜索、
训练零误差、每条保留 clause 有反例见证。没有负样本仍拒绝；20 次乱序的规则与学习摘要一致。

研究 protocol/split/fit/Scope 的训练绑定由[独立拟合接口](study-fit.md)核验；
独立的[研究重放 v2](research-fitted-replay.md)另核对拟合与执行两个可信锚、查询实际定义和特征，
只有新版审核/准入/授权通过才可执行。没有把裸学习结果传给 Docker 的入口。
C1 plan/admission v1 与 authorization v6 不接收这些新字段，旧版 learned replay
继续返回 `study_fit_interface_not_implemented`，`run=null`。
fixture 学习成功不会增加真实研究样本数，也不会产生任何自动标签或正式研究结论。

## 摘要与重算

新增包源码改变全包实现指纹。旧 binding/capture/Guard/review/replay 在需要当前实现时须使用新 ID 完整重建，
不能重签历史 JSON；原 H 字节未变则可复用 H。
本次不重物化外部来源、不改既有 artifact。三份新 Schema 独立存于 [study-features-v1](../schemas/study-features-v1/)。
验收范围与未执行项见[结果说明](results/study-features-v1/README.md)。
