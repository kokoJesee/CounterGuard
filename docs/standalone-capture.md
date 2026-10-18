# 从通用契约捕获双向 Evidence

含[受限异常消息断言](literal-message-oracles.md)的 contract.v4 使用 standalone-capture.v2 / standalone-test.v2，原捕获计划与模板保留。消息不符归为测试失败；异常类型相同本身不能使该 case 通过。

`bootstrap capture` 接续 [H 内契约与来源绑定](standalone-contracts.md)，在已审核 Docker runner 中分别执行 B/F。
支持零运行时依赖、普通模块/包、根目录或 `src` 布局和 `contract.v3` 的受限字面量断言。
它生成首次 Evidence；后续[最小 Guard 编译、快照 Scope 和 Shadow 接入](standalone-guards.md)已支持同一受限 profile。

## 审核与命令

先完成真实 B→F→H 的契约准备、所有者提交和 `bootstrap bind`。绑定须来自当前工具实现，
各角色目标闭包均为 `review_required`，没有 unresolved finding；unknown/blocked 不能用审核理由覆盖。
人工仍须核对 oracle、调用绑定、包初始化/副作用、动态行为、资源需求和 case 独立性。
源代码兼容声明须允许 runner 的 Python 3.13.16，目标不可依赖镜像外安装或上游测试引导。

```powershell
counterguard runner list
counterguard bootstrap capture --repo <repo> --binding <binding-directory>/binding.json --runner-id <root-pytest8-reviewed-id> --evidence-id evd_regression_v1 --review-reason "已审核契约、调用绑定、闭包及独立性" --output <fresh-capture-directory>
counterguard bootstrap verify-evidence <fresh-capture-directory>/evidence.json --repo <repo>
```

runner ID 从 `runner list` 中选择 `root-pytest8.v1`，须已审核且本机 available；该镜像同时支持显式根/`src` 导入根。
它不是 validators 专用 pytest9 profile。发现、授权与执行均重验 catalog/build/attacks 来源，运行前核对精确 image ID；
不接收浮动 tag、不拉取替代镜像、不降级到本地执行器。Docker 未启动或镜像不可用须先修复运行环境。

绑定与输出位于当前工作区内，输出在目标仓库之外，目录必须全新。`--timeout` 默认 10 秒，范围 `(0,30]`。
`--review-reason` 是必填的本机可信操作者审核记录，**不是身份认证、签名或上游所有者授权凭据**。
H 的 Git blob 证明契约属于提交树，也不认证提交者身份。独立验证不执行仓库代码、不启动 Docker。

| 退出码 | 捕获结果 |
|---|---|
| 0 | B 为真实断言失败且 F 全通过；两侧完整覆盖契约 case，失败集非空，`reproduced=true` |
| 1 | 两次都是有效测试结果，但未满足双向复现，例如 B 全通过或 F 仍失败 |
| 2 | 请求参数非法，尚未建立有效捕获 |
| 3 | Docker/IO 不可用，或导入、收集、超时等执行故障；不能当作缺陷 |
| 4 | 源输入 unknown/blocked、Python 或 runner profile 不支持；不启动目标执行 |
| 5 | 来源、测试、授权、运行记录或日志完整性拒绝 |

有效但未复现的双向结果仍保存 `evidence.v4`，其 `reproduced=false`；成功核对这份记录不等于复现通过。
前置/完整性失败写 `capture-failure.json`，保留已完成的真实运行记录，不能发布成功 Evidence。
`verify-evidence` 独立重建事实后也按上述复现/故障口径返回 0/1/3；完整性拒绝返回 5。

## 输入与产出

容器只收到各自 B/F 角色的源码闭包、H 契约的精确字节和可信生成测试。
F 新增依赖不会倒灌给 B；测试配置、conftest、上游测试文件、仓库安装脚本和未声明资源不挂载。
这不证明原生测试套件兼容，也不改变旧 strict preflight 的含义。

- `capture.json`：`standalone-capture.v1`，绑定审核理由、当前实现、binding、runner review、封闭 policy 与超时。
- `auth/buggy.json`、`auth/fixed.json`：`docker-execution-authorization.v4`，分别绑定提交、输入 origins/pins、规范测试、请求与 case 映射。
- `b/`、`f/`：角色源码、`cg_control/contract.json`、`cg_control/test_capture.py`、`r/record.json` 和原始 stdout/stderr/JUnit。
- `evidence.json`：`evidence.v4`，包含两侧 RunRecord/授权引用、契约 ID/摘要、真实失败 case、复现结论及拒绝原因。

生成器只解码经过类型校验的字面量，不 eval 表达式，不在宿主 import 目标。raises 使用固定异常白名单；
目标导入发生于 pytest 收集期，导入抛异常不能被 raises oracle 误算为通过。
契约稳定 ID `case_<hex>` 保持不变；传输到既有 JUnit 读取器时单射映射为 `case-<hex>`，授权记录两者，
Evidence 失败集映射回原契约 ID。没有修改旧读取器的 case 规则。

执行前后均重建来源与授权；发布 Evidence 前再次独立核对两次实际记录、封闭 Docker argv、输入、版本和原始 JUnit。
若 B 在 F 执行期间被改动，保留实际运行证据并拒绝发布 Evidence。
输出不覆盖，时间是真实 UTC，重复运行使用新 Evidence ID/目录和 run ID；比较 case/计数，不能要求全产物摘要相同。

## 边界与重算

新模型和 [Schema](../schemas/standalone-evidence.schema.json)独立于旧 Evidence/Guard/Registry。
新 Evidence 通过 `bootstrap compile` 生成 Guard v3 后才能登记并进入统一 verify；旧 `capture/compile` 不消费新记录，
不能通过手改版本、重签历史或设置布尔开关绕过。
源码、B/F/H、契约投影、runner、policy 或输入映射变化时按[重算规则](data-contracts.md)重新 bind/capture，使用新命名空间。
绑定 v1 和旧执行证据保留原字节，不在当前源码下补签为有效。

Docker 控制降低宿主暴露面，但不能认证恶意目标没有在容器内干扰 pytest/JUnit；本机全链重写也没有密码学证明。
本次[实测](results/standalone-capture-v1/README.md)使用工具自有 B/F/H fixture，验证真实 Docker 路径，
不是第二个外部开源缺陷的接入成功，也不是已完成用户接入计时或通用安全证明。
