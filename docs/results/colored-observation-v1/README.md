# termcolor → colored 固定快照观察

本次完成单独获批的受限外部观察：重建来源 Evidence/最小 Guard，在同一已审核 Docker 镜像中，
对固定 `colored:cprint` 分别重复运行完整来源 Guard 和独立 stdout 见证。
工程链跑通；**不据此给整个 Guard 分配适用性标签，也不声明目标完全合规或跨项目学习收益**。

## 固定输入与实际结果

| 项目 | 固定输入或结果 |
|---|---|
| 来源 | [termcolor owner fork](https://github.com/kokoJesee/termcolor)，公开入口 `termcolor:colored` |
| B / F | `db6b299abfec18223a98827f4cd6a7e475b7dfb5` / `520facb24e5310a6f48736dddfe86164057a322c` |
| H | `fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5`，相对 F 只新增获批契约，未新建 fork/H |
| 契约 | `contracts/termcolor.colored.rgb-range.v2.json`；原始字节与[已批准契约](../static-reexport-v1/termcolor-contract.json)一致 |
| 目标 | [colored](https://gitlab.com/dslackw/colored)，MIT，`f3d799873a7cde62f3c43d74ed6ffc258240d956`，根入口 `colored:cprint` |
| 目标检查 | 50 个完整树文件、12 个闭包文件；原 static-reexport-v2 grammar 与有限钩子审查不变 |
| 镜像 | root-pytest8：`sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16` |
| 运行版本 | 实测 Python 3.13.16 / pytest 8.4.2 |
| 来源捕获 | B 8 failed、F 8 passed，reproduced=true；独立 Evidence 核验通过 |
| 最小 Guard | 保留原 8 个失败 case 和消息 oracle；B 8 failed、F 8 passed 自检及独立 Guard 核验通过 |
| colored 原 Guard | 两次均 test_failed，每次 8 failed；pytest exit=1 |
| 独立 stdout 子集 | 两次均 passed，每次 4 passed；pytest exit=0 |
| 重复性 | 每个 lane 的 admission、逐 case 结果及计数相同；真实 run ID 不同，四份结果分别独立 verify |

实际外部容器恰好 **8 次**：来源捕获 2、自检 2、目标完整 Guard 2、目标 stdout 子集 2。
没有额外外部重跑、宿主目标 import、本地 executor、依赖安装或全局环境更改。
原始执行发生于 2026-10-20，真实 UTC 与 run ID 见[观察回执](observations.json)，没有改写为相同摘要。

## 两类观察分别说明什么

完整 Guard 每次保留 8 个原 case：4 个越界三元组没有抛出来源要求的 ValueError，
另 4 个二/四通道元组抛出了 ValueError，但消息没有匹配来源要求。
这些是**来源 oracle 不匹配**，不等于发现 colored 缺陷。

四个越界三元组的目标夹紧政策有固定上游
[CHANGES](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/CHANGES.md#L14)
及[前景测试](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/tests_pytest/test_colored.py#L42)依据。
背景输出字面量由共同政策和固定调用链推导，经维护者批准后才运行；不能说成上游已有相同的背景输出 golden。
获批的[四条 stdout 字面量](stdout-witness.json)独立执行并通过，但不能替代完整 Guard。

观察器为有界 non-TTY StringIO。未转发 FORCE_COLOR/COLORTERM/NO_COLOR、未加载上游 conftest，
未增加 reset 字节；RGB 路径仍实际生成颜色前缀与换行。
见证的 basis_refs 包含审读过的 `tests_pytest/conftest.py`，**它是固定规范依据 pin，不是容器输入或加载许可**。
完整[调用映射](call-map.json)只将 color/on_color 改名为 fore_rgb/back_rgb，force_color 显式 source-only；
不夹紧、不补参数、不改输入值、不删消息 oracle。

另外四个长度错误输入仍**不确定**：已检查的固定树没有明确异常类型/消息规范，
Python 解包行为不能充当独立规范。没有删除这四个 case，也没有为其编造 stdout 或合规标签。
whole_guard_applicability 与 whole_target_contract_compliance 均为 null。

## 工程资格与复核入口

[新接口](../../external-observations.md)使用封闭 v3/v8 和独立可信审核锚；旧 fixture-only v1/v2/v6/v7 保持原样。
真实外部运行前，快层、严格模型/完整来源专项、CLI 子集和工具自有 Git/Docker 资格项已通过。

```powershell
uv run pytest -m "not slow" -q
uv run pytest tests/unit/test_study_observation_models.py tests/unit/test_study_observation.py -q
uv run pytest tests/unit/test_study_observation.py -q -k observation_does_not_accept_fit_inputs_in_cli
uv run pytest tests/integration/test_study_observation.py -q
uv run ruff check .
uv run python scripts/export_study_observation_schemas.py --check
uv run python scripts/export_study_schemas.py --check
uv run python scripts/export_study_feature_schemas.py --check
uv run python scripts/export_study_fit_schemas.py --check
uv run python scripts/export_study_fitted_schemas.py --check
```

Docker 资格项须将 `COUNTERGUARD_RUNNER_IMAGE_DIGEST` 设为上述精确已审核 ID；未设置会 skip，不能算实测通过。
快层 **1141 passed / 268 deselected**；模型/来源专项 **19 passed**；加强 CLI 子集 **1 passed**；
真实工具自有 Git/Docker 项 **1 passed、无 skip**，运行 8 个工具自有容器，与外部 8 次分别统计。
Ruff、9 个 Python 文件格式、5 份新 Schema 与 24 份既有 Schema 一致性检查通过。
选择存在重叠，不能把数字相加为独立测试总数。没有运行全量或重跑原四项隔离攻击。

首次工具 fixture 在启动前失败：模块级环境哨兵不符合现有根导出 grammar。
仅将工具自有哨兵移入函数，产品准入/oracle 未改；失败记录保留，容器数为 0。
成功资格测试在新目录进行。精确时长、私有 JUnit 摘要、完整实现指纹和保护文件核对见[验收回执](acceptance.json)。

复核固定 Git 字节不需要执行目标：

```powershell
git -C <termcolor-fork> diff --name-only 520facb24e5310a6f48736dddfe86164057a322c fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5
git -C <termcolor-fork> show fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5:contracts/termcolor.colored.rgb-range.v2.json
git -C <colored-clone> show f3d799873a7cde62f3c43d74ed6ffc258240d956:CHANGES.md
git -C <colored-clone> show f3d799873a7cde62f3c43d74ed6ffc258240d956:tests_pytest/test_colored.py
```

新执行须按[来源捕获](../../standalone-capture.md)、[最小 Guard](../../standalone-guards.md)和
[外部观察接口](../../external-observations.md)在新目录重建，并取得匹配当前实现的独立审核锚。
不能复制此页的历史摘要当成执行批准；有完整原始工作区时，使用原 `scripts/run_scope_study.py verify` 独立核验，命令见接口页。
本次包源码在资格测试与真实捕获之间保持一致；当时尚未提交，用基点和逐文件字节 pin 记录，不伪称为历史 commit。

## 数据与公开范围

真实来源修复仍为 **1**；实际外部观察 pair 为 **1**；正式接纳的跨项目研究场景仍为 **0**。
没有研究标签、拟合、initial/refinement/holdout 数据冻结或生产权限变更，不能开始四方法正式评测。
后续仍需整组语义裁决、长度错误规范依据、外部 context/特征逐项对账及足够独立数据。

公开材料只包含实现、测试、必要接口文档、获批映射/见证和有限结果投影。
原始绑定/授权/Run/JUnit 与工作区包含本机执行上下文，保留本地；公开摘要可定位原记录，
**有限投影不能替代完整来源独立 verify**。个人计划、草案、系统诊断与控制脚本不发布。
6655 份既有保护文件和全部发布 tag 未变；新源码使需当前结论的旧链过期，按新 ID 重建，不补签历史。
远程身份/签名/防回滚、谱系无借用证明、并发原子快照及恶意目标干扰 pytest/JUnit 仍未覆盖。
