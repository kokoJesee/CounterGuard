# 新一批输入校验数据调查

按维护者“去找数据”的要求，核查 **12 个新仓库**，另只读复查既有 base45 历史。
找到 **3 条真实输入拒绝修复线索，来自 2 个项目谱系**；新增可准入来源、比较目标和正式跨项目场景均为 **0**。
修复线索未经 Docker 双向捕获，不能计为已验证 Evidence。当前真实来源保持 1，正式跨项目场景保持 0。

实现基线为 `0458cfcfc0c38bbae6cf8e7d8aaddd607f366558`，未修改产品代码或准入标准。
[候选机器记录](../../../benchmarks/v2/rechecks/input-validation-search-v2.jsonl)记录固定 SHA、源码摘要、检查种类及停止原因；
[汇总](summary.json)另记录原测试投影、完整树预算及失败证据。它们是调查回执，不是执行授权或正式标注。
原始下载、clone、日志和开发方案仅保留本地，没有发布上游实现副本。

## 找到了什么

| 项目与真实修复 | 原回归依据 | 实际停止点 |
|---|---|---|
| [TerminalTextEffects：加强颜色输入校验](https://github.com/ChrisBuilds/terminaltexteffects/commit/b360e0723d2c8e88e7db4f98c162b99b87442bd9)，B=`bb541505aa05d12e6f43d62d803b05836a5db09a` | 同提交的 `test_fg_invalid_hex` / `test_bg_invalid_hex` 各 6 个输入，另有布尔拒绝回归 | F 完整树 369 blob / 108,610,617 bytes；42 个文件超过 1 MiB，最大 5,000,052 bytes。超过现有单文件及全树预算 |
| [TerminalTextEffects：限定 ASCII hex](https://github.com/ChrisBuilds/terminaltexteffects/commit/0b6861567519b86d6bd9ab256131486c24a418ef)，B=`a69628ee20264604b22dc7fb0828d15ea893a0e3` | 同一 fg/bg 测试各保留完整 9 输入，新增带符号及全角数字输入 | F 完整树 368 blob / 108,586,419 bytes；同样 42 个文件超过 1 MiB，最大 5,000,052 bytes |
| [Tomli-W：拒绝负缩进](https://github.com/hukkin/tomli-w/commit/293e0a19762b29081521234a95b8b13f59da6a45)，B=`54268afcdea0bf3fba2e44d7e0e1a46c68583258` | `tests/test_invalid.py::test_negative_indent` 完整 1/1 条断言、1 case：`dumps({"k": "v"}, indent=-1)` 应抛 ValueError | B/F 完整树和唯一父关系已核对；两侧静态导出均为 unknown / `export_nonliteral_assignment` |

TerminalTextEffects 两条修复不能当作两个独立项目。其函数收 hex 字符串或 XTerm 整数，不能套用 termcolor 的 RGB 元组 Guard。
两份 F 的非截断 API 树均无 symlink/submodule，文件数未超 2048；失败的是字节预算。
完整 clone 在 API 预算失败后被主动停止，退出 1 / early EOF 是停止后的记录；**没有把下载失败当成准入失败依据**。
没有删除媒体、只取模块冒充完整提交，或调高限额。

额外对下载的固定原测试做了 AST 诊断，**未进行完整树准入**：
两份 F 的 fg/bg 非法 hex 测试各有一条断言，但参数使用 `pytest.param`，4 次投影均为 0 case / `nonliteral_expression`。
两份 F 的 `test_fg_invalid_bool` 则各完整投影 1/1 条、2 case；这不消除仓库预算或未审查导入闭包的阻塞。
不能因此说“只补 pytest.param 就能接入”，也不能只抽 hexterm 测试的 bool 断言而舍弃同函数的 Color 构造断言。

## 十二个新仓库及停止原因

SHA 和逐文件摘要见机器记录。以下区分一手静态调查与实际完整 Git 树评估，不把所有候选都写成“跑过 preflight”。

| 候选 | 检查到哪里 | 结论 |
|---|---|---|
| [colr](https://github.com/welbornprod/colr/tree/9fe7e07beb3d4bb1c9695399a55b7b4a6d753a9b) | 固定元数据、许可、接口和测试 | legacy；公开 color 是绑定方法，完整 oracle 未确认 |
| [console](https://github.com/mixmastamyk/console/tree/31ce7f0068d8f55f6303ccc60ee9bcce453bc8e8) | 固定元数据、许可 | legacy，且声明 ezenv 等运行依赖 |
| [yachalk](https://github.com/bluenote10/yachalk/tree/8c635690d5fa6ea03257835a01f2840b58e0c23b) | 固定元数据、许可、接口 | setup.cfg 有运行依赖；RGB 是拆通道工厂链 |
| [tcolorpy](https://github.com/thombashi/tcolorpy/tree/94f41b6ced704cd85756ef2d065ce26cb41ef9bd) | 固定元数据、许可、双色元组函数和范围测试 | legacy；长度 2/4 的类型/消息政策仍不确定 |
| [AthenaColor](https://github.com/code-of-chaos/AthenaColor/tree/3507c29cf9097cc9e12ccbd702c3574bc2c71197) | 固定元数据、GPL-3.0 许可及接口 | legacy、类接口；API 重定向已记录，不把它写成 MIT |
| [TerminalTextEffects](https://github.com/ChrisBuilds/terminaltexteffects/tree/b75a7baefe89a25d22754bcefb7d5caae8809477) | 固定 HEAD 元数据/接口、两条历史修复、完整 F API 树预算、原测试 AST | 真实修复存在；完整树超限，后续闭包不确定 |
| [loadfx](https://github.com/tivalsdeveloper/loadfx/tree/48f555763e01d0092ada4146e5983ee958a00f03) | 固定元数据、许可及接口 | MIT 文本完整性不确定；拆通道接口不能代表原八个元组调用 |
| [acrylic](https://github.com/prdx23/acrylic/tree/6bf062192914eaa864c5ce11d7a36c1f75ac5c9b) | 固定元数据、MIT 许可及接口 | legacy、类接口 |
| [uritools](https://github.com/tkem/uritools/tree/755daa58a33c6a0c2e402bc3313fbefc14569950) | 完整 Git 树及 `uritools:urisplit` 直接函数评估 | unknown：动态查找、导入状态修改；历史非法 scheme 修复不能移植现代元数据 |
| Tomli-W | 真实 B/F 完整树、父关系、根导出评估及原测试完整投影 | unknown：静态导出语法；没有绕过公开根入口改选内部函数 |
| [webcolors](https://github.com/ubernostrum/webcolors/tree/6c8da6832eb4ae2591a1883a0d1371263d6cd4db) | 完整 Git 树及 `webcolors:normalize_hex` 根导出评估 | unknown：`dynamic_code_or_lookup_requires_review`、`export_evaluated_annotation` |
| [durationpy](https://github.com/icholy/durationpy/tree/3df7a337a852f0b432f73c4892c4b48590a01bd0) | 固定 Git 元数据与 MIT 许可 | 没有 pyproject，[project] 缺失；未执行 setup.py |

另查 base45 HEAD 仍为既有 `5f49a519c3884a4fbc4c58c5c8f1fa25d7046020`，未发现能替代既有旧 Poetry B/F 的新修复。
这不是第十三个新候选，也没有重复计算旧预检通过数。
validators、pytimeparse 和 termcolor 衍生项目未纳入本批。

## 可重复核查

在上述 CounterGuard 实现版本的环境里，完整 clone 放在 `<candidate-clones>` 下，以仓库短名命名。
本轮实际运行的是现有 `read_committed_files`、`assess_runtime_source`、`assess_minimal_python` 和 `project_test` 函数，
没有将函数调用伪报成 CLI exit=0。以下是复查三个角色的等价只读入口；unknown 不提供执行许可：

```python
from pathlib import Path
from counterguard.repository import read_committed_files
from counterguard.bootstrap_binding import assess_runtime_source

root = Path("<candidate-clones>")
cases = [
    ("uritools", "755daa58a33c6a0c2e402bc3313fbefc14569950", "uritools", "urisplit", False),
    ("tomli-w", "293e0a19762b29081521234a95b8b13f59da6a45", "tomli_w", "dumps", True),
    ("webcolors", "6c8da6832eb4ae2591a1883a0d1371263d6cd4db", "webcolors", "normalize_hex", True),
]
for name, revision, module, symbol, exported in cases:
    _, files, _ = read_committed_files(root / name, revision)
    result = assess_runtime_source(
        files, module=module, symbol=symbol,
        source_ref=f"src/{module}/__init__.py", import_root="src",
        closure_algorithm="module-import-closure.v2",
        export_algorithm="static-root-reexport.v2" if exported else None,
    )
    print(name, result["status"], result["findings"])
```

TerminalTextEffects 无需下载媒体即可复算预算；对表中两条 F 分别运行：

```powershell
$fixed = 'b360e0723d2c8e88e7db4f98c162b99b87442bd9'
$tree = Invoke-RestMethod "https://api.github.com/repos/ChrisBuilds/terminaltexteffects/git/trees/${fixed}?recursive=1"
if ($tree.truncated) { throw 'Incomplete API tree' }
$blobs = @($tree.tree | Where-Object type -eq 'blob')
$blobs.Count
($blobs | Measure-Object size -Sum).Sum
@($blobs | Where-Object size -gt 1048576).Count
($blobs | Measure-Object size -Maximum).Maximum
```

API 元数据足以否决超限候选，不等于本地 Git 对象完整性核验或执行准入通过。
Tomli-W 的 1 case 与 TTE 的 AST 诊断均保留原断言；没有创建 H、授权、Evidence、Guard、标签或训练数据。
本轮只增调查材料，检查其摘要、数量、来源链接和隐私；没有代码改动，因此未重复快速层、全量或 Docker 测试。

结果为 **insufficient_data**。这些线索尚不足以建立独立 initial / refinement / holdout，不能据此进入正式训练或宣布实验完成。
也没有证据表明单独补一种语法就能解锁完整跨项目场景；扩大 profile 或完整树预算须另行评审，不能在采数时隐式放宽。
