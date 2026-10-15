# 攻击面排查清单

基线：2026-10-15，D13 修复提交 `14c9586`。本清单记录实际检查及缺口，不是穷尽性安全认证。D14 的安装验收另见 [发布验收](progress/day14.md)。

## 四类缺口是怎样发现的

采用的是**沿信任边界检查声明与原始事实是否一致，再用受控篡改证伪**的方法，而非随机发现四个错误后停止：

1. 沿 Capture → Evidence → Guard → Scope → Replay → Evaluation / Gate / Pipeline，列出各公开入口声称验证的事实，以及事实来源：契约/源码、原始 stdout/stderr/JUnit、冻结协议和训练成员。
2. 比较独立 `verify_evidence`、`verify_guard`、`verify_replay` 与外层审核。外层已经重建某项事实，不代表独立入口也检查了它；摘要一致也不代表声明真实。
3. 只在临时副本修改一个声明，重新计算该 JSON 的自摘要，保留原始日志或源码不变，再调用公开验证器。这样能区分“发现摘要不匹配”和“真正发现事实矛盾”。
4. 对诊断边界，用缺失文件的真实 CLI 调用及模拟外部进程启动异常检查输出；只使用合成凭据，分别核对公开摘要和私有原日志。
5. 先观察失败回归，再修实现，最后跑专项和全量；保留原始历史产物。具体复现和 D13 执行结果见 [D13 记录](progress/day13.md)、[回归矩阵](d13-audit-matrix.md)。

这是一轮针对来源一致性和失败语义的定向审计。没有完成全仓模糊测试、渗透测试、形式证明或对恶意 OS/并发文件系统的审计；**未发现问题不能解释成没有问题**。

## 状态与信任假设

“已测”仅指表中具体行为有回归或实际记录；“部分”表示存在保护但覆盖不完整；“未测/未实现”不得借用其他行的测试宣称安全。D13 的执行证据是 552 项全量；本清单新增本身没有产生新的攻击实测。

当前信任本机执行器、解释器、工作区权限和自己准备的目标代码。假设攻击者能修改被校验的记录副本，但不能同时控制可信来源、所有原始日志、验证器及其运行环境。摘要不提供签名或身份认证。直接 `guard run` 是显式目标的 smoke run，不能代替完整来源审核或 Scope 决策。

| ID / 状态 | 边界与已排查行为 | 证据 | 未覆盖的范围 |
|---|---|---|---|
| A01 已测，D13 类 1 | Evidence 重签失败 case 集、契约身份或目标模块，原始 JUnit/源码不变时拒绝 | [test_integrity.py](../tests/unit/test_integrity.py) | 同时伪造全部来源；OS 执行真实性、主机和时间认证 |
| A02 已测，D13 类 2 | Guard 自检结构化 case 元数据必须与原始 JUnit 一致 | [test_integrity.py](../tests/unit/test_integrity.py) | 任意 Guard 模板/用户 oracle 的正确性；直接运行不等于完整 verify |
| A03 已测，D13 类 3 | 独立 Replay 重签执行结果、known/unknown trace、Guard/Scope/protocol/契约/目标身份时拒绝 | [test_full_mvp.py](../tests/e2e/test_full_mvp.py) | 对任意新特征/契约的泛化；并发替换文件的原子快照保证 |
| A04 部分，D13 类 4 | CLI 自产错误的绝对路径和显式凭据赋值被隐藏；启动摘要仅含异常类型，原 stderr 保留 | [test_failure_semantics.py](../tests/unit/test_failure_semantics.py)、[diagnostics.py](../src/evidenceguard/diagnostics.py) | Typer 自身参数错误、无上下文秘密、原日志/argv/业务数据、通用公开导出脱敏 |
| A05 已测 | pytest 1 与 2/3/4/5、收集/import/skip、缺失/歧义 case、timeout/launch 分开；unknown/inapplicable 不启动 pytest | [test_execution.py](../tests/unit/test_execution.py)、[test_replay.py](../tests/integration/test_replay.py)、[真实 unknown](results/day13/unknown-report.json) | 恶意进程自报 JUnit、任意子孙进程清理、资源耗尽 |
| A06 已测 | holdout 污染 train、修改标签或重签 split 被拒；learner 只收 FeatureVector，20 次乱序稳定 | [test_holdout_isolation.py](../tests/integration/test_holdout_isolation.py)、[test_scope.py](../tests/unit/test_scope.py) | 人工标签语义真伪、全局最小性、未见仓库表现 |
| A07 部分 | ArtifactRef 拒绝绝对路径、盘符、反斜杠和 `..`；引用 resolve 后检查工作区边界；路径预算含临时文件 | [test_models.py](../tests/unit/test_models.py)、[test_path_limits.py](../tests/unit/test_path_limits.py)、[protocol.py](../src/evidenceguard/protocol.py) | 未做完整恶意 junction/reparse/hardlink、TOCTOU、ADS/保留名/大小写/Unicode 攻击矩阵；代码检查不等于这些攻击实测 |
| A08 部分 | 同 ID 不同内容拒绝覆盖；完成/部分目录不自动重建；实际时间、代码和环境 pin 保留 | [test_mvp_flow.py](../tests/e2e/test_mvp_flow.py)、[test_demo.py](../tests/e2e/test_demo.py)、[artifacts.py](../src/evidenceguard/artifacts.py) | 恶意外部写者、权限提升、断电/并发写的完整故障矩阵、签名/撤销/防回滚 |
| A09 部分 | 受控 argv、无 shell、环境 allowlist、空 pytest 配置、禁 conftest 与插件自动发现 | [test_execution.py](../tests/unit/test_execution.py)、[执行策略](pytest-execution-policy.md) | 目标 Python 本身可读写宿主、访问网络；插件隔离不是沙箱 |
| A10 部分 | 声明式候选只引用可信契约 case，非法 Python/空候选拒绝；AgentContext 不含 fixed/标签/环境 | [test_independent_verifier.py](../tests/unit/test_independent_verifier.py)、[test_verification_gate.py](../tests/integration/test_verification_gate.py) | 实时模型、提示注入、任意生成代码、新 oracle 的正确性 |
| A11 部分 | 严格 Schema、JSON 子集、摘要、三格式同源及既有 Markdown 转义案例 | [test_cli_contract.py](../tests/unit/test_cli_contract.py)、[test_demo.py](../tests/e2e/test_demo.py) | 巨量/深层 JSON、恶意 XML 的拒绝服务预算、终端控制字符及全面输出注入检查 |
| W01 未实现 | 不可信目标的文件、网络、CPU/内存/PID、子孙进程隔离 | W3-B 待验收 | 当前禁止把未知仓库交给 LocalTrustedExecutor；Docker 不可用不降级执行 |
| W02 未实现 | Git base/head、浅克隆、diff 路径、子模块、Git 配置和仓库链接边界 | W3-A 待实现 | 影响范围不明必须 unknown；不得隐式执行 hooks、过滤器或仓库安装脚本 |
| W03 未实现 | 真实项目声明配置、插件、conftest、依赖安装/build hooks | W3-A/B 待实现 | 仓库配置与安装过程也是代码；全部进入受限执行边界，不能只隔离测试函数 |
| W04 未实现 | Registry 权限/状态、CI 凭据/上传、公开报告、供应链和多平台矩阵 | W3-C / W4 待实现 | 本地 hash 不能替代发布签名；本机 wheel 成功不等于跨平台或 CI 安全 |

## W3 开工与准入

W01–W04 是未关闭事项，不因 D14 MVP 验收通过而关闭。W3 开始时，把每项拆成 `docs/security-model.md` 中的可信资产、攻击者能力、实现责任模块、攻击 fixture、预期拒绝和实测记录；新发现的边界追加 ID，不把“未测”改成空白。

在首次运行未知仓库前，W3-A/B 至少必须证明：仓库引用不会越过允许的挂载边界；缺失 base/head/不明 diff 返回 unknown；恶意目标不能访问宿主私有文件/网络或写只读挂载；资源及日志上限生效；超时后子孙进程不能遗留；未声明插件/fixture 明确失败；依赖安装不在宿主执行。每项要有可重复命令、失败时证据和实现版本；这些是待完成的准入条件，**当前没有通过记录**。

只有检查点全部通过才允许 W3-D 未知仓库试点；失败时保留诊断并停止该类执行，不用可信本地模式绕过。Registry/CI 接入前再关闭 W04 对应项。此流程不改变 scope_v1 的标签、指标或历史验收。

历史“verify 通过”的解释见 [旧验证结论的边界](known-limitations.md#历史验证结论的边界)。

MVP 冻结补充：A09 的依赖缺失预检由 [test_runner_dependency.py](../tests/unit/test_runner_dependency.py) 和 [真实安装验收](progress/mvp-freeze-v1.md) 覆盖；缺 pytest 元数据或模块时，CLI 给出 runner 安装提示、执行器不启动进程。这不关闭 W01 的未知代码隔离缺口。
