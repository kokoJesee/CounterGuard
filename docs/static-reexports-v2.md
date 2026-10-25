# 多导出根包与有限类查找钩子

本规格描述已实现的受限静态导出，实测见[验收记录](results/static-reexport-v2/README.md)。
在新增接受逻辑前冻结以下范围。它只识别可供源码审核的声明，不证明 Python 安全或授权跨项目执行。

## 版本与入口

显式 `contract prepare --profile static-reexport-v2` 会生成 `contract.v6`，profile 是 `standalone-static-reexport.v2`。契约里 `export_algorithm=static-root-reexport.v2`、`closure_algorithm=module-import-closure.v2`、`hook_grammar=finite-raise-hook.v1` 都是封闭 Literal。

`bootstrap plan --profile static-reexport-v2` 生成 `bootstrap-plan.v2`，只作静态材料。新契约生成 `bootstrap-binding.v4`，B/F/H 分别重建算法、闭包、导出、钩子和所有源码 pin。

默认 profile 是 `existing`，仍然使用原有算法和 contract.v3/v4/v5，不会自动尝试 v2。未知 profile、算法或字段都拒绝，不能降级后忽略。

比较目标无需虚构自己的 B/F/H。以下只读命令生成独立的 `static-target-inspection.v1`：

```powershell
counterguard bootstrap inspect-target --repo <repo> --revision <SHA> --target <root:symbol> --import-root . --profile static-reexport-v2 --output <new-dir>
```

它固定完整提交树、共享同一依赖/closure/export 检查，CLI 始终退出 4；不能作为契约、binding 或执行授权读取。

| 消费层 | 本次版本决策 | 重建依据 |
|---|---|---|
| contract / plan / binding | 新增 v6 / v2 / v4 | 显式算法选择和新观察字段 |
| capture / generator | 继续 capture.v2 / standalone-test.v2 | v6 保留 v4 的字面量 oracle，渲染代码不变；完整 binding digest 和原始 H 契约仍绑定 |
| Evidence / authorization | 继续 evidence.v4 / authorization.v4 | 结构未变，每次独立重建 binding、当前全包实现、runner、policy、输入与 JUnit |
| Guard / Registry | 继续 guard.v4 / registry-entry.v4 | 字段和 oracle 语义未变，来源审核必须递归接受并重建 v6/v4；不把新字段塞入旧契约 |
| snapshot Scope / replay | 保留旧版本及精确来源限制 | 不允许换仓库、换 symbol 或拼接 B/F；不是本轮研究桥接 |

## 静态导出 grammar

根包仅允许 docstring、`from __future__ import annotations`、同包直接子模块的多个具名 from-import、
一次字面量 `__all__`，以及一次 `__version__ = '…'` 或 `__version__: str = '…'`。
版本必须为字符串，注解只能是未被本模块绑定的内置 `str`。所有绑定唯一；目标恰好绑定一次，
不能与子模块导入同名冲突。所有导入模块必须存在为普通 `.py`，没有并列同名包。

目标仍是同包直接子模块的普通顶层函数，定义模块只允许原 v1 的受限声明，加上可解析且存在的同包具名相对导入。
相对导入不证明被导入对象纯净；闭包包含所有包初始化器、旁支、条件和函数内导入。
未知装饰器、动态默认值、求值注解、重绑定、动态／多跳目标别名仍拒绝。
不复制目标，不绕过原根包。闭包 import cycle 可以存在；目标解析不沿 cycle 或多跳追踪。

主要拒绝码：`export_root_statement_unsupported`、`export_direct_child_required`、
`export_rebinding`、`export_hook_binding`、`export_version_not_literal_string`、
`export_version_annotation_unsupported`、`export_definition_not_ordinary_function`；其余沿用 v1 有限错误码。

## 有限钩子 grammar

closure.v2 按词法作用域区分 module / class / metaclass / nested_function。
条件、循环、try 内不创建新作用域。模块的 `__getattr__` 声明、导入、赋值、删除和 global 绑定保持 unknown，
类 hook 的别名／赋值不能当成有限方法。`__getattribute__` 不获有限支持。

唯一可识别类钩子是顶层、无装饰器、无 class keyword、无类型参数的普通 class 或单一 `type/object` 基类，
类体只含 docstring 与一份 `__getattr__`。方法无装饰器、默认参数、变参或类型参数，恰有两个普通位置参数；
方法体除 docstring 只有 `raise ImportedException(message)`，不能有 cause、其他调用、返回或转发。
message 只允许字符串常量或仅插入第二参数的无转换／格式说明 f-string。
注解必须延迟求值。异常名必须唯一、由模块顶层具名 from-import 引入同包模块；模块／类作用域均不得覆盖相关名字。

异常模块整体限定为 docstring、future annotations 与普通唯一命名的 Exception 直接子类；
异常类仅含 docstring，可选一个 `__init__(self, message: str) -> None`，其体仅为 `super().__init__(message)`。
空异常类也允许 `pass`。
不能有装饰器、额外方法、导入、class keyword、默认参数、重绑定或任意构造副作用。
这是保守的语法审核，不是 Python 异常等价或任意 monkeypatch 的证明。

识别结果写入 `hook_observations`：scope、qualified name、行号、grammar、模块内容摘要及异常模块/类/摘要。
有限识别只消除这一条误分类；仍为 `review_required`，不表示安全通过。
模块钩子为 `module_lookup_hook_requires_review`，非有限类钩子为 `class_lookup_hook_requires_review`，
嵌套函数记录观察；全局逃逸仍 unknown。动态查找、资源、原生访问等原有 finding 均保留。

## 验证与重新物化

专项包含旧路由不变、新旧模型隔离、正反 grammar、20 次乱序、重签导出/观察/闭包/版本的拒绝，
以及只执行工具自有 B/F/H fixture 的 Docker 捕获、最小 Guard、Registry 核验。
真实进程测试标 slow。运行快速层和专项，不跑全量，不执行 colored。

源码变化会改变全包 implementation_digests；旧 plan/binding/capture/Evidence/Guard/Registry 不原地更新。
需要消费时以新 ID 重新物化全链；termcolor 原契约和 H 若内容不变可复用，但旧运行记录不冒充当前实现验收。
冻结 scope_v1、原 examples/契约、历史 artifact、发布标签不变；本轮不新增运行时依赖。
Windows 终端初始化、环境读取、类体与元类的其他效果仍需对完整源码逐项人工审核。
colored 不需要虚构 B/F/H；外部跨项目执行继续等待独立研究映射与授权桥接。
