# 研究调用映射与 Docker 桥接提案

状态：**待维护者确认的新研究 Interface**。现有产品没有这里拟议的执行授权或命令。
本提案不授权 colored 执行，不冻结研究标签、split、特征或最终协议，也不提前宣称精化有效。
来源和输入审核见[只读回执](../../results/colored-review-v1/README.md)。

## 先解决哪一段

已有 termcolor 真实来源链；colored 的根包/闭包已达到静态 review_required。
两者之间缺少的是独立的研究 Module：在核验来源 Guard 后，将**同一组原始断言**用于另一个获审快照，
并以同一个 Docker Adapter 执行四方法获准的调用。生产 standalone 的精确快照规则保持原样。

建议分两批：

| 批次 | 范围 | 可以声称什么 |
|---|---|---|
| C1：严格输入与研究 replay 的最小闭环 | source/target/map/review/replay 严格模型，独立重建，工具自有 Git/Docker fixture，旧生产拒绝路径回归 | 研究桥接工程可行，不能声称外部样本或实验成功 |
| C2：研究协议与训练适配 | 其余 protocol/split/fit/evaluation 模型、特征/context 规格、词汇对账、四方法及指标编排 | 数据、规格和准入逐项通过后才可冻结拟合/评测 |

本次请求确认 **C1**。工程初估 2–4 人日；C2 另估 2–5 人日，取决于特征与数据问题，均不是日历承诺。
不先实现一整套评测器，不因投入过工程成本而承诺接纳 colored。

## 8 个映射的语义边界

来源 2 条断言展开的全部 8 case 必须保留；每条均保持 ValueError 与消息字面量子串要求。
仅作 `color → fore_rgb`、`on_color → back_rgb`；text 与整个 RGB 元组逐值原样传入。
`force_color=True` 是来源控制参数，显式记录为 source-only，不能转发给目标或 print。
不在 Adapter 解包 RGB，不截断/补齐，不先校验/夹紧，不捕获或改写目标异常。

4 个三通道越界输入有明确的上游夹紧测试依据；4 个长度错误虽然能进入目标内部，
但没有找到固定上游关于它们应有异常类别/消息的独立规范测试。
不能由“内部解包会报 ValueError”的源码推断，直接得到规范要求或 8 个合法反例。
后 4 个仍保存为 `outside_explicit_rgb_arity_contract` 的待审观察，不能删除或偷偷加进合法反例计数。
applicability 的研究单位仍是 `(Guard, target)`，不是按 8 个参数产生 8 个独立样本；最终如何裁决整行须人审。

自有合规见证必须与来源 Guard 分开：

- 三通道输入建议以**目标 cprint 的 stdout 字面量**确认实际夹紧值，不能只检查返回 None/没有异常。
  Observer 可用标准库 StringIO/redirect_stdout 收集输出，不改调用参数、不吞异常、不 monkeypatch 目标。
  这需要独立、封闭的 `stdout_eq` 见证 grammar；不会加入来源 contract.v5 或修改原 Guard oracle。
- 样式/TTY/environment 前提必须记录、验证；禁止加载上游 autouse conftest，也不透传宿主 FORCE_COLOR 等变量。
  未确认输出前提或见证格式未验收，own-contract compliance 保持 unknown，不当作通过。
- 长度错误可以保存 raw observation；没有规范裁决时不把预测异常文字写成已审核金标准。

`stdout_eq` 见证也仅在 C1 自有 fixture 验收；外部见证内容和 colored 实跑仍需单独批准。

## Module 的 Interface 与放置位置

外部 Interface 保持三项：`audit(spec) -> Admission`、`replay(spec, method, output) -> Result`、
`verify(result) -> RebuiltFacts`。调用者不能传入一个裸 `applicable=True` 或自造测试 Python 获得执行。
输入事实和策略交由这个 Module 核对，四方法调用同一个 replay 实现。

- `src/counterguard/study_models.py`：所有研究输入 extra=forbid、预算、ID/路径/版本与角色约束。
- `study_data.py`：从真实 Git 和现有 Evidence/Guard 验证器独立重建 source/target/map/review。
- `study_replay.py`：唯一研究执行路径、Scope 决策核验、运行前后重新授权、结果重建。
- `study_test.py`：可信字面量映射渲染器和独立 stdout 见证渲染器，不接受 Python 表达式。
- `scripts/run_scope_study.py`：薄入口；原 inventory 保持原语义。新入口只串联已验收的正式 Interface。

Production snapshot replay 与 research replay 使用不同的授权 Adapter；共同复用已有
`_AdmittedDockerProcess`、DockerPolicyV1、最小挂载/runner transport/JUnit 校验，不复制 shell 命令或提供本地 fallback。
transport 只是执行 seam，不能接受一份研究 JSON 就默认已授权。

## 拟议 C1 数据契约

这些名字在确认后才成为实施规格；当前不存在可执行的对应 Schema。

| 模型 | 最小必需内容 | 必须重建的事实 |
|---|---|---|
| `study-source.v1` | source_id；来源仓库/真实 B/F/H；H 内契约；当前 Evidence/Guard 引用、字节/自摘要；最小 case IDs | 完整来源、真实日志、失败集、Guard 自检；不是只认引用自摘要 |
| `study-target.v1` | target_id；仓库/固定提交/公开与定义入口；完整树与闭包 pins；导出/closure/hook 版本；许可和人工源审引用 | 从完整提交树重建所有角色、初始化器、闭包与 finding；unknown 无 override |
| `study-call-map.v1` | map_id；source/target digests；逐 case 映射；source-only 控制清单；原 assertion/oracle digest；字面量生成器版本 | 映射与来源最小 case 集完全一致，前景/背景和值及 oracle 逐一核对；无新增/丢失断言 |
| `study-review.v1` | review_id；精确 source/target/map/见证/代码/runner/policy digests；用途、操作者、实际时间、原因；先前事件 digest | 可信本机操作者的独立研究审核，不能把 proposal 的自摘要或 Git 所有权当执行授权 |
| `study-replay-plan.v1` | 研究用途；方法；来源与目标；review；结果引用；决定/trace 与 Scope/fit 依据；固定限额 | B1 恒适用、B2 唯一接口等值、learned 来自匹配 fit；调用者不能伪造决定 |
| `docker-execution-authorization.v6` | 独立 research purpose；source H 与 target revision 分列；逐文件来源角色；新 request/test/map/review/Scope/code pins；精确 image/policy | 每次从上述事实重新授权；旧授权不吞新字段，不降级到生产 replay |
| `study-replay.v1` | 准入/Scope/执行/判定分别记录；run 或 null；原始日志/授权/映射/见证引用；方法与来源链 | 从实际 request、输入和 JUnit 重建，不把 setup/import/timeout 当违规 |

来源合同是 H blob，只能作为 source-contract 数据挂载；它的 target 字段不能被重写成 colored。
新生成的研究测试单独绑定源 Guard/test/oracle digest 和获审映射，目标文件来自 target 提交。
来源断言数据、目标源码、工具生成测试采用显式不同来源角色，不能混成一个 Git 树或假造目标 H。

source Guard 可以维持 Candidate；研究用途须有单独 review，不能借此让 Candidate 在生产 Registry 可调度，
也不自动做 Shadow/Active 转换。本机审核文本/事件不是身份签名；若主机、验证器和可信审核记录同时被控制，
摘要不能提供保护。该信任假设须在结果中保留。

## 授权顺序与失败语义

1. 严格读取输入，校验路径/字节/预算/版本；完整 source chain 与 target Git 独立重建。
2. 核对源审和映射审核、精确 runner catalog/收据/镜像与 policy、当前全包实现和路径长度。
3. 核对协议/方法依据，计算实际 Scope 决定。共同安全准入失败时保存 unknown/具体原因；不因 B1 放行。
4. inapplicable 或 unknown：`run=null`、真实进程启动 0 次，二者原因分开，不能显示 pass。
5. applicable：写新工作区的最小目标闭包、H 原始契约、可信测试和逐次授权；只用 Docker。
6. 运行后重新核验全部 pin/状态及 JUnit；中途变化保留实际 Run 并记 stale，不回填成未启动或通过。

源码在收集阶段导入，须在 raises oracle 之外；字面量解码/映射在运输前完成验证，不能把 Adapter 错误当目标 ValueError。
返回不支持/异常时结果文件先保留；重复 ID 不覆盖。错误码沿既定研究口径：参数 2、执行故障 3、准入不足 4、完整性 5；
verify 的 0 仅表示事实可重建，不能把研究负结果改成正结论。

## C1 必须通过的专项

- 工具自有两个独立 Git 历史：source B/F/H + 不要求 B/F/H 的 target，证明不同 import 根仍可完整绑定。
- 真 Docker 的映射字面量、原消息 oracle、stdout 见证与最小失败 case；目标不得在宿主 import。
- 篡改/重签 source、target/export/hook/闭包、map 值/角色/断言/消息、review、代码/runner/policy、Scope 或执行结果时拒绝。
- target 在 import 时抛 ValueError 仍是 collection/import failure，不能被 raises oracle 吃掉。
- stdout 见证的 Observer 出错属于基础设施，不作为目标契约满足；没有见证结果不能自动标 contract_compliant。
- unknown/inapplicable 的真实启动次数为 0、run=null；未知不能伪装成不适用或 pass。
- 生产跨仓库仍 unknown；新授权不能送进旧 parser，旧授权不能冒充研究目的；Candidate 生产调度规则不变。
- 全部新进程测试标 slow/Docker，路径含原子临时文件满足既有 240 UTF-16 单元预算；20 次乱序语义稳定。
- 不读 holdout；真实 source/target 不因 fixture 通过就自动获准。

仅跑 `uv run pytest -m "not slow" -q`、新专项及 Ruff，不跑全量。

## 数据与结论仍有的缺口

colored 的 577 个、termcolor F 的 233 个可达提交没有共享 commit ID，当前/root 文档和相关 RGB 实现未找到衍生声明或复制依据。
这不证明不存在借用，不能用不同根提交/作者/许可证当独立性证明。最终分组依据仍需维护者审核。

返回字符串的 termcolor.colored 与写 stdout 的 colored.cprint 不完全相同。
`interface_kind` 的定义必须先冻结，不能为了让 B2 误用目标而硬标相同；如果基线本来能排除它，照实接受零收益。
当前 ast-features.v1 拒绝 termcolor 主函数的 For，范围 helper 的 GeneratorExp 也不支持。
不能跳过函数体、制造空特征或把“夹紧/应拒绝”标签编成 token；新提取器和 context 属于 C2，先规格再对账。

只有 1 个已验证来源和 1 个已知比较候选，不足以独立填满 initial / refinement / holdout。
8 个 case 或 B/F 快照不增加独立场景数；初始无反例则 learner 按原规则拒绝，不能改成默认全适用来制造精化前后对比。
这批材料均已被执行者阅读，标 known exposure，不能当盲测。

## 重算与此次不做

本次只读 auditor 位于 scripts，单独绑定脚本摘要，不改 counterguard 包源码，因此不引入新的全包过期。
确认 C1 后会新增包源码并改变全包 implementation_digests；先让 fixture 与拒绝路径通过，再用新 ID 物化真实来源链。
原 termcolor contract.v5/H 若内容不变可以复用，但旧捕获不能重签为当前实现；目标也不补造 H。
v1 数据、旧 artifact、已有 schema、发布标签保持原样；不新增运行时依赖。

不做 legacy/插件/依赖安装、参数展开、任意 oracle/Python 模板、自动标签、lazy/ICE/shrinking/变异造数据，
不直接运行 colored，不创建新 fork/H，不启用生产跨仓库调度，不解封 holdout，不预定研究成功。
