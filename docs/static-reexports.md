# 受限根包重导出

`contract prepare` 能识别根包通过一条显式 `from ... import ...` 导出的普通函数，使用新版本
`contract.v5` / `standalone-static-reexport.v1`。这是源码声明核验，仍须人工审核；不会导入目标 Python。
既有 contract.v3/v4 不获得这一能力，未改写历史契约或执行产物。

例如原回归测试使用 `from package import public`，而根包声明 `from .core import original as public`。
工具仍按 `package:public` 提取并生成测试，不把调用偷偷换成 `package.core:original`。

## 接受范围

- 导入根为 `.` 或 `src`；公开入口必须是根包的唯一 `__init__.py`，不能同时存在同名 `.py`。
- 根包只允许字符串文档、future import、一条具名导入和可选的字面量 `__all__`。
  导入只能指向本包的一个直接子 `.py` 模块，支持显式 `as`；不支持多条导入、多级转发或子包。
- 公开符号只绑定一次；拒绝星号、条件导出、赋值别名、删除、动态属性和模块查找 hook。
  `__all__` 不被当作证明符号身份的依据。
- 定义必须是未装饰的顶层同步函数；定义模块只接受显式标准库导入、无重绑定的字面量常量和普通函数。
  拒绝顶层调用、类、动态/属性赋值、非字面量默认值、未知装饰器和一般控制流。
- 注解须由 future annotations 延后求值。唯一允许的条件块是先显式赋值 `TYPE_CHECKING = False`
  后的 `if TYPE_CHECKING:` 导入块，无 else；完整闭包仍检查其中的导入。
  其他函数只额外允许未重绑的 `from functools import cache` 装饰器，目标函数仍不能装饰。
- 每个解析模块至多 50,000 AST 节点；原有完整 Git 树、模块闭包、依赖/资源/遮蔽预算和检查不变。

这些条件刻意窄。条件不符时保留 unknown/拒绝，不执行候选代码，也不安装依赖或载入上游 pytest 环境。
F 不能按该语法解析时 prepare 保留原格式及待审结果；不会伪造一个已支持的 v5 声明。

## 声明、重建和执行

v5 新增 `definition_module`、`definition_symbol`、`definition_ref`；原 `target_module` / `target_symbol` /
`source_ref` 始终指向公开入口。定义路径必须在完整 `runtime_refs` 中，不以定义文件替换父包初始化。
见 [Schema](../schemas/standalone-contract-v5.schema.json)。纯字面量 case 保留 projection.v1；消息 case 要求 projection.v2。

新 `bootstrap-binding.v3` 从 B、F、H 分别重建导出声明，每个角色记录根包/定义文件的内容摘要和定义位置，
逐项比对契约中的定义，不用 F 的结论代替 B。H 仍必须是 F 的直接子提交，且只新增该契约文件。
任何角色的导出重绑、定义漂移、未知闭包或依赖问题都阻止捕获。独立 verify-binding 重读提交并重算整个记录；
修改结论后重签自摘要不能授权执行。

执行仍须另行审核与已审核精确 Docker runner。v5 复用字面量测试生成器 standalone-test.v2、capture.v2、
Guard v4 / Registry entry v4；这些记录已绑定完整契约原始摘要、角色闭包和逐文件实现摘要，不需要另改执行格式。
生成测试始终 import 公开入口，最小 Guard 仍只保留实际失败 case。精确快照 Scope 包含整组根包和定义模块，
不能单凭公开入口文件或 RunRecord 的单文件 target_digest 判断整个目标是否未变。

静态声明不能证明任意 Python 副作用、oracle 语义、所有者身份或缺陷真实存在。函数体与标准库操作仍需源审，
实际 buggy 失败/fixed 通过必须由双向 Docker 运行证明。该能力也不提供学习 Scope 或自然跨项目可比性。

## 重算范围

更换导出/定义映射必须用新契约 ID、所有者 H 和新绑定目录。工具源码变化使旧实现绑定过期；需要当前结论时，
按新 ID/目录重新 bind → capture → compile → Registry 审核，不能为历史补签。
现有契约、artifact、冻结 scope_v1、Docker policy/镜像收据和发布标签保持原样。未新增运行时依赖。

验证覆盖见[静态专项](../tests/unit/test_static_exports.py)、
[含传输替身的链路回归](../tests/unit/test_exception_match_pipeline.py)和
[真实 Git/Docker 专项](../tests/integration/test_standalone_capture.py)。替身测试不被算作真实目标执行。
