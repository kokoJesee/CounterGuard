# Click 与 termcolor：RGB 契约可比性评审

核对日期：2026-10-18。仅阅读固定 Git 对象、现有契约和一手上游页面；候选代码执行数为 **0**。没有 import、安装、Docker、fork、H、标签冻结或 profile 改动。本文是研究提案，不是目标准入证明，也不是已确认的合法反例。

## 判断

**Click 值得保留为 RGB 共同域比较目标，但不适合仅补一项参数展开语法后就宣布接入。** 两项目确实都把 RGB 颜色理解为三个位于 0–255 的整数；可以讨论前景/背景参数映射。完整 termcolor Guard 还包含专属异常消息，Click 合法实现使用另一消息。因此，比较有自然业务基础，但“同一输入域”不等于“原 Guard 在所有目标上适用”。[termcolor F 规范与实现](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/src/termcolor/termcolor.py#L128-L185)、[Click F 规范与实现](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/src/click/termui.py#L572-L700)

比较目标**不需要自己的 buggy/fixed 修复对、来源 Evidence 或新的来源 Guard**。它需要独立固定快照、明确的自身规范、可审核调用和完整安全准入。Click 的真实修复可帮助理解规范与历史差异；不能把复现这次修复再追加成“作为目标”的强制门槛。新的跨项目研究桥接须单独版本化；生产 Guard 的仓库、入口与 snapshot scope 不能直接替换。[现有研究规格](../experiments/scope-v2/design.md)、[现有来源闭环](../results/termcolor-source-v1/README.md)

## 固定来源

| 对象 | 固定版本 / 用途 |
|---|---|
| termcolor B | `db6b299abfec18223a98827f4cd6a7e475b7dfb5`；已有真实来源捕获 |
| termcolor F | `520facb24e5310a6f48736dddfe86164057a322c`；现有 Guard 的行为依据 |
| Click B | `7925a3410d7098c28cfca3b2baa6c852666bbd14`；解释真实修复前的行为 |
| Click F | `07c909f23f0f83b5ca137c167b9a134d66201f67`；本次优先讨论的目标快照 |
| Click 本轮已检查 HEAD | `2247b35ea1c47c727d7a06e51fa280e12a863ff6`；不能与 F 混成同一快照 |

Click F 的直接父提交确为上述 B；补丁同时修正非法颜色校验和调色板索引 `0` 的 truthiness 问题。它不是只改报错文本。许可为 BSD-3-Clause，termcolor F 为 MIT；保留相应署名和许可仍是后续分发要求。[Click 修复](https://github.com/pallets/click/commit/07c909f23f0f83b5ca137c167b9a134d66201f67)、[Click F 许可](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/LICENSE.txt)、[termcolor F 许可](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/COPYING.txt)

## 共同域和调用映射

建议先讨论最窄共同域：普通字符串文本、单一前景或背景参数、元素类型为普通整数的 RGB 元组。有效 RGB 为长度 3 且每项在 0–255；待拒绝域为越界整数或长度错误的元组。暂不混入命名色、整数调色板、列表、布尔值、浮点、组合属性或输出终端检测。[termcolor F API](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/src/termcolor/termcolor.py#L134-L185)、[Click F API](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/src/click/termui.py#L597-L655)

| 维度 | termcolor 来源调用 | Click 目标调用 | 审核要求 |
|---|---|---|---|
| 公开入口 | `termcolor:colored` | `click:style` | 原公开导出均须绑定；直接定义模块诊断不等价于根包准入 |
| 文本 | 第一个位置参数 | 第一个位置参数 | 可取同一固定字符串；原来源 case 的文本不能悄悄改写 |
| 前景 | `color=rgb` | `fg=rgb` | 显式、固定参数映射 |
| 背景 | `on_color=rgb` | `bg=rgb` | 同上；每个 case 只启用一侧 |
| 强制着色 | `force_color=True` | 无此参数 | 这是 termcolor 的到达路径设置；不能原样传给 Click |
| 返回值 | 返回 ANSI 字符串；未启用颜色时可提前返回文本 | `style` 直接构造 ANSI 字符串 | 拒绝型 Guard 不应偷换成逐字节返回值比较 |

termcolor 在检查 RGB 之前执行 `can_colorize`；`force_color=True` 且没有显式 `no_color=True` 时先于环境变量/TTY 检测返回真。现有 8 个 case 已带该参数。Click `style` 本身没有 `force_color` 或 TTY 门控；终端输出/剥除行为属于 `echo` 等其他入口，不能用 `secho` 替换本次返回值 API。[termcolor 着色门控](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/src/termcolor/termcolor.py#L92-L125)、[Click style 返回路径](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/src/click/termui.py#L690-L724)

来源 Guard 的 4 个 RGB 值乘前景/背景形成 8 case。Click F 原测试中的非法 RGB 值有部分完全重合，溢出分量的位置也有区别；不能把两个参数表说成逐项相同。二者可比较的依据是固定规范与输入域，而不是“都恰好有 8 个测试”。[来源契约](../results/static-reexport-v1/termcolor-contract.json)、[Click F 测试](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/tests/test_utils/test_style.py#L81-L107)

## 消息差异与合法反例假设

现有来源 oracle 是 `ValueError` 加字面量片段 `Expected a tuple of 3 ints in range 0-255`；它不是仅要求“拒绝非法 RGB”。Click F 自身测试要求 `ValueError` 和片段 `Unknown color`。异常类型相同不能掩盖消息契约不同，消息不同也不自动否决整个比较目标。[termcolor 原测试](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/tests/test_termcolor.py#L387-L402)、[Click 原测试](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/tests/test_utils/test_style.py#L81-L107)

可供后续人审的假设：在保留源 Guard 消息断言、完成上述调用映射且无其他映射缺口时，Click F 对例如 `(-1, 0, 0)` 的自身合法拒绝，可能触发源 Guard 的消息不匹配报警。这可研究**错误应用来源消息策略**的适用边界；不能把它报成 Click 漏校验，也不能仅凭 Guard 报警给它贴 inapplicable 标签。需要先独立审核 Click 自身规范，再在受准入 Docker 中同时验证目标自身契约与迁移结果。当前都未执行，标签为未裁决。

这个假设的收益和限制需要一起保留：它有真实 API 差异，但可能主要测到消息措辞的可迁移性。若目标研究只想证明“RGB 越界拒绝”能够迁移，应另开明确的研究主张与契约版本；不能追溯删除已获批 Guard 的 match，更不能在观察 replay 结果后改 oracle。[合法反例规则](../experiments/scope-v2/design.md)

以下情况也不能混成合法反例：Click B 对负 RGB 直接格式化的源码路径是待验证缺陷线索，不是“不同项目所以合法”；有效 RGB 会被原 raises Guard 错误要求抛异常，但它们没有出现在来源失败输入中，不能为凑负例悄悄加入；布尔/浮点值虽然暴露两实现的检查差异，却不在本次最窄共同域，且不宜在规范未审前解释为哪方正确。[Click B 实现](https://github.com/pallets/click/blob/7925a3410d7098c28cfca3b2baa6c852666bbd14/src/click/termui.py#L572-L580)、[termcolor F 检查](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/src/termcolor/termcolor.py#L128-L131)

## 原测试是否能机械展开

Click F 的 `test_styling_invalid_color` 有两个独立参数轴：`param` 取 `fg` / `bg`，`value` 为 18 项固定输入，完整语义为 **36 个调用 case**。断言内 `**{param: value}` 的键和值都能在具体参数绑定后确定；不需要执行字典或项目代码来知道调用参数。字面量 match 已是现有能力，不能把全部阻塞归给消息语法。[固定测试](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/tests/test_utils/test_style.py#L81-L107)

这是一个可讨论的小范围提取器扩展，而不是任意 `**mapping` 支持：限定绑定后的静态字典、字符串关键字、无重复键或跨显式关键字冲突、无调用/属性/推导式/外部变量求值，并完整绑定原断言与参数轴。稳定 case 身份、排列次序、重复值和预算也要有规则。不能选择性丢掉难表示的值而把 36 个 case 说成完整投影。本文只说明静态可确定性，没有实现该扩展或生成新契约。

仅作为固定比较目标时，本来就不要求从 Click 测试新建完整来源捕获链；上述 36-case 投影是未来来源契约工具的一项可选能力。它**不能解决根包导出和完整导入闭包**，也不能独自开启跨项目运行。

## 谱系独立性：当前支持程度

支持独立候选的证据强于仓库 `fork=false`：两边有不同历史根；Click 的 `style` 接口在 2014 年已独立存在，2019 年以 `_interpret_color`、tuple/list 解包及 ANSI 字符串实现 RGB；termcolor 于 2025 年加入 RGB，采用两处 tuple 分支与 `%` 格式化。选定 Click F 的受检源码/文档/元数据及提交标题没有查到 termcolor 引用，termcolor F 的受检源码/README/变更记录/元数据没有查到 Click 引用。[Click 历史 style](https://github.com/pallets/click/commit/f516eeecf79be6ed51a064e99f01a34a4aec7a75)、[Click RGB 历史](https://github.com/pallets/click/commit/5949dad4bd08ae6ba8ca241e5949474fd2fd54be)、[termcolor RGB 历史](https://github.com/termcolor/termcolor/commit/682cb16d7d98fa17fae83f216bdf6978a45c3cd8)

这支持“不是已知 termcolor 衍生”的工作假设；**不确定**之处是未穷尽作者讨论、所有分支和外部移植史，无法证明从未互相借鉴。RGB 元组、0–255 区间与 ANSI 控制码是通用格式语义，单看这些相同不能判定复制；不同根提交也不能排除借用。正式 cohort 仍要记录受检范围和审核者判断，不作绝对无借用声明。[Click 根历史](https://github.com/pallets/click/commit/4101de3daf91c6d35b92395a72bf84132ef48f7c)、[termcolor 根历史](https://github.com/termcolor/termcolor/commit/ec4bf7dd54ccb54002a62dc098d020fb73e6357e)

## 工程准入与实施边界

Click 根包并不是现有受限重导出 profile 所接受的单项静态导出：它导入许多子模块，并定义动态 `__getattr__`。`termui` 本身还导入其他 Click 模块、标准库与 gettext。直接诊断 `click.termui:style` 不能替代原测试 `import click; click.style(...)` 的公开入口绑定，也不能把一项 helper 的源码检查称为完整闭包准入。[Click F 根包](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/src/click/__init__.py)、[Click F termui 导入](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/src/click/termui.py#L1-L29)、[当前重导出实现](../../src/counterguard/static_exports.py)

Click F 具有现代项目元数据，但这不能消除导出与闭包问题。所需成本应分开估计：参数化静态字典展开属于有限语法扩展；原公开根包的完整安全准入属于独立功能设计，不能以“增加一条允许列表”处理。本调查不为后者给未经工程审查的人日估算，不实施 legacy profile。[Click F 元数据](https://github.com/pallets/click/blob/07c909f23f0f83b5ca137c167b9a134d66201f67/pyproject.toml)、[当前 bootstrap 检查](../../src/counterguard/bootstrap_plan.py)

建议决策：先保留语义可比性提案和消息策略反例假设；如果独立工程评审确认需要扩张导出/闭包范围，就提出有界设计后再确认实施。在此之前，继续寻找更小的独立 RGB 实现比绕过根入口、修改上游代码或通过包装器拦截并改写异常更合适。没有通过全部准入时保持未接纳，不能提前进入 Shadow 或研究执行。

## 可重复的只读复核

在 Click 的完整 clone 中读取固定对象；以下命令不运行项目代码：

```powershell
git rev-parse 07c909f23f0f83b5ca137c167b9a134d66201f67^
git show 07c909f23f0f83b5ca137c167b9a134d66201f67 -- src/click/termui.py tests/test_utils/test_style.py
git show 07c909f23f0f83b5ca137c167b9a134d66201f67:src/click/__init__.py
git show 07c909f23f0f83b5ca137c167b9a134d66201f67:pyproject.toml
git show 5949dad4bd08ae6ba8ca241e5949474fd2fd54be -- src/click/termui.py
git rev-list --max-parents=0 07c909f23f0f83b5ca137c167b9a134d66201f67
```

在 termcolor 的完整 clone 中：

```powershell
git show 520facb24e5310a6f48736dddfe86164057a322c:src/termcolor/termcolor.py
git show 520facb24e5310a6f48736dddfe86164057a322c:tests/test_termcolor.py
git show 682cb16d7d98fa17fae83f216bdf6978a45c3cd8 -- src/termcolor/termcolor.py
git rev-list --max-parents=0 520facb24e5310a6f48736dddfe86164057a322c
```

源码推导、规范审核、工程诊断、目标实测和正式研究标签是不同证据层。本次只完成前两项的提案核查，不声称后续环节已通过。
