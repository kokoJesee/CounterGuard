# 训练专用研究拟合验收

交付[研究拟合接口](../../study-fit.md)：独立 protocol/split/sample/人工标签审核、训练输入来源重建、
initial/refined 拟合、反例见证、研究 Scope 和不可变成功/拒绝回执。
本批全部使用明确的工具自有合成 fixture，**不计外部研究样本**。

最终执行：

```powershell
uv run pytest -m "not slow" -q
uv run pytest tests/unit/test_study_fit_provenance.py tests/integration/test_study_fit.py -q
uv run ruff check .
uv run python scripts/export_study_fit_schemas.py --check
uv run python scripts/export_study_feature_schemas.py --check
uv run python scripts/export_study_schemas.py --check
```

快速层 **1124 passed / 249 deselected**，其中新拟合纯检查 34 项。
另跑来源/Git 专项 **4 passed**，明确标 slow；两组并行启动，时长不是性能对比。
Ruff 与新文件格式检查通过，7 新 fit / 3 既有 feature / 9 既有 research Schema 字节均匹配运行模型。
完整必要计数与实现绑定见 [acceptance.json](acceptance.json)。

自有 fixture 的 initial 有 2 正例和 1 合法负例，学出 version；加入冻结的合法负例后，
refined 为 version AND interface，训练计数分别为 2/0/1/0 与 2/0/2/0（TP/FP/TN/FN）。
每个条件都有删除后会放入的反例见证；20 次训练迭代乱序保持整个拟合和规则摘要一致。
无负例时保留 `no_counterexample`、`scope=null`；CLI fit 返回 4，verify 返回 0 时仍保留原 refusal。

纯检查包括：阶段/组/仓库/逻辑目标分离，初始不读后续成员，holdout 在读协议前拒绝且无文件引用；
变更 input/context/audit/规范依据/审核/实现 pin，重签全部内部关系一致的假学习链，
同名 helper 代替静态导出的真实定义，新增正例伪装 refinement，预算超限、撤回和输出路径拒绝。
标注分歧保留双方，不自动调整 golden 或标签。

来源专项中，3 项使用完整的 B/F/H → binding → Evidence → 最小 Guard 来源核验，
Git 与 Docker transport 是替身；合成响应不宣称发生过真实执行。
它证明新拟合确实消费原验证器，并拒绝 Guard 重签、来源仓库替换；拟合不新增执行调用。

另 1 项对四个自有目标创建**真实 Git 提交**，检查初次/重复拟合及独立 verify。
工作树源码和 conftest 被改成报错哨兵后，仍只读取固定提交，输出相同；没有 import 或执行目标。
这项的 source verifier 明确使用替身，不把它单独称为完整真实 B/F/H 端到端验证。
两类专项分别验证来源复用与实际目标快照，不能合并宣称一次新的真实 Docker 实验。

原始 JUnit/日志保留仓库外，公开回执只列必要计数、摘要和限制。
本批未运行全量或 Docker，未重新捕获 termcolor、未执行 colored，也没有新依赖。
全部原有保护文件和发布标签保持原样；新增源码改变全包指纹，旧链按原规则需新 ID 重建。

当前完成训练侧来源绑定；新 fit/Scope 的 `execution_allowed` 恒为 false。
尚未接入研究 plan/admission/authorization，learned replay 仍 unknown / run=null。
外部语义裁决、谱系分组、足够独立样本、正式 scope_v2 冻结和最终评测仍未完成。
