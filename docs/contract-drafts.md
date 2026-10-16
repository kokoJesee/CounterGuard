# 从已有测试起草契约

`contract draft` 已提供通用的**静态草案提取**。此前只有 validators 的专用 `extract_mac_contract`，
没有面向任意测试的命令；两种能力不能混称。当前命令不运行测试、不 import 项目、
不安装依赖、不加载 conftest，也不生成可执行授权。

```powershell
counterguard contract draft --repo <repo> --revision <full-sha> --test-ref tests/test_price.py --test-function test_price --target package.pricing:price --output artifacts/proposals/new-id
```

从完整 Git 提交树读取指定测试，写全新目录中的 `proposal.json`。输出需在调用工作区下、目标仓库外；
工作树修改不会替换提交中的断言。即使原仓库的执行预检不通过，也可只读准备草案，不能借此执行它。

## 支持的语法

- 一个显式选中的顶层同步 `test_*` 函数；没有 fixture/default 参数，或参数完整来自字面量 `pytest.mark.parametrize`。
- 普通 import / from-import 与前置的目标函数别名；这只是语法绑定，不证明运行时对象身份。
- 直接 `assert target(literals) ==/!= literal`；`is/is not` 只接受 None、True、False。
- `assert target(...)` 和 `assert not target(...)` 保留 truthy/falsey，不改写成 `is True/False`。
- 单语句 `with pytest.raises(ValueError/TypeError/OverflowError): target(...)`，不接收 match、as 或用户异常类。
- 标量、有限浮点、bytes 和有界 list/tuple/dict；类型带标签保留，tuple 不变成 list，bytes 以十六进制记录。

固定预算为测试 1 MiB、AST 50000 节点、最多 256 case；字面量嵌套最多 8 层、容器最多 128 项、整数最多 256 bit。
不计算算术、不调用 helper、不读取模块全局值，不执行 eval/exec。负数字面量可保留；`1024 ** 2` 这类表达式拒绝。
只用安全的 AST/字面量读取解释 parametrize 标签，不执行其参数表达式。

fixture、任意 setup/赋值、控制流、异步、间接参数化、未知装饰器/通配 import、嵌套目标调用和复杂 oracle 均需人工处理。
任意 setup/控制流会拒绝整段选中函数；独立但不支持的断言逐项列出，绝不悄悄丢掉。
局部变量/参数不能冒充导入的目标或内置异常。非字面量 assert message 也拒绝；普通文字 message 不成为 oracle。

## 如何读结果

| 状态 / 退出码 | 含义 |
|---|---|
| draft_ready / 0 | 选中测试的断言语法全部被表达；仍需人工审核，不能执行 |
| partial / 4 | 部分断言已投影，unsupported 给出未表达的行及原因；已经写出草案 |
| unsupported / 4 | 没有可表达的 case，保留原因，不制造空的可执行契约 |
| 2 / 4 / 5 | 输入/解析错误、Git 信息不足或安全/不可变输出冲突；不覆盖历史输出 |

草案绑定 commit、测试路径、Git blob ID、原字节摘要、原行号、断言 AST 摘要和实际工具源码摘要。
同输入同实现不使用时间/UUID，结果可逐字节复现；case ID 不依赖原行号，增加注释只改变来源记录。
`source_assertions` 统计 assert 及 pytest.raises 上下文；表示数与未表示数必须对账。
Schema 为独立 [contract-proposal.v1](../schemas/contract-proposal.schema.json)，不冒充已有 contract.v1/v2。

`human_review_required=true`、`execution_allowed=false` 均为强制字段。
Registry、compile 和 verify 不消费这种草案；没有“改一个 approved=true 就执行”的通道。
原测试也可能写错，多个断言之间可能依赖状态，import 可能受运行时重绑影响；因此机械提取并不是正确性或行为等价证明。
用户必须审核每个预期、调用类型、case 独立性和遗漏项，再由仓库所有者提交最终契约到 assertion head。
通用契约格式、Docker 双向捕获和 Guard/Scope 绑定仍见[接入前置](project-admission.md)。

本轮 [boltons 试走](results/onboarding-boltons-v1/README.md)从一个真实修复新增的测试中提取 12 条直接断言，
明确保留 1 条幂等性断言为 unsupported；没有把该库代码放到宿主或 Docker 中执行。
