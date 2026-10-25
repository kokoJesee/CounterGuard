# scope_v2 候选续查回执（v4）

本轮只做固定提交的只读检索、源码/测试形状审核和已有入口的预检。没有执行候选代码，
没有创建 fork、H、标签、训练数据或外部 Docker 运行。筛选标准保持不变：真实输入校验修复、
完整 B/F、原回归断言可无损表示、许可清楚、来源与目标谱系独立，并且当前受限 profile 能拒绝
所有未审核的安装与测试钩子。

## 结果

| 候选 | 真实修复 | 当前结论 | 精确阻塞 |
|---|---|---|---|
| `parse#261` | 是 | 不准入 | 原测试把参数写成 `"12:00 " + offset`，契约准备器拒绝动态字符串表达式 |
| `mpmath#886` | 是 | 不准入 | 原测试通过 `lambda` 传给 `pytest.raises`，超出现有字面量调用语法 |
| `python-json-patch#236` | 是 | 不准入 | 原测试依赖 `unittest` 类、循环和 `subTest`，无法无损投影 |
| `gimmegit#53` | 是 | 不准入 | 回归依赖宿主 Git 子进程、CLI `Namespace` 与额外依赖 |
| `ibeacon-ble#6` | 否 | 排除 | 修改的是距离计算/`None` 语义，不是非法输入漏拒绝修复，并带 Bluetooth 依赖 |
| `prometheus/client_python#1019` | 部分 | 排除 | 改动增加拒绝行为，但同一 PR 没有新增或修改对应回归测试 |
| `ref-builder#64` | 部分 | 不准入 | 同一提交混有大量无关改动，测试依赖模型/Faker/循环，无法形成最小独立来源链 |

本轮新增正式来源捕获、外部观察与正式场景均为 0；累计仍为 **2 / 2 / 0**。
这些拒绝不构成扩大 profile 的理由，也不允许把候选中的参数行当作独立研究场景。

## `parse#261` 的可重复证据

固定提交：

- B：`0d2d28fbccf023d0485be21aaccc95de88e92eaa`
- F：`c38631edb6b759417cc6544af13d99d03783750a`
- 合并提交：`0abf338be4a685a370f559ab256759f0cb985d64`

预检：

```powershell
uv run counterguard preflight --repo <parse-clone> --revision c38631edb6b759417cc6544af13d99d03783750a
```

结果为退出码 4、`status=unknown`，原因是 `runtime_dependencies_not_declared`。继续对原测试做只读契约准备：

```powershell
uv run counterguard contract prepare --repo <parse-clone> --revision c38631edb6b759417cc6544af13d99d03783750a --test-ref tests/test_format.py --test-function test_invalid_timezone_minutes --target parse:parse --output <new-output>
```

结果为退出码 1，`fixed_test_has_no_supported_cases`。源码复核确认原测试使用四个字面量 offset，
但被测调用参数是动态拼接表达式；现有提取器拒绝它，而不是删改输入来求通过。

## 对主线的影响

当前缺口已经从“执行器能否工作”变成“是否拥有至少一条通过正式语义裁决的跨项目场景”。
继续补工具自有 fixture 不会改变该计数。`scope_v2` 在正式场景、冻结数据和训练拟合出现前必须保持关闭。
