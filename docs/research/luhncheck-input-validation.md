# luhncheck：输入拒绝修复与跨项目可比性调查

核对日期：2026-10-18。只读 Git 对象与上游 API；没有 import、安装或执行候选项目，没有启动 Docker、创建 fork/H、修改候选登记或冻结研究标签。

## 结论

**暂不具备进入跨项目研究桥接的小样资格。** 当前 HEAD 是已有池中 `preflight_exit_code: 0` 的候选，值得优先检查；但该结果不能外推到历史修复提交。找到了一次真实输入校验变化，却没有找到同时满足“原先接受非法值、修复后拒绝、对应断言已在固定 F 测试中”的现成来源。它也不能直接承接 termcolor 的完整异常消息 Guard。[历史修复](https://github.com/dralshehri/luhncheck/commit/5142c55264930de138cccfd1e5e55e09ac27dbf8)、[固定 HEAD 测试](https://github.com/dralshehri/luhncheck/blob/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2/tests/test_luhncheck.py)

| 项目 | 固定对象 / 判定 |
|---|---|
| 仓库 | `dralshehri/luhncheck` |
| 本次核对 HEAD | `26c4f875beb01d841ff5ebe072bf872ef3e1a9c2` |
| 函数 | `luhncheck:is_luhn`；`src/luhncheck/__init__.py`，普通顶层函数 |
| 可疑校验变化 B | `ce064bd699a85b55efd5d9a908b768dd1e8cd472` |
| 可疑校验变化 F | `5142c55264930de138cccfd1e5e55e09ac27dbf8`；直接父提交为上述 B |
| 许可 | HEAD 与 F 均有 MIT LICENSE |
| 本次目标执行 | 0；下文行为均为源码推导，不是 Docker 实测 |
| 完整跨项目场景 | 未建立；不得据此增加接纳场景数量 |

来源：[HEAD 源码](https://github.com/dralshehri/luhncheck/blob/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2/src/luhncheck/__init__.py)、[F 提交](https://github.com/dralshehri/luhncheck/commit/5142c55264930de138cccfd1e5e55e09ac27dbf8)、[HEAD 许可](https://github.com/dralshehri/luhncheck/blob/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2/LICENSE)、[F 许可](https://github.com/dralshehri/luhncheck/blob/5142c55264930de138cccfd1e5e55e09ac27dbf8/LICENSE)。

## 真实修复：必须区分两种行为变化

F 的提交标题是 `Optimize the code`，但实际补丁同时加入 `if not number.isdigit(): return False`，并把 `test_number_validation` 的一个整数正例换为字母混入样例 `("110179827B", False)`。这是真实上游变更，不能因为标题没写 fix 就漏掉；也不能据此称其已证明严格的“漏拒绝”缺陷。[完整补丁](https://github.com/dralshehri/luhncheck/commit/5142c55264930de138cccfd1e5e55e09ac27dbf8)

| 输入 / 参数 | B 的静态推导 | F 的静态推导 | 固定 F 是否已有对应断言 | 适用结论 |
|---|---|---|---|---|
| `"110179827B"`，默认参数 | `map(int, number)` 遇字母产生异常 | 提前返回 `False` | 是，9 行参数化中的 1 行 | 拒绝方式从异常改为布尔值；不是“此前返回有效、后来拒绝” |
| `""`，默认参数 | 空数字列表的两项和均为 0，返回 `True` | `isdigit()` 为假，返回 `False` | 否 | 符合漏拒绝的静态线索；没有现成 F 断言，不能冒充已机械提取的来源契约 |
| `" - "` 等仅由空格、连字符构成的字符串，默认参数 | 规范化为空串，返回 `True` | 规范化为空串后返回 `False` | 否 | 同上；不额外计成独立修复 |
| `length` 或 `prefix` 不匹配 | 已有相应条件返回 `False` | 保留相应拒绝条件 | 多项已有断言 | 证明接口已有约束，不证明本次修复补了这些约束 |
| Unicode 数字 / 参数类型错误 | 未执行；没有为其建立项目认可的输入域 | 未执行；没有为其建立项目认可的输入域 | 本次历史字面量检查未找到 | 不确定；不贴缺陷或适用性标签 |

上述推导分别依据 [B 源码](https://github.com/dralshehri/luhncheck/blob/ce064bd699a85b55efd5d9a908b768dd1e8cd472/src/luhncheck/__init__.py)、[F 源码](https://github.com/dralshehri/luhncheck/blob/5142c55264930de138cccfd1e5e55e09ac27dbf8/src/luhncheck/__init__.py)、[F 回归测试](https://github.com/dralshehri/luhncheck/blob/5142c55264930de138cccfd1e5e55e09ac27dbf8/tests/test_luhncheck.py)。没有补写空串断言、移植 HEAD 测试或把异常解释成“接受了非法值”。

历史追踪还核对了三类变化：2021 年把专用 Saudi ID 校验改为通用 Luhn，并新增 `length` / `prefix` 参数；2022 年新增空格与连字符规范化；2026 年更新类型注解。第一类改变了模块、接口及业务范围，第二类扩大合法输入，第三类没有新增拒绝条件，均不能充当本轮所需的现成漏拒绝修复。[通用化提交](https://github.com/dralshehri/luhncheck/commit/797a168f670ae6817d759cab4d1175c264f377af)、[分隔符提交](https://github.com/dralshehri/luhncheck/commit/52b87470d9d0c482544ac91e45ea0143628f6ea3)、[类型更新](https://github.com/dralshehri/luhncheck/commit/073862e35a45cb222020b4b754ebb3fb7951b44b)

## 工程边界：当前 HEAD 通过不等于 B/F 通过

固定 HEAD 的 PEP 621 元数据明确声明 `dependencies = []`。历史 B/F 仍使用 `setup.cfg` + `setup.py`，F 的 `pyproject.toml` 只有构建与工具配置，没有 `[project]`。当前 CounterGuard 的 source-only 评估要求可读取的项目声明，并对 `setup.py` 保留单独审查条件。不能把 HEAD 的元数据挪进 B/F，也不能执行 setup.py 推断“应该零依赖”。[HEAD 元数据](https://github.com/dralshehri/luhncheck/blob/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2/pyproject.toml)、[F pyproject](https://github.com/dralshehri/luhncheck/blob/5142c55264930de138cccfd1e5e55e09ac27dbf8/pyproject.toml)、[F setup.py](https://github.com/dralshehri/luhncheck/blob/5142c55264930de138cccfd1e5e55e09ac27dbf8/setup.py)、[本工具判断实现](../../src/counterguard/bootstrap_binding.py)

本子调查没有新跑 preflight 或 bootstrap prepare；随后[全批核查](../results/input-validation-search-v1/README.md)已实测 HEAD preflight=0、HEAD 角色无 finding、B/F 角色均 metadata unknown，并复核 F 的 1 条断言投影为 9 case。它仍没有提供空串回归见证，也没有解除历史 B/F 元数据阻塞，未生成新的准备契约。手工新增来源契约需要独立规则与审核，新增 legacy profile 也未获实施授权；两者都不是本次为了凑小样可以直接启用的能力。

## 谱系与可比性

GitHub 一手仓库 API 在本次只读请求中返回 `dralshehri/luhncheck` 的 `fork=false`、`parent=null`、MIT。其可达历史起点是 Saudi ID 校验器，随后改名和通用化；没有查到与 termcolor 共享代码来源的声明。这支持将它作为与 termcolor 业务、实现来源分离的候选，但 API 的 `fork=false` 不能证明没有复制代码。[仓库 API](https://api.github.com/repos/dralshehri/luhncheck)、[最初 README](https://github.com/dralshehri/luhncheck/blob/a1401c89f349d292efcf464b87610840bada3ec3/README.rst)、[改名与接口历史说明](https://github.com/dralshehri/luhncheck/blob/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2/CHANGELOG.md)

**与现有 `mmcloughlin/luhn` 的独立性尚不能确认。** 两仓库的 GitHub API 都不是 fork，但 luhncheck 最初实现与较早 luhn 实现的核心校验片段具有明显文本相似性，包括相同的 `odd_sum`、`even_sum` 变量及切片、`sum(divmod(...))` 计算形式。它可能来自共同算法惯用写法，也可能有代码借用；本次没有一手说明能排除后者。因此不能把不同仓库名、不同根提交或 MIT 许可直接当作谱系独立证明，暂不将这二者凑成独立项目研究对。[luhn API](https://api.github.com/repos/mmcloughlin/luhn)、[早期 luhn 实现](https://github.com/mmcloughlin/luhn/blob/bdd29d9a31387f76f718fcdce221c1323723094e/luhn.py)、[luhncheck 最初实现](https://github.com/dralshehri/luhncheck/blob/a1401c89f349d292efcf464b87610840bada3ec3/src/saudi_id_validator.py)

termcolor 的现成 Guard 对 RGB 元组断言 `ValueError` 及特定消息；luhncheck 的公开 API 是字符串校验，非法号码约定返回 `False`，并明确允许空格和连字符。不能直接换入口运行 termcolor 的 8 个 RGB case，不能删去消息或改写期望值把两者说成可迁移。它们目前只共享“输入校验”类别，尚无共同输入域、同一行为 oracle 或获审适配方案。[termcolor 固定测试](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/tests/test_termcolor.py)、[luhncheck API 与规范化说明](https://github.com/dralshehri/luhncheck/blob/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2/README.md)

luhncheck 可以保留为未来**布尔型号码拒绝 Guard**的目标候选；前提是另有谱系独立、输入域与行为契约吻合、真实修复可复现的来源。纯数字非空 ASCII 字符串只是可讨论的候选共同域，不能反过来用它把空串排除后仍声称评测了本轮发现的空串漏拒绝。

## 复核范围与命令

固定 HEAD 可达提交数为 131。本次检查 `is_luhn` 的 `--follow` 路径历史、前身 `src/saudi_id_validator.py` 历史，以及关键实现与测试补丁。另只读枚举 HEAD 可达历史中 `tests/` 下的 10 个唯一 Python 测试 blob，用 `ast.parse` 检查字符串常量；空字符串、纯空格/连字符字符串、非 ASCII 字符串均未找到。这只证明这些受检测试 blob 没有相应字面量；不证明动态生成输入、其他路径、未拉取分支或未来提交没有相关测试。

在候选 clone 中可重复执行以下只读命令：

```powershell
git rev-parse 5142c55264930de138cccfd1e5e55e09ac27dbf8^
git rev-list --count 26c4f875beb01d841ff5ebe072bf872ef3e1a9c2
git log --follow --format='%H %s' -- src/luhncheck/__init__.py
git log --follow --format='%H %s' -- src/saudi_id_validator.py
git show 5142c55264930de138cccfd1e5e55e09ac27dbf8 --
git rev-list --objects 26c4f875beb01d841ff5ebe072bf872ef3e1a9c2 -- tests
```

受检测试 blob：`49143d6891ebff2cbe40eaecdf14ca07a2c65a67`、`77ea62da9b366c1c76298a929b819bc9b43c84ba`、`8daff3a893b276737ff757c5b794ea8599325e15`、`4030727043ad464b25d815538439a82120fc530b`、`9e8c16515ab7f88ca983a1ac8b0187c47080c0d1`、`b10c3e18dc3312583926c6aee3c3b598c4c88f4c`、`e83db4860418f51f3084a818b1f6c1f5b2290ad6`、`c64d92a797474b31cbcda6faae3e23c1bcc7d0df`、`deca6fe8da52d4ecbc6a096a87f34bfe967ff68c`、`a46b06846b696d328ed67059747227d95fd2e3ee`。

最终处置：保留候选，不新增来源 Evidence/Guard，不触发外部执行，不进入研究桥接。继续核查其他候选的现成真实修复及自然可比目标。
