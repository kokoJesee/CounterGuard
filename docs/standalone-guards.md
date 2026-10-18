# 从首次 Evidence 到日常 verify

[受限消息断言](literal-message-oracles.md)采用 guard.v4 / Registry entry v4，最小失败集仍保留原 match 与异常类型，两次 Docker 自检和快照 Scope 要求不变。原 guard.v3 与 entry v3 保留。

[受限根包重导出](static-reexports.md)的 contract.v5 同样使用 Guard v4 / entry v4，完整契约摘要包含定义映射，
快照 Scope 包含公开入口及定义模块；旧 Guard 不因工具升级而自动重签或取得新的适用范围。

本页接续[通用 Docker 捕获](standalone-capture.md)。受限独立契约现在可以完成最小 Guard 编译、
B/F 自检、精确快照 Scope、本地登记与 Shadow/Active 验证；不要求先有合法反例，也不伪造学习结果。
它仍只支持 source-only 字面量 profile，不加载上游 pytest 配置、conftest、fixture 或插件，不安装目标依赖。

## 非固定项目的支持边界

**非固定项目的受限闭环已实现。** 模块名、目标函数、字面量 case 与导入闭包不再硬编码为 validators。
满足同一输入规则的新项目，可从真实修复完成 Docker 双向 Evidence、最小 Guard 自检、独立核验、Candidate 登记及人工审核 Shadow。
这不等于任意 Python 项目都已兼容；“通用”指同一受限格式可用于不同项目。

| 环节与实现提交 | 具体成果 | 尚不能据此声明什么 |
|---|---|---|
| plan · `44817d2` | 模块级候选闭包、包初始化、测试投影与上游引导分层，只读且保留 unknown | 计划不是契约或执行授权 |
| bind · `babefe9` | 准备 contract.v3；独立重建 B→F→H、H 内契约、原测试投影和完整来源 | 来源正确不等于缺陷复现；工具不替所有者制造 H |
| capture · `6fb236e` | 已审核 Docker 中执行 B/F，保存原始 JUnit，独立重建 evidence.v4 | 导入/收集错误不算缺陷；unknown 不能用审核理由覆盖 |
| onboard · `fcbf6a8` | Guard v3 最小失败集及 B/F 自检、精确快照 Scope、Registry v3、显式审核与 verify | 首次 Scope 没有学习泛化，也不会自动提升 Shadow/Active |

进入 Docker 前必须同时满足：B/F 线性真实修复、所有者另行提交且只新增契约的 H、受支持的 oracle/调用绑定、
普通根/src 包、兼容 runner 的 Python 声明、零目标运行时依赖，以及各角色运行闭包均为 review_required、没有 unresolved finding。
存在 conftest 本身不否决独立 Guard；它不得进入目标闭包或被当作原生测试引导加载。
缺少 H、闭包仍 unknown 或只有 proposal 时，应停在相应准备环节，不先创建无用的 Registry 状态。

根/src 的全链成功证据来自工具自有真实 Git/Docker fixture；validators 是固定外部缺陷试点。
[boltons 的当前版本复跑](results/boltons-standalone-retrial-v1/README.md)最远生成 contract.v3，
因保守调用分类与缺少 owner H 停在执行前，尚无 Evidence/Shadow，不能作为第二个外部项目接入成功的证明。

## 编译、核验与审核

```powershell
counterguard bootstrap compile --repo <repo> --evidence <capture-directory>/evidence.json --guard-id grd_regression_v1 --review-reason "已核对 oracle、case 独立性及 B/F 精确闭包边界" --output <new-guard-directory>
counterguard bootstrap verify-guard <new-guard-directory>/guard.json --repo <repo>
counterguard registry add <new-guard-directory>/guard.json --cwd . --repo <repo> --root <registry>
counterguard guard transition grd_regression_v1 --to shadow --reason "来源、oracle、快照 Scope 已审核" --root <registry>
```

Evidence 必须在当前源码下独立核验通过且 reproduced=true。编译器只选 `failing_case_ids`，
不能人工加 case、删掉部分失败 case 或复制全契约。新生成测试在原已审核 Docker 镜像中重新运行：
B 的所有保留 case 必须真实失败，F 全通过。收集/导入、超时或其他基础设施错误不算缺陷。
两侧自检、来源和原始 JUnit 全部重建后才发布 `guard.json`；失败保留原日志/记录与 compilation-failure，不发布 Guard。
`verify-guard` 只读重建，不启动容器。

新登记仍为 Candidate，不自动执行。Shadow 违规只记录；明确接受重放结果后，才通过同一个
`guard transition --to active --reason ...` 提升。禁用与 Retired 都是终态；状态事件追加，Guard 本体保持 candidate。
本机审核理由/actor 是审计标签，不是身份认证或远程 CI 凭据。

## 配置与 verify

配置只做声明映射，不提供执行开关，仍采用 JSON 语法。下面是工具自有 `sample.core:price` 示例；
请使用契约中的实际模块/符号/路径，dependency_refs 必须精确列出 runtime_refs 中除目标源码之外的全部路径。

```json
{
  "schema_version": "project-config.v2",
  "project_id": "sample",
  "targets": [{
    "target_id": "price",
    "guard_id": "grd_regression_v1",
    "module": "sample.core",
    "symbol": "price",
    "source_ref": "sample/core.py",
    "import_root": ".",
    "contract_ref": "contracts/price.v1.json",
    "dependency_refs": ["sample/__init__.py"]
  }]
}
```

`src` 布局把 import_root 改为 src，并给 source_ref/dependency_refs 加 src/ 前缀，模块名不变。
不在映射内的改动仍为 unknown；许可的逐文件文档/CI 忽略或 audit_refs 必须显式声明，不能把源码标成忽略。
上游原生测试的环境与受审核独立 Guard 分开处理，不修改旧 strict preflight 的判定标准。

```powershell
counterguard verify --repo <repo> --base <base-sha> --head <head-sha> --config <config.json> --registry <registry> --runner-id root-pytest8 --output <new-verify-directory>
counterguard ci-report --report <new-verify-directory>/report.json --output <new-public-directory>
```

待测 head 必须真实包含原 H 契约的相同字节。工具读取 Git 对象，不使用 dirty 工作树替代 head。
只接受完整闭包恰好等于已审核 B 或 F 的一整组路径/内容摘要；不能逐文件混合两组来源。
新增源码、闭包/映射变化、第三方依赖、Python 不兼容或来源仓库不一致都是 unknown，run=null、退出 4。
缺失/篡改 Guard 或运行证据为完整性失败 5，不能伪装为 unknown 或“不适用”。
这是一条有限快照规则，不是语义等价性证明或学习作用域；未来普通代码改动可能经常 unknown。
需要跨版本泛化时另行审核新证据/Scope，不能沿用 scope_v1 的训练结论。

## 新版本与实测范围

新增 `standalone-compilation.v1`、`guard.v3`、`standalone-snapshot-scope.v1`、授权 v5、Registry entry v3 和
verify-report.v3。旧格式保留；只有含新 profile 的 Registry 走报告 v3。JSON 是事实来源，Markdown/公开 Summary 同源。
Registry v3 在本机保存来源仓库与工作区绝对路径，不能把条目拷到其他机器后改签充当授权。
发布时使用有限字段投影，原始日志、Registry 与工作区不公开上传。

新代码改变全包源码摘要：旧来源链保留原字节，新目录重新 bind/capture/compile/register，不能补签旧结果。
快照 Scope 绑定 Guard ID 与 Evidence，Guard 再绑定 Scope 摘要，避免相互摘要自引用。
每次真正执行前后重新核验来源和状态；单次核验内部复用刚重建的事实，不跨调用缓存有效状态。

[真实 Git/Docker 专项](../tests/integration/test_standalone_bootstrap.py)覆盖根/src、最小自检、Candidate/Shadow/Active/Retired、
固定提交重复决策、unknown 不启动及篡改拒绝。fixture 是工具自有代码，不代表外部新项目已完成用户接入计时。
