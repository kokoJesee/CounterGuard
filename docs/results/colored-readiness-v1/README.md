# colored 固定快照的只读准入复核

核对实现：`d1bdc7ff840beaad520e5d76112eb3f50aca6afb`。
这是固定 Git 字节、原映射和当前接受范围的复核；没有执行外部 Python、Docker、安装脚本或上游测试，
没有分配研究标签。实现方案、未批准 stdout 字面量和原始日志留在本地。

## 已确认的事实

| 项目 | 实测或证据 | 当前结论 |
|---|---|---|
| 固定目标 | colored `f3d799873a7cde62f3c43d74ed6ffc258240d956`，`colored:cprint`；50 文件完整树、12 文件闭包 | 当前检查仍 review_required；不是执行批准 |
| 只读入口 | 两次 inspect-target 输出字节相同，子进程退出 4 | 不存在靠该回执开启执行的路径 |
| 原映射 | 当前 inspection 下再次核对 8/8 case，退出 4 | 原输入、异常及消息要求保留，未丢弃长度错误 case |
| 来源 H | `fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5` 仅比原 F 新增已批准契约，字节不变 | 不需要新 fork 或改 H 来解决当前代码指纹变化 |
| 历史 Evidence | 当前原验证器拒绝，原因 capture_implementation_is_stale | 历史复现不能冒充当前验证；需要新 ID 重建来源链 |
| 实际定义的语法 | termcolor fixed 为 branch:none；colored cprint 为合法空 token 集 | 仅纯语法诊断；没有为外部代码伪造 fixture-only context、golden 或 FeatureRecord |
| 当前执行用途 | plan/review/authorization 的 purpose 限定 tool_owned_research_fixture_only | 不能把第三方目标改名成工具 fixture，也不能用审核理由绕过 |

机器回执见 [readiness.json](readiness.json)；限定专项 **35 passed**，完整保护/执行计数及检查边界见
[acceptance.json](acceptance.json)。没有跑全量或真实 Docker，35 项不是一次全快层验收。

## 规范与环境结论

固定上游 [CHANGES 夹紧政策](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/CHANGES.md#L14)
与[前景 RGB 测试](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/tests_pytest/test_colored.py#L42)
支持四个三通道越界输入的夹紧行为。背景的精确字节需要沿同一政策和调用链推导，
不能说成上游已有四条相同输出 golden，也不能把手工推导说成运行通过。

[cprint 的 RGB 分支](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/cprint.py#L45)
调用[不经过 enabled 的 RGB 函数](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/colored.py#L263)。
在当前 runner 的封闭环境与 non-TTY StringIO 观察器中，RGB 前缀仍会产生，
styling/reset 则经 attribute/TTY 检查关闭。因此候选见证无需 FORCE_COLOR、COLORTERM、PTY 或加载 conftest，
并且不能凭 reset=True 就给预期输出补上 reset 字节。这里是静态推导，尚未作为外部见证执行。

另外四个二/四通道输入仍**不确定**：检查范围内没有找到明确异常类型与消息政策。
三通道注解及 Python 解包实现不构成规范 oracle。检查了固定树的 README、CHANGES、相关源码和测试，
没有穷尽所有 issue/MR 或未固定文档站；“未找到”不等于上游永无此类说明。
全部 8 个原 Guard case 继续保留；四条候选 stdout 见证不代替整个 Guard，也不自动产生整行合法反例标签。

## 可复核入口

使用本页固定实现、完整 clone 和全新输出目录：

```powershell
counterguard bootstrap inspect-target --repo <colored-clone> --revision f3d799873a7cde62f3c43d74ed6ffc258240d956 --target colored:cprint --import-root . --profile static-reexport-v2 --output <new-inspection-directory>
uv run python scripts/audit_rgb_mapping.py --source-contract docs/results/static-reexport-v1/termcolor-contract.json --worksheet docs/results/bounded-rgb-targets-v1/colored-cprint-proposal.json --target-inspection <new-inspection-directory>/target.json --output <new-mapping-directory>
uv run pytest tests/unit/test_rgb_mapping_audit.py tests/unit/test_study_fitted_models.py -m "not slow" -q
```

两个只读命令预期退出 4，检查输出中的未审核/未执行状态；不是测试失败或已获执行权限。
上游规范可用 `git -C <colored-clone> show <fixed-sha>:<path>` 复查，不在宿主 import 上游代码。

本次只缩小未决问题，没有扩大代码接受范围。真实来源历史闭环仍为 1，正式接纳的跨项目场景仍为 0，
初始/精化/留出数据仍不足；不能因此开始训练或最终评测。现有生产快照 Scope、旧 Schema/产物与标签未改变。

此复核完成后，维护者另行批准受限外部观察的实现与固定 pair 的有界 Docker 运行，
仍须先通过自有 fixture 与新鲜来源准入；本页回执保留其产生时的未批准/未执行状态。
批准不等于执行通过或语义标签，也不允许把现有 fixture-only 用途用于第三方代码。
