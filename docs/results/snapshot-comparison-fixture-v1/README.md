# 自有独立快照比较验收

2026-10-21 验收[独立比较接口](../../snapshot-comparisons.md)：当前用途仅为工具自有 fixture。外部执行为 0，未创建真实仓库的 fork/H，未分配研究标签、训练或冻结协议；正式跨项目研究场景仍为 0。回执中的 fork/H 限制同样指真实仓库；测试自己的 B/F/H 另计。

## 本轮实际验证

源自有 B/F/H 仍包含完整 4-case 原测试，捕获 B=2 fail/2 pass、F=4 pass；最小 Guard 恰好保留 2 个失败 case，双向自检 B=2 fail、F=2 pass。另建独立目标仓库，固定其自身异常消息政策。整个目标包及数据原样挂载，来源 H 契约字节不变，来源包和目标 conftest/pytest 配置不进入目标挂载。

| 操作 | 决定 / 实际观察 | 容器数 |
|---|---|---:|
| 来源捕获与最小自检 | 上述完整原 case / 实际最小子集 | 4 |
| B1 Guard，固定目标重复两次 | 各 2 个真实断言失败，case/结果计数一致 | 2 |
| 独立自身 witness | 同样 2 个输入，按目标政策 2 pass | 1 |
| B2 同接口 | 仅接口相同判 applicable，原 Guard 2 fail | 1 |
| learned initial/refined | 此新快照 profile 未绑定 fit，unknown/run=null | 0 |
| B2 异接口，另一个 stdout 自有目标 | inapplicable/run=null | 0 |
| 错误比较锚 | 执行前拒绝，不建输出 | 0 |
| 实际运行后篡改测试字节 | 保留原 Run/授权/日志，stale/integrity_error，verify 拒绝 | 1 |

合格轮启动次数由 Docker transport spy 实际计为 **9**，不是从预期表反推。宿主目标 import 和 local executor 都有禁止哨兵。unknown/inapplicable 不构造测试、不发现 Docker；实际结果另经原始 JUnit/来源独立 verify。迟到篡改只发生在该新运行目录，其他结果/来源不覆盖。

自身 witness 不替换原 Guard，也不把两种观察转换为标签。B1 与自身观察不同，不等于已发现目标缺陷。旧 profile 的 fit 不借给新快照；没有伪造 learned 规则或把 unknown 改成不适用。

## 命令与实际结果

| 检查 | 最终结果 |
|---|---|
| `uv run pytest -m "not slow" -q` | **1243 passed / 282 deselected**；538.34 秒 |
| `uv run pytest tests/unit/test_snapshot_admission.py tests/unit/test_snapshot_comparison.py -q` | 38 passed；1.25 秒，包含在快速层内 |
| `uv run pytest tests/integration/test_snapshot_comparison_data.py -q` | 1 passed；1.61 秒 |
| `uv run pytest tests/integration/test_snapshot_comparison_docker.py -q` | 1 passed / 无 skip；747.71 秒 |
| `uv run ruff check .` | 通过 |
| 15 个本轮源码/测试/脚本及接口文档的 format check | 通过 |
| 新比较 Schema 与原快照 Schema check | 各 8 份一致，原 Schema 字节不变 |

Docker 项须设置 `COUNTERGUARD_RUNNER_IMAGE_DIGEST` 为 catalog 核验过的 root-pytest8 精确 ID：`sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16`。未设置而 skip 不算实测。

没有运行交付全量。两个 integration 文件均 slow，Docker 另标 docker。快速层与 Docker/真实大快照只读准备曾并行，耗时受并行负载影响，不用它们做性能提升或退化结论；各组重叠，不相加为独立测试总数。真实 Docker 专项约 12 分钟，主要成本包括重复完整来源重建，日常快速层不运行它。

## 保留的前轮与实证修复

先一轮纯逻辑发现比较 help 没写明 fixture 边界，提示补齐后通过；没有改判断标准。第一轮快速层 1242 passed、Docker 全链 1 passed（577.66 秒，9 个自有容器）。

在随后[真实候选只读准备](../snapshot-readiness-v1/README.md)中，TTE 被 `__future__` 的依赖误判阻塞。全包诊断确认它是唯一未允许的标准库编译指令模块；仅修正独立快照分类，补禁止遮蔽测试，并在源/目标真实自有 fixture 加入 future 指令。源码固定后另用新目录运行上述最终轮，没有在执行中改实现，也没有补签第一轮。前后轮 JUnit 与私有记录摘要见 [acceptance.json](acceptance.json)。

原网络、只读、环境、时间、内存/PID 六类 transport 攻击没有在本批重跑，不把本批 9 个容器冒充那组覆盖。运输与固定 policy 未改；其[历史快照实测](../research-snapshot-fixture-v1/README.md)保留原版本边界。本批增加的是新源/目标映射、双锚、跳过、严格类型和运行后输入变化覆盖。

## 仍未关闭

新快照 profile 的 fit/特征来源桥接尚未绑定；外部用途尚未批准或实现，真实 owner H/捕获和正式跨项目数据仍未取得。来源完整性、执行审核和语义裁决分开，不能把本批资格当成真实数据。

远程身份/签名/撤销、防回滚、原子快照、任意插件/安装以及恶意目标干扰容器内 JUnit 均未由本批关闭。W01/W03/W04 总体保持部分。冻结输入、原 artifact、运行时依赖与两个发布标签未改变；个人方案与原有用户文档移动不提交。
