# 研究 fixture 的训练拟合与来源核验

工具自有 fixture 可以通过独立的 `study-fit-protocol.v1`，从获审训练成员拟合研究 Scope，
再从原始来源独立重建结果。这是训练专用接口，不生成 Docker 或生产调度许可。
真实外部数据的 `scope_v2` 协议、标签和分组尚未冻结。

实现见 [study_fit.py](../src/counterguard/study_fit.py)，
严格模型与七份 Schema 见 [study_fit_models.py](../src/counterguard/study_fit_models.py)、
[study-fit-v1](../schemas/study-fit-v1/)。旧数据、旧 Schema、`ast-features.v1` 和 `conjunction.v1` 不改写。

## 输入与信任来源

| 记录 | 绑定内容与作用 |
|---|---|
| `study-sample.v1` | 独立目标、项目组、feature context 和人工特征对账的精确引用/摘要；不含适用性标签 |
| `study-label-review.v1` | source/Guard、sample/target、人工适用性与合法反例声明、固定目标提交内的规范依据 pins、真实审核时间/操作者 |
| `study-split.v1` | initial、refinement additions 的成员与标签 pins；holdout 只含承诺、组和仓库身份，不含文件路径 |
| `study-fit-protocol.v1` | source/Guard、split、特征/签名/词汇版本、原 learner、受限 fixture 预算 |
| `study-fit-review.v1` | 拟合前由可信本机操作者批准的 protocol/split/source 与全包实现 pin；可追加撤回事件 |
| `study-fit.v1` | 实际消费成员的 pins、阶段、学习/解释/研究 Scope，或明确的拒绝原因 |
| `study-learned-scope.v1` | 精确 source/Guard/protocol/split/review/训练绑定、learning/explanation 摘要与规范化条件 |

审核函数 `issue_fit_review` 不调用 learner，也不打开 holdout 文件。
调用者单独保存返回的可信审核摘要，Session 通过该摘要核对审核事件，不能从可变协议自行取得批准。
审核是可信本机操作记录，不提供身份签名、远程角色或自动发现最新撤回的能力；使用撤回事件时须显式换用新摘要。
同时控制可信摘要、代码和主机的攻击不在保证内。

标签的语义由人审。当前 `own_contract_confirmation=trusted_manual_fixture_review` 表示人工确认自有 fixture 的规范，
不冒充一次已执行的契约检查，不自动分配外部标签。
工具核对规范依据确实来自固定目标提交及其字节，但不能证明这份文本的语义或人工结论正确。
合法反例声明与适用性必须一致，refinement additions 全部必须是获审负例。

## 实际重建的事实

来源复用 `inspect_source`，核对当前实现下的 Guard、最小 case、自检、Evidence 和真实 B/F/H 链；
不接受只具有正确自摘要的 source JSON。
目标复用 `inspect_target`，从固定 Git 提交重新生成完整树、闭包和评估摘要，工作树改动不能替代提交。
仓库路径由可信调用方显式提供，按独立本机仓库身份摘要匹配；样本 JSON 不提供宿主路径。

特征从固定目标提交的原始字节重建，绑定[已审核 context、行见证及人工对账](study-features.md)。
direct 目标必须精确匹配目标文件与符号；static-reexport-v2 复用已批准的 static-root-reexport.v2，
匹配实际 `definition_ref/definition_symbol`。闭包里的同名 helper 不能代替目标定义。
支持不足或标注不一致时明确停止，不回填假特征、不自动修改人工期望。

split 先拒绝重复 sample ID、逻辑目标键、训练引用以及跨组/仓库的训练—留出重叠。
逻辑目标键取仓库身份、固定 revision、公开 module/symbol，改 target ID 或文件引用不能多造一个观察。
同一仓库不能改名成两个项目组，来源项目组和来源仓库也不能进入 holdout。
镜像、fork 或复制代码的谱系是否应归同一组，仍需独立人审；本机路径摘要不证明项目独立。

initial 只读取冻结 initial 的 sample/label/context/audit。
refined 读取 initial 加全部冻结 additions；初始阶段不提前读取 additions 内容。
holdout 没有读取入口，接口在读取协议前拒绝 phase=holdout。
承诺本身可以被读取，内容未被解封或验证，不应把承诺数量当成已完成的真实留出评测。

## 学习、拒绝与确定性

只有精确 `TrainingExample(FeatureVector, bool)` 进入纯 learner；路径、来源/分组 ID、审核依据和运行结果均留在外层。
复用 `conjunction.v1`：至少 2 正例、1 负例；eager 枚举 1–3 条合取；训练零 FP/FN；
既有并列裁决和每条保留条件的反例见证不变。解释通过 `explain_scope` 独立绑定同一训练多重集。

没有负例、正例不足、标签冲突或无可支持规则时，写出 `status=refused`、具体 refusal_code、`scope=null`。
不会默认全适用。输入损坏、特征不支持、撤回或预算不足则按下述命令语义停止。
本版本为自有 fixture 限定最多 32 个训练成员、32 个候选谓词，超限拒绝，不截断搜索空间；
这不是正式外部研究的容量或标准变更。

拟合结果不生成时间戳，时间仅来自真实人工审核输入。
固定输入与审核不变时，规范化 pins、纯学习结果、解释和研究 Scope 可重复。
20 次训练迭代乱序检查规则与拟合摘要相同；重新审核或改路径等来源信息会改变外层摘要，不能伪造相同历史。

`verify` 重读当前源链、目标提交、审核、人工依据和特征，重新拟合并比较整个结果。
即使重签 learning、explanation、Scope 和外层 fit，使其内部关系完全一致，也必须符合实际训练事实。
解析或自摘要检查不代替 verify；生产 Scope 与 C1 replay parser 不接受这些新记录。

## Python 与命令行

Session 的参数是 source repo、workspace、仓库身份摘要到本机路径的字典、独立可信 review anchor。
Python Interface：

```python
result = session.fit("protocol.json", "review.json", phase="initial", output=Path("fits/initial.json"))
refined = session.fit("protocol.json", "review.json", phase="refined", output=Path("fits/refined.json"))
verified = session.verify(Path("fits/refined.json"))
```

准备并获审的自有 fixture 可在源码仓库根运行：

```powershell
uv run python scripts/fit_scope_study.py fit --workspace <workspace> --source-repo <source-clone> --repository <training-clone> --review-digest <trusted-digest> --protocol protocol.json --review review.json --phase initial --output fits/initial.json
uv run python scripts/fit_scope_study.py fit --workspace <workspace> --source-repo <source-clone> --repository <training-clone> --review-digest <trusted-digest> --protocol protocol.json --review review.json --phase refined --output fits/refined.json
uv run python scripts/fit_scope_study.py verify --workspace <workspace> --source-repo <source-clone> --repository <training-clone> --review-digest <trusted-digest> --result fits/refined.json
uv run python scripts/export_study_fit_schemas.py --check
```

多个训练仓库重复传 `--repository`；只有本阶段实际消费的仓库需要提供。
输入引用相对 workspace，输出须在 workspace 内且位于各仓库之外；不同内容不可覆盖。
CLI：拟合成功返回 0，证据不足的已保存 refusal 返回 4；verify 的 0 只表示事实可重建，refused 仍保持 refused。
不支持/审核撤回/缺少仓库/预算不足为 4；输入损坏与来源漂移为 5；参数错误为 2。
错误输出采用有限原因，不回显任意源码或本机路径。

## 执行与历史边界

protocol、fit、scope 都固定 `execution_allowed=false`；本接口没有目标执行器或本地 fallback。
尚未将 fit/scope 接入新研究 plan/admission/authorization，C1 learned replay 仍 unknown / run=null。
训练通过不提升 Candidate/Shadow/Active 权限，也不计为真实外部研究场景或最终研究结论。

新包源码改变全包实现指纹；消费当前实现时，旧 binding/capture/Guard/review 等须用新 ID 完整重建，
不能重签或覆盖既有产物。验证不提供并发文件系统的原子快照或远程身份保证。
本批测试和未测范围见[验收记录](results/study-fit-v1/README.md)。
