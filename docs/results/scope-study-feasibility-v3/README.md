# 按现有 profile 继续筛选

维护者选择继续按当前准入规则采集，旧式源码 profile 提案暂不实施。本批再读 3 个仓库，累计 **13 个候选、接纳场景 0、目标执行 0**。固定提交、角色评估和命令见 [probes.json](probes.json)，原始候选登记仅追加新行；前两批回执没有覆盖。运行包源码仍与实现提交 `466dd007f6c24cde78995e728b308539ed1f1826` 一致。

| 候选 | 实测结果 | 下一项具体缺口 |
|---|---|---|
| [termcolor](https://github.com/termcolor/termcolor/tree/c7d0b8e8a42f417ec0c07fd846138b0a19b24d36) | HEAD preflight 4：pytest 最低版本超过正式 runner、tox 配置、省略 dependencies。source-only 的直接模块 `termcolor.termcolor:colored` 为 review_required、无 finding；RGB 范围修复 B=`db6b299abfec18223a98827f4cd6a7e475b7dfb5` / F=`520facb24e5310a6f48736dddfe86164057a322c` 的两侧角色评估也均无 finding | 测试从根包导入 colored，重导出身份尚未审核；现成 `test_invalid_rgb` 的两条 raises 都带 match，按原语法投影为 0/2、unsupported_exception_assertion。未删除 match 或调整 oracle 来绕过。没有 prepare/H/Evidence |
| [base45](https://github.com/kirei/python-base45/tree/5f49a519c3884a4fbc4c58c5c8f1fa25d7046020) | HEAD preflight 4，省略 dependencies；source-only 当前普通函数闭包无 finding。单字节修复 B=`6701de331b33053ac654545d20dfcafda8a547f1` / F=`49e73b0eb0b7ff43cae270d5601c5fe267f4ab34` 仍使用旧 Poetry 元数据，两侧 project_metadata_unavailable | 测试为 unittest 类方法/数据循环，不是支持的顶层字面量函数。不能把 HEAD 元数据移植到历史 B/F，也没有从 merge 提交伪造直接父子修复对 |
| [egcd](https://github.com/lapets/egcd/tree/05855f73934727eb7707185cc75ef380738e768a) | HEAD preflight 4，省略 dependencies；运行模块本身 import doctest，不在当前审核 stdlib 集合内，角色评估 unknown。负数输入修复 B=`15e5eaa9a5a6334e72d11b06f4dae6462b6a475c` / F=`1107109eefa36c917d2a520c2ddc02feee5ee5aa` 两侧也有同一 finding | 回归依据在 docstring，未伪选顶层 test 函数。doctest 即使是 Python 标准库，也不因此自动加入本工具允许集合；没有删导入或执行 doctest |

termcolor 是目前已核对的“真实 B/F + 两侧普通函数源码无 finding”来源，仍缺受支持的契约投影。无 finding 不等于已审核、可以执行或存在失败见证，不能标为接纳场景。HEAD 的 pytest 版本问题与历史 B/F 的 source-only 评估分别记录，没有升级 runner 或加载仓库测试配置。

## 复核方式

每个候选的 `preflight_command` 可直接替换 clone 占位符后执行；本批都退出 4。静态角色评估使用固定实现中的以下内部 API，只读完整 Git 树，不 import 目标：

```python
from pathlib import Path
from types import SimpleNamespace
from counterguard.bootstrap_binding import _runtime_assessment
from counterguard.repository import read_committed_files

_, files, _ = read_committed_files(Path("<candidate-clone>"), "<full-commit>")
shape = SimpleNamespace(
    target_module="<module>", target_symbol="<symbol>",
    source_ref="<source_ref>", import_root="<import_root>",
)
report = _runtime_assessment(files, shape)
```

参数来自回执各 observation 的 target/source_ref/import_root；历史评估分别使用 buggy_commit/fixed_commit。termcolor 的语法投影另以 `termcolor:colored` 读取 `tests/test_termcolor.py::test_invalid_rgb`，与直接运行模块的重导出绑定未获验证。该探测不等同于 bootstrap bind 或捕获授权。

本批没有测完整下载/检索、人审和所有者等待时间，不能估算总接入时间或兼容比例。没有查询当前 Docker 状态，没有执行目标/安装脚本，没有新增依赖或放宽默认 profile；也没有创建 fork/H、冻结新数据、运行 learner 或开始研究桥接。

下一步继续寻找 **真实 B/F + 普通函数 + 支持的直接字面量回归断言** 同时成立的来源，再审查自然可比的独立项目。termcolor、Luhn/luhncheck 作为明确缺口的开发候选保留；不给它们补假标签或成功记录。候选可行性 gate 仍未通过，研究评测器保持未启动。

这里只追加候选材料与说明；[validation.json](validation.json)记录摘要、固定 blob、链接、隐私及受保护路径核对，Ruff 通过。没有新运行代码，因此未重复快速/全量测试或 Docker 专项。原始进程 stdout/stderr 和 clone 只留本地。
