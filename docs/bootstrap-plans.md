# 独立 Guard 的输入计划

`bootstrap plan` 是通用 Docker bootstrap 的第一个只读准备环节，本命令不批准捕获或执行。
它把目标模块的候选输入集与上游测试环境分开记录。仓库里存在 conftest，不等于所选断言使用了 fixture；
反过来，目标只用标准库也不证明可以忽略其包初始化、动态导入或资源文件。

```powershell
counterguard bootstrap plan --repo <repo> --revision <full-commit-sha> --target package.module:function --import-root src --test-ref tests/test_module.py --test-function test_regression --output <new-plan-directory>
# 根布局显式使用 --import-root .；输出目录位于当前工作区内、目标仓库外。
```

命令读取完整 Git 提交树，不 checkout/import，不运行项目测试、加载配置、安装或启动 Docker。
生成不可覆盖的 `plan.json`（`bootstrap-plan.v1`），固定提交、完整文件 Git/content pins 和工具源码摘要：

- `target_closure`：模块级静态导入图，包括父包 `__init__.py`、相对导入、可能的子模块及循环。
  模块内函数/分支中的 imports 全部保留；不因某条分支看起来不走而剪掉依赖。
- `proposed_runtime_pins`：提议供后续审核的源码输入；它**不是**已执行挂载或已批准闭包。
  独立模块/普通包与 `.`/`src` 可分析；缺失/冲突/namespace、第三方导入、标准库遮蔽、
  已知动态加载/资源访问保持 blocked 或 unknown。每闭包最多 256 模块、每模块 50,000 AST 节点、合计 250,000。
- `test_projection`：沿用[受限草案语法](contract-drafts.md)，保留源断言计数、case、unsupported 和测试 blob。
  不执行测试的顶层代码，不把未表达断言、fixture、setup 或复杂 oracle 当作已经迁移。
- `upstream_test_environment`：原 strict 全仓判断完整保留；另外列出引导文件及内容摘要、可解析的配置节和命名 hook。
  `setup.cfg` 的 packaging 节、tox 的环境节与真正 pytest 节分别显示；声明只表示存在，不证明目标需要它。

三个计划状态 `review_required` / `unknown` / `blocked` **都返回 4**，并保留计划。
没有“通过即执行”状态：`execution_allowed=false`、`verify_supported=false`、`execution_outcome=not_run`。
Git/路径完整性拒绝返回 5；参数/不可读取的草案内容等错误返回 2。已有输出目录拒绝覆盖。
完整树、pins 和边均排序；固定实现/提交/选项的结果无时间、随机 ID 或输出目录参与摘要，乱序 20 次稳定。

全仓 `minimal-python.v1` 的语义和旧报告保持原样。新计划不是契约、Evidence、Guard、Scope 或 Registry 条目，
任何现有执行入口都不消费它。静态闭包不能穷尽 Python 动态行为；别名反射、条件资源、模块重绑等仍需人工审核。
即使没有 finding，也须审核调用绑定、包副作用、资源、oracle 和 case 独立性。

用户下一步是审核计划及未支持项，准备真实 B/F 和由所有者提交到 H 的最终契约。
现在可继续使用[contract prepare 与 bootstrap bind](standalone-contracts.md)准备并重建 H 内契约和 B/F 来源；
这不提供自动审批；审核后可单独运行 [Docker 双向捕获](standalone-capture.md)及[最小 Guard/Scope](standalone-guards.md)，
不能用本地 capture、删 conftest/配置、重签计划或任意布尔开关代替。
运行上游原生测试套件是另一条路线，先完成配置、conftest/hooks、fixture、插件及其依赖的受控引导。
