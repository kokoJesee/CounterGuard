# validators fork：MAC 试点执行设计

2026-10-16；用户确认阶段 A 后实施。范围是上游新增测试的 MAC 全部 10 case，
不代表其余 25 个区域标识符 case 已测，也不代表已学习跨仓库作用域。

## 三个提交及来源

- B `e01166b00424be9d7d544d262e0e0873e1f0a999`：真实 buggy。
- F `6ffd8625ee4272dade063653bff615014bdc4734`：真实上游修复及新增测试。
- H `a7565a59962bf9c784cd1c6dc4ad8df0ee0effd5`：fork 中单独一次工具方提交，直接继承 F，
  提交信息为 `NOT upstream: add EvidenceGuard MAC pilot configuration and contracts`。

H 只新增 `evidenceguard.yaml`、`contracts/mac-complete-v2.json` 和
`contracts/provenance.json`。全部上游文件逐字节与 F 比较，不能修改、删除或替换。
manifest 的 file_origins 逐文件记录 upstream/tool、来源提交和内容摘要。
许可为上游 `LICENSE.txt` 的 MIT，原字节摘要也被固定。

fork 为 https://github.com/kokoJesee/validators，上游为
https://github.com/python-validators/validators。H 仅在本地 clone 创建，没有推送。
`artifacts/pilot/validators-fork-v1/owner-head.bundle` 保存包含 H 的历史，摘要被 manifest 固定；
需要恢复原 H 时用 bundle，不能重做一个提交并冒充相同 SHA。

## 契约来自 head，历史源码分别授权

契约必须是 H 的真实 blob。`contract.v2` 从 F 的
`tests/test_complete_values.py` 静态提取：7 组输入乘以 5 种后缀共 35 case，
选择 validate 绑定为 mac_address 的 2 组输入，保留全部 5 种后缀。
AST 展开不执行测试、装饰器、项目元数据或依赖安装。
测试主体不再是已审核形式时拒绝提取；不能用结果倒推和修改 case。

`docker-execution-authorization.v2` 分别记录 assertion_head、target_revision、
phase、role、每个输入 Git blob/内容摘要、请求、实现、镜像和固定隔离策略摘要。

| 用途 | 目标代码 | 契约 | 附加要求 |
|---|---|---|---|
| capture / buggy | B | H | 原样执行全部 10 case |
| capture / fixed | F | H | 原样执行全部 10 case |
| compile / replay role | H | H | 已重验 Evidence；仅实际失败 case；F/H 上游字节相同 |
| replay | H | H | Registry 未禁用、来源完整、精确 Scope 匹配 |

执行前后均重建授权；重新计算 JSON 自摘要不能替代原始来源审核。
旧 v1 replay 授权继续只接收 project-config.v1 和同 head 输入。
Inspection 的 execution_allowed 仍恒为 false；配置没有打开执行的布尔开关。
捕获有独立准入，不要求先存在尚待捕获生成的 Guard；普通重放仍要求先有真实 Guard。

## 调用、oracle 与导入

`project-config.v2` 用 import_root=src 声明唯一模块映射。
只允许 . / src 两种导入根，不允许绝对路径、任意搜索路径或任意模块别名。
本试点只装载已固定的完整 validators 包闭包，保持公开函数的 @validator 行为。
所有声明逐项与提交对象比较。audit_refs 记录配置、契约来源测试和 provenance；
它们不被伪称为运行时依赖，也不进入 ignored_paths。本试点 ignored_paths=[]。

`guard-test.v3` 调用 target(*positional_args)，不绕过装饰器。
两个 oracle 分别为 result is True 和 isinstance(result, validators.utils.ValidationError)。
返回异常对象不是抛出异常；False、None、1、相同名字的其他类均不能替代原断言。
不支持任意 oracle Python、eval、任意类型导入或用户插件。

新镜像使用 pytest9.0.3；宿主 runner/dev 依赖范围不变。
仍使用空 pytest 配置、--noconftest 和禁插件自动发现，不加载上游 addopts/doctest 配置。
新的容器请求 v2 只增加受限 import_root；响应和 Docker 隔离参数不变。
不得安装可选 crypto extras 来凑通过；其需求与未测范围必须明确报告。

## Scope、报告与验收

`pilot-scope.v1` 的 basis 是 audited_exact_snapshot：绑定 H、MAC 源码、完整运行闭包、
契约、Guard 和 manifest。它不是 scope_v1 的学习结果，没有构造新的人工训练标签。
旧业务 Guard 没有 validators 的语义审核，保持 unknown / disabled 且 run=null。

双向 Evidence 通过须是 buggy exit=1 且真实失败，fixed exit=0 且 10 case 全通过；
导入/收集/启动错误不能充当缺陷证据。`evidence.v3` 保存两次原始日志及独立授权。
`guard.v2` 只包含该 Evidence 的实际失败 case，并在 H 自检通过后才登记。
Registry 使用新的 registry-entry.v2，事实来源仍为不可变 JSON，SQLite 仍仅为索引。

H 的两次重放使用独立 run ID 和新报告目录。比较前独立重验 Registry、Scope、授权、
原始 JUnit 与逐 Guard 决策，并重算计数；不能拿同一次运行当成两次，不能把 skip 当 pass。
时间和运行 ID 保留实际值，投影比较只剔除这些非计数信息，不伪造固定时间。

失败在新输出目录写 pilot-failure.v2，next_stage_allowed=false；已产生的日志保留。
没有 LocalTrustedExecutor 回退。若增加插件、安装要求或其他装饰器语义需求，
超出本次已审核范围，停止执行并另行设计。

## 版本与重算

新契约、生成器、Evidence、Guard、授权和 Scope 使用新版本；本次全部产物写新命名空间。
benchmark、examples、scope_v1 experiment/split/context、旧 artifact 与 v0.1.0 tag 不变。
新增包源码会使旧 Inspection 的当前实现绑定过期，这是预期行为，不能给旧报告补签。
未来修改契约/源码/镜像/运行授权/生成器，必须新建 manifest 与产物版本并重新捕获；
没有重新计算、实测的产物不视作当前实现的执行凭据。

当前安全限制继续适用：信任主机、Docker daemon/内核和工具方实现；
未解决恶意目标干扰 pytest/JUnit、上游身份签名、CI 身份授权、跨平台和任意动态依赖证明。

## 首轮更正与重捕获

首轮 manifest-v3 / validators-fork-v1 完成 B/F 捕获，但验证器错误地把 RunRecord.cwd="."
相对于工具进程解析，因此在独立验证阶段停止，没有发布 Guard。
首轮两次原始运行和失败报告保留；该实现的完整源码归档在
validators-fork-v1/implementation-v2，版本为
sha256:8d84eb4b2b4a64d3d78b25541c0a70b4d8b6737d6104fadc69ec9339fb6b36c6。

更正后用 manifest-v4 / validators-fork-v2 / evd_validators_mac_complete_v2 重新验收。
manifest 显式链接前驱摘要与重捕获原因；H 与三份工具方文件完全不变，没有再次创建 owner 提交。
相对目录、独立重放 ID、Scope 重签以及 manifest 路径重定向均有进程内回归。

第二轮完成两次捕获和 H 自检，但因来源链逐 blob 启动 Git 的重复开销，在完整验收前显式停止。
未把它记录为执行试点通过；源码归档版本为
sha256:286fc27abd2b7299bea9b75f14fec66a1b57ce2057e2951c99a1103599910c90。

批读取通过 Git 原边界专项和二进制/空对象/预算/篡改专项后，最终采用
manifest-v5 / validators-fork-v3 / evd_validators_mac_complete_v3。
每次先检查全部对象大小，批读后逐个验证对象 SHA-1 与原文件 pins 的 SHA-256；
不缓存跨复核结果，不修改限额或减少前后审核。最终核心实现版本为
sha256:e533064d5c2ee7ffd47bfb9262063f2288a31e12c409e3e317ab7f5202816f66。
