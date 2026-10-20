# 自有 fixture 研究重放验收

实现：[663c891](https://github.com/kokoJesee/CounterGuard/commit/663c8914e748d041ecfd6a174095c424c460899e)。
接口与限制见[研究重放](../../research-replay.md)，记录见 [acceptance.json](acceptance.json)。
本批只验证工程通道：没有执行 colored，没有重新捕获 termcolor，没有生成外部研究标签或新增研究场景。
开发实施方案仅在本地维护；公开材料描述已经实现的行为和实测结果。

## 实际观察

现场创建两个独立的工具自有 Git 历史：source 有 B/F/H 与 H 内契约，target 只有固定提交。
source 使用根包布局，target 使用 src 布局；不复制来源到另一个仓库冒充独立谱系。

| 检查 | 实测 |
|---|---|
| 来源捕获 | B 退出 1、F 退出 0，reproduced=true |
| 最小 Guard | 来源共 2 case，仅保留实际失败的 1 case；双向自检通过 |
| b1 研究重放 | 两次均为 test_failed，逐 case 计数相同；这是原 oracle 的观察，不自动生成回归标签 |
| 独立 stdout 见证 | passed；不改来源 oracle，不产生 contract_compliant 标签 |
| b2 fixture 接口过滤 | inapplicable、run=null、启动 0 次 |
| 两种 learned 方法 | unknown、run=null、启动 0 次；fit 尚未实现 |
| 导入时抛 ValueError | infrastructure_error，未被 raises oracle 吃掉 |
| stdout Observer 失效 | infrastructure_error，未伪装成见证通过 |
| Registry | 来源保持 Candidate，生产不可调度 |

完整摘要见 [docker-summary.json](docker-summary.json)。最终专项共 9 次容器运行：来源捕获/自检 4 次、
研究目标观察 5 次。第一轮在后续攻击前因新测试读取 Registry 字段错误中止，已有 7 次自有容器运行；
修正的是测试字段，不是运行标准。两轮合计 16 次自有容器运行，外部目标为 0。
旧生产 Scope 和授权 parser 未扩张；定向测试用 JSON 解析模式核对旧 parser 因 schema_version 拒绝 v6。

## 验证命令

| 命令 | 结果 | JUnit 秒 |
|---|---|---:|
| `uv run pytest -m "not slow" -q` | 1025 passed，244 deselected | 167.999 |
| `uv run pytest -q tests/unit/test_study_replay.py` | 28 passed，无 skip | 133.741 |
| `uv run pytest -q tests/integration/test_study_bridge.py` | 1 passed，无 skip | 237.287 |
| `uv run pytest -q tests/unit/test_study_models.py` | 最终 20 passed，无 skip | 见 acceptance |
| `uv run pytest -q tests/unit/test_study_replay.py -k source_and_target_keep_distinct` | 最终定向 1 passed，27 deselected | 见 acceptance |
| `uv run ruff check .` | exit 0 | — |
| `uv run python scripts/export_study_schemas.py --check` | 9 个新 Schema 与模型一致 | — |

三组主验证并行执行，耗时仅记录这次验收，不作性能比较。运行另用了全新短临时目录和私有 JUnit 输出。
真实 Docker 专项要求 `COUNTERGUARD_RUNNER_IMAGE_DIGEST` 为 runner list 核验后的精确 root-pytest8 image ID；
未提供该条件时会 skip，不能据此声称专项通过。本次实测没有 skip。

完成快速层后增加了深层 JSON 的纯测试，并把旧 parser 的定向断言改为实际 JSON 模式；
两者均已定向通过。没有把附加结果伪装成另一次快速层或全量运行。
深层 JSON 检查没有复现推测的递归异常；保留回归，不声称覆盖任意嵌套深度或全部拒绝服务攻击。
新进程测试标 slow/docker，完整来源链 transport-double 测试也在 slow 层。**未运行全量**。

真实 CLI 另验证了 audit 退出 0、verify 退出 0、unknown replay 退出 4；
最后一项没有运行记录，也没有新增容器启动。见 [cli-summary.json](cli-summary.json)。

## 不变量与未覆盖范围

所有既有冻结/历史文件逐字节保留，发布标签未移动，原有无关文档移动未纳入提交。
新 strict models/授权/生成器使用新名称和版本，生产 snapshot Scope 与 Candidate 权限不变，没有新运行时依赖。
本批新增包源码使旧来源链按原规则过期；需要当前实现的真实来源结论时，必须重新以新 ID 物化，不能重签旧产物。

审核摘要由调用方独立保留，本机审核不是身份签名，也没有自动最新 tip 或密码学防回滚。
未复跑原四项隔离攻击；共享 Docker transport、policy 和镜像未改动，本批攻击覆盖仅限表列行为。
不证明恶意目标不能干扰 pytest/JUnit，也不替代内核/daemon、多平台、全部文件系统或资源攻击审计。

自有 fixture 不计入真实样本，不能证明外部谱系独立性或精化效果。
colored 的可比性裁决、外部执行、新特征/context/fit、正式 split/protocol 和独立留出数据仍未完成。
没有用假特征、自动标签、修改冻结标准或放宽生产 Scope 填补这些缺口。
