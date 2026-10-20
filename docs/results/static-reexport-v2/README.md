# 静态多导出与有限类钩子验收

实现版本：[30746ee](https://github.com/kokoJesee/CounterGuard/commit/30746ee9ab090e5c25729fa9f502a3e1a481f4e3)。
范围按维护者批准的 [colored 提案](../../experiments/scope-v2/colored-minimal-support-proposal.md)，
精确语法、拒绝码、版本盘点与重新物化规则见[规格](../../static-reexports-v2.md)。

本轮完成的是工程支持。colored 从旧算法的 unknown 进入新算法的 **review_required**，
没有执行 colored、创建它的 fork/H、生成标签或计入研究样本。新增合格研究样本仍为 **0**。

## 实测

| 选择命令 | 结果 | JUnit 时间 |
|---|---|---:|
| `uv run pytest -m "not slow" -q` | 976 passed，215 deselected，无失败/skip | 111.385 秒 |
| `uv run pytest -q tests/integration/test_bootstrap_binding.py tests/integration/test_bootstrap_plan.py` | 3 passed，无失败/skip | 19.709 秒 |
| `uv run pytest -q tests/integration/test_standalone_capture.py -k static-reexport-v2` | 1 passed，5 deselected，无失败/skip | 83.151 秒 |
| `uv run ruff check .` | exit 0 | — |

本机运行另指定了全新临时目录和 JUnit 输出目录；没有跑全量。新增真实进程分支继承 slow/docker 标记。
最初受限模式的静态专项因 pytest 临时目录访问权限失败，原日志和 JUnit 保留在私有审计目录；
改用正常权限后完成专项和上述最终快速层，不将环境错误解释为候选不兼容。
中间专项经过后续源码变更，其早期通过数不替代本表最终验收。

Docker 专项只执行工具自有 src 包：根包多导出、版本字面量、定义模块相对导入、一个有限元类钩子及独立异常文件。
B/F/H 各保留 4 个闭包文件和 1 条钩子观察。B 两 case 中失败 1 个，F 两 case 全通过；
最小 Guard 仅保留失败的消息断言，B/F 自检及独立 verify 通过。Registry entry.v4 登记幂等，Candidate 不可调度。
测试禁止目标包在宿主 import，也禁止本地执行器回退。见[真实摘要](docker-summary.json)。
没有重跑原四项 Docker 攻击；runner image 与封闭 policy 均未变，不能把本轮专项当作新镜像或全面隔离认证。

## colored 静态回执

固定仓库 `https://gitlab.com/dslackw/colored.git`，提交 `f3d799873a7cde62f3c43d74ed6ffc258240d956`。
公开调用仍为 `colored:cprint`，定义为 `colored.cprint:cprint`，没有复制/包装目标来绕开根包初始化。

- 完整提交树 50 文件；候选运行闭包 12 文件。
- 3 个钩子分别是 MetaStyle / MetaBack / MetaFore 的 `__getattr__`，均识别为有限 raise，绑定本模块与异常模块摘要。
- 两个全新输出目录的完整回执逐字节一致，自摘要为 `sha256:bd7f70880b66fd2f2a7e1babb516fb0d7f7c9d0bea8acce95f851dca47d0782a`。
- 默认 v1 根导出仍拒绝 `export_root_statement_unsupported`，closure.v1 仍有 3 个模块钩子 finding、状态 unknown；严格全仓检查仍 blocked。
- 新结果只有静态 review_required / not_run；execution_allowed=false，没有来源 B/F/H、契约、oracle、标签或执行授权。

见[完整回执](colored-target.json)与[旧版本对照](profile-comparison.json)。在全新输出路径复跑：

```powershell
counterguard bootstrap inspect-target --repo <colored-clone> --revision f3d799873a7cde62f3c43d74ed6ffc258240d956 --target colored:cprint --import-root . --profile static-reexport-v2 --output <new-directory>
```

尖括号替换为实际路径。仓库可用 `git clone --no-checkout` 获取，禁止在宿主 import；CLI 预期退出 4，
表示尚需审核。回执不得当作 source contract 或绑定交给 capture。

## 来源、不变量与剩余门槛

[acceptance.json](acceptance.json)记录实现逐文件摘要、选中测试和原始私有证据摘要、报告文件字节摘要及不变量。
263 个既有受保护文件逐字节未改，包含 benchmarks/experiments/examples、历史 artifact/结果和旧 Schema；
v0.1.0/v0.5.0 未移动。原 termcolor 8 case、字面量消息 oracle、原所有者 H 与旧运行记录未覆盖。
全包源码变化仍使旧源码绑定按规则过期；消费当前实现时须在单独获批后，以新 ID 重建 binding → capture → Guard → Registry。
不是给旧验收补签，也不需要在原契约未变时伪造新 H。

新 v6 保留字面量 oracle，所以继续使用 capture.v2、evidence.v4、Guard v4、Registry entry v4。
独立审核递归重建 v6/v4 的源契约和绑定，新 schema 没有降级成旧模型后丢字段；旧模型拒绝新算法字段。
静态否定测试还覆盖模块/条件/别名钩子、异常构造副作用、未知装饰器、动态默认值、版本/导出/闭包重签与 20 次乱序。

下一步是独立研究调用映射和授权桥接的设计，不能直接用生产 snapshot Scope 换仓库。
桥接前仍须逐项审核完整包初始化、类体、环境读取、Windows/ctypes 分支及任意动态改写影响；
本轮机器规则不证明这些效果安全。来源 oracle 的 8 case 不能删改或拦截目标异常来制造结果；
force_color 只属于来源控制，不转给 cprint/print 的 kwargs。
未通过研究语义审核前不分配适用标签，不宣称具备足够独立谱系或留出 true_bug 来支持泛化结论。

本次 Docker Engine 一度不可用，修复的是两个旧 socket 所在的运行目录，保留同父目录备份；
没有手工改持久设置、删除镜像/卷或读取凭据内容。Engine 恢复为 29.4.1 后才跑真实专项，
过程和恢复原目录方式见[Docker 运行说明](../../docker-execution.md)。这不是 CounterGuard 源码缺陷或完整 Docker 诊断认证。
