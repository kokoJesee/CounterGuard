# 研究静态特征的自有 fixture 验收

本次交付 [ast-features.study.v1](../../study-features.md)：单函数静态提取、可信 context pin、
逐 token 行见证、人工特征对账、事实重建与精确 `FeatureVector` 学习投影。
支持普通 For 和 GeneratorExp；旧 ast-features.v1、生产 Scope 和冻结 scope_v1 保留。

实测命令：

```powershell
uv run pytest -m "not slow" -q
uv run pytest tests/unit/test_study_features.py tests/integration/test_study_features.py -q
uv run ruff check .
uv run python scripts/export_study_feature_schemas.py --check
uv run python scripts/export_study_schemas.py --check
```

最终专项 **65 passed**：64 项纯检查与 1 项明确标 slow 的真实 CLI 测试。
后者启动 4 次工具自身 Python，检查两次重复输出相同、人工标注不一致保留双方且返回 4、
独立 context 摘要不匹配返回 5。目标源码中含执行即报错的哨兵，未执行目标。
先前同一 CLI 专项另通过一次；保留独立记录，不把重复测试相加当作新增保证。
快速层的最终精确计数、时间和文件摘要见 [acceptance.json](acceptance.json)，专项与快速层存在重叠，不能求和。

Ruff 通过；3 份新增 feature Schema 与 9 份既有 research Schema 的实际字节均匹配运行模型。
确定性专项对自有训练行打乱 20 次，规则与学习摘要一致；initial 为 version 一条，
加入自有合法反例 fixture 后 refined 为 version AND interface，两条都具有删除后放入反例的见证。
这组标签是工具测试数据，不是外部研究标注；无负样本仍明确拒绝。

覆盖了循环/生成器的作用域、builtin/module/参数遮蔽、第一个 iterable 外层解析、
独立条件不合并范围、类型参数拒绝、局部注解不供特征、原始字节与审核 anchor、
重签行号/元数据/词汇/实现 pin、标注分歧保留、来源字段不进入 learner、预算及 unsupported。
元数据由可信操作者提供，测试不证明其语义。静态库绑定解析可能保守遗漏，逐样本对账仍是前置。

首轮 56 passed / 2 failed：严格子类 fixture 错把序列化 list 当 frozenset，
链接检查替身挂错模块。修正测试接线后复验通过，原失败 JUnit/日志保留在仓库外。
后续复核增加了类型参数、局部注解、条件导入遮蔽的防御与测试。
原始日志含本机路径，不公开；receipt 仅含必要计数、实现/日志摘要及保护结果。

本次没有运行全量、Docker、colored 或重新捕获 termcolor，也没有新增运行时依赖。
新增包源码会改变全包实现指纹；旧 capture/Guard/review 不能冒称当前实现核验通过，
需要当前实现时仍须新 ID 完整重建，不覆盖旧产物。

当前完成的是静态特征与纯 learner 接缝。研究 protocol/split/fit/scope 授权链仍未实现，
learned replay 保持 unknown / run=null；没有新真实研究场景、外部分类冻结或正式标签。
此验收不提升 Registry/CI 权限，不代替外部来源与语义准入。
