# 完整快照范围内的来源与独立目标复筛

本轮复查两个已有来源，并查询十个新仓库：Tomli-W 的原负缩进断言现在可以完整准备，
但新增自然比较目标仍为 **0**。本轮没有候选执行、Docker、fork/H、标签或训练；
正式跨项目研究场景数没有增加。不能把新的来源准备成功当成 Evidence 已复现。

检查使用实现 `e80a316abee2926c2b71926c006b235fe961d09a` 的既有读取/投影规则，
没有修改准入标准。[逐项回执](../../../benchmarks/v2/rechecks/snapshot-candidate-rescreen-v1.jsonl)
和[汇总](summary.json)区分一手文件调查、真实完整快照检查与单项 AST 诊断。
原始 Git、源码、失败日志和实施方案留在本地，不进入公开仓库。

## 已有来源

[Tomli-W 的真实负缩进修复](https://github.com/hukkin/tomli-w/commit/293e0a19762b29081521234a95b8b13f59da6a45)
以 `54268afcdea0bf3fba2e44d7e0e1a46c68583258` 为唯一父提交。
现有新快照 profile 已实际读取两侧完整树和包，生成
`tests/test_invalid.py::test_negative_indent` 的完整 1/1 条断言、1 case：
`dumps({"k": "v"}, indent=-1)` 应抛 `ValueError`。
两侧状态为 review_required，尚无 owner H、执行审核、Evidence 或 Guard。

四个独立 TOML 库都不接受原 `indent` keyword。删去 keyword、改成 `pretty` 或新增包装器会改变调用，
因此没有继续创建 H 或执行来源来制造一个无法比较的场景。

[ulid-transform 原负时间戳回归](https://github.com/bluetooth-devices/ulid-transform/blob/1c55bb384a52df0eb43ea3bc9a1145ab16a131e0/tests/test_init.py)
也经当前 snapshot 投影器重新诊断：仍为 0/1 条、0 case，
`fixture_or_default_argument_requires_review`。没有把 `impl` fixture 或动态 `gen` 分发替换成手选内部实现。
这项是投影诊断，没有冒称已重跑完整来源准入。

## 十个新仓库

| 固定候选 | 实际触达边界 | 停止原因 |
|---|---|---|
| [tomlkit@eddd27e](https://github.com/python-poetry/tomlkit/tree/eddd27e43a62fe58707c311bfad2f52e72493f53) | 一手源码、元数据、许可与完整 API 树 | `dumps(data, sort_keys=False)` 无 indent；树中另有 submodule |
| [toml@65bab75](https://github.com/uiri/toml/tree/65bab7582ce14c55cdeec2244c65ea23039c9e6f) | 固定公开 encoder、setup 与许可 | `dumps(o, encoder=None)` 无 indent；legacy 元数据 |
| [rtoml@01d4d46](https://github.com/samuelcolvin/rtoml/tree/01d4d46f2794f04cfc190dbbb4698797c0de50c2) | 固定 Python API、元数据、Rust 实现与许可 | 无 indent；需要原生 Rust/PyO3 |
| [pytomlpp@a4dd9e9](https://github.com/bobfang1992/pytomlpp/tree/a4dd9e9998c2ca76c95c018d8f87e8be2c37439a) | 固定公开 API、元数据、setup 与许可 | `dumps(data)` 无 indent；需要 C++ 扩展 |
| [starhue@e70ee80](https://github.com/devesh-aggarwal/starhue/tree/e70ee80ee2fb26e98d622dcfeaa33eca830e96bc) | 实际完整快照、公开 hex API/测试、目标准入函数 | 包内可选 `matplotlib.figure` 导入拒绝；声明空依赖不代表全包无第三方 import |
| [material-palette-generator@8d79625](https://github.com/blacksteel3/material-palette-generator/tree/8d79625da3f77c2a314528398728202cff38cdb7) | 实际完整快照与目标准入函数 | 包内 `PIL` 导入拒绝；未只取 hex helper 绕过完整包 |
| [wallpaper-engine-toolkit@f7ae60e](https://github.com/rolling-codes/wallpaper-engine-toolkit/tree/f7ae60e47e441f4894f52dad63b205cda96e0fdc) | 实际完整快照、公开 hex API、目标准入函数 | `we_lib.py` 为单文件模块，当前快照要求普通包 |
| [colorist-for-python@d23bee9](https://github.com/jakob-bagterp/colorist-for-python/tree/d23bee9dc3607e777f92a33df330243457d1b0ca) | 实际完整快照、公开 ColorHex 构造器与六项拒绝政策 | 包内 `src/colorist/conftest.py` 拒绝；文件虽为 0 bytes，当前规则没有空文件例外 |
| [hexcraft@fc0dd1f](https://github.com/sn/hexcraft/tree/fc0dd1f5f3211e9f15baa3c11a09c96d6f99327a) | 实际完整快照、公开 parse 与六项拒绝政策 | 包内可选 numpy 导入拒绝；未删除可选模块 |
| [pansi 一手发行元数据](https://pypi.org/project/pansi/) | PyPI 页面/JSON 与其指向的 GitHub 请求 | 原仓库返回 404，固定 Git SHA 不确定；发行元数据另声明 pillow 运行依赖 |

前四项没有调用本地完整快照准入器。中间五项实际取得完整 Git 树并运行现有目标检查器，
各自的拒绝原因写入回执；pansi 没有用发行包冒充所需 Git 来源。
无明确迁移证据不等于证明迁移不存在。独立谱系仍需完整审核，不能仅凭不同仓库名或 fork=false 判定。

colorist 的固定[公开规范](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/docs/reference/extended-colors/hex.md)
及[校验实现](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/src/colorist/helper/validate.py)
覆盖原六字符串的拒绝域；阻塞的是包内文件身份，不是容量。
hexcraft 的[公开 parse 规范](https://github.com/sn/hexcraft/blob/fc0dd1f5f3211e9f15baa3c11a09c96d6f99327a/src/hexcraft/parsers.py)
也覆盖全部六项，仍不能据此跳过包内未安装导入。
本轮没有运行这些函数，也没有用静态推导替代目标自身 oracle 的实测。

## 特征与复现边界

另对已有 TTE `fg` 和 webcolors `normalize_hex` 的固定源码运行了现有研究语法解析诊断。
前者在语法子集内，后者因 Try 返回 `study_control_flow_or_binding_unsupported`。
没有创建外部 fixture context、FeatureRecord 或训练标签；不能借 helper 或填空特征来消除拒绝。

复现 Tomli-W 准备可调用已存在的
`prepare_snapshot_contract`，参数为上述 B/F、
`tests/test_invalid.py`、`test_negative_indent`、`tomli_w:dumps`、
`src/tomli_w/__init__.py`、import root `src`，输出必须为全新路径。
其他目标可将机器回执中的固定 SHA/entry 传给 `inspect_external_snapshot_target`；
该函数仅作检查，不赋予执行权限。profile 不同，旧只读 preflight 的退出码不能替代本检查。

本轮出现过本地 uv 缓存权限、裸 Git 布局、终端编码与回执序列化错误，均保留原记录。
随后从同一固定对象重查；没有把这些编排故障当成项目源码拒绝，也没有覆盖失败回执。
该只读调查使用上述未修改的基线代码，验收检查来源 pin、回执、链接和隐私。
研究训练桥接另有代码变更和单独验收，不把其测试计为候选已获准执行。

真实来源修复仍为 **2**、实际外部观察 pair **2**、正式研究场景 **0**。
当前材料仍不足以冻结独立 initial/refinement/holdout；30–50 场景目标未达到。
完整快照的研究拟合桥接另行实施和验收，不能用工程 fixture 增加上述真实数据计数。
