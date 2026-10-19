# 五个 RGB 比较目标的一手接口调查

本调查只读取上游文档、固定 Git blob 与许可文本；没有导入、安装或执行候选项目。正式 preflight、完整导入闭包与是否接纳，以本批机器回执为准。**以下是可比性线索，不是已接纳样本或运行结论。**

队列限定为五个发行包：colorist、sty、ansicolors、colored、rgbprint。没有增加第六个候选，没有使用 validators 或 pytimeparse。比较目标不要求另有自己的 B/F/H；来源仍是既有 termcolor 修复。

## 来源 Guard 与映射边界

来源是 termcolor `colored` 的四种非法 RGB 元组 `(-1, 0, 0)`、`(0, 0, 256)`、`(0, 0)`、`(0, 0, 0, 0)`，分别传给前景、背景，共八个 case；每个 case 同时要求 `ValueError` 与消息 `Expected a tuple of 3 ints in range 0-255`。不能删去消息、修改来源 case，或让适配器自己拒绝输入来冒充目标拒绝。[固定来源测试](https://github.com/termcolor/termcolor/blob/520facb24e5310a6f48736dddfe86164057a322c/tests/test_termcolor.py)、[已审来源契约](../results/static-reexport-v1/termcolor-contract.json)

三个标量参数的接口可以讨论映射两个长度为三的越界元组；它**不能自动代表短元组、长元组**。若适配器在调用前解包失败，失败属于适配层。仅有前景接口，也不能把来源背景 case 改名前景后再计一次。所有映射数量只是静态可表达范围，尚未实现桥接或生成评测标签。

## 固定对象与官方源码解析

| 发行包 | 本次固定仓库与提交 | 官方源解析依据 |
|---|---|---|
| colorist | `jakob-bagterp/colorist-for-python` · `d23bee9dc3607e777f92a33df330243457d1b0ca` | [PyPI Source Code 与发布 provenance](https://pypi.org/project/colorist/) 指向该仓库；原拟议 `/colorist` 不是本次有效源码 URL，不能当作已成功重定向 |
| sty | `feluxe/sty` · `6f1774ef260be04bac356c101e3fca0ae5b38c70` | [PyPI](https://pypi.org/project/sty/)、[固定 README](https://github.com/feluxe/sty/blob/6f1774ef260be04bac356c101e3fca0ae5b38c70/README.rst) |
| ansicolors | `jonathaneunice/colors` · `c965f5b9103c5bd32a1572adb8024ebe83278fb0` | [PyPI](https://pypi.org/project/ansicolors/)、[固定 README](https://github.com/jonathaneunice/colors/blob/c965f5b9103c5bd32a1572adb8024ebe83278fb0/README.rst)；发行包名与导入名 `colors` 不同 |
| colored | `gitlab.com/dslackw/colored` · `f3d799873a7cde62f3c43d74ed6ffc258240d956` | [PyPI 安装说明](https://pypi.org/project/colored/) 明列 GitLab clone 地址；不把未经确认的 GitHub 同名地址当正式源 |
| rgbprint | `ddjerqq/rgbprint` · `d001f45bc5a527220f881b47ff85ac1dc191a5d4` | [PyPI](https://pypi.org/project/rgbprint/) 的项目说明与 [固定 setup.py](https://github.com/ddjerqq/rgbprint/blob/d001f45bc5a527220f881b47ff85ac1dc191a5d4/setup.py) 均指定该仓库 |

修正官方源码 URL 不增加候选数量。失败尝试与最终解析由本批回执保留；不能用最终成功覆盖首次失败。

## colorist：普通公开函数，逐通道拒绝，但消息不同

公开 `rgb(text, red, green, blue)` 与 `bg_rgb(text, red, green, blue)` 是普通顶层函数，分别构造 `ColorRGB` 与 `BgColorRGB`。不能因为内部使用类，就把用户入口描述成只支持构造器；也不能为了简化闭包，改选内部布尔 helper 作为等价用户接口。[前景函数](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/src/colorist/print/foreground/rgb.py)、[背景函数](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/src/colorist/print/background/rgb.py)

固定文档将各通道限定为整数 0–255。`RGB_ABC.__init__` 分别检查三个通道，越界时产生 `ValueError`，消息由通道名与值组成，和来源 Guard 的消息不同。这是“正确拒绝但消息不一致”的潜在合法差异，尚未经过独立裁决或 Docker 运行。标量入口只自然覆盖来源八个 case 中的四个三通道越界 case，长度错误仍缺映射。[固定 RGB 文档](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/docs/reference/extended-colors/rgb.md)、[拒绝实现](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/src/colorist/model/abc/rgb.py)、[消息实现](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/src/colorist/helper/error.py)

## sty：公开入口是可调用对象，底层函数不等于校验承诺

官方示例通过 `fg(r, g, b)`、`bg(r, g, b)` 生成 RGB 序列；`fg`、`bg` 是 Register 实例，靠 `__call__` 按参数数量分派。另有普通 `renderfunc.rgb_fg` / `rgb_bg`，其实现直接拼接参数。不能把低层渲染函数当成已经获准的输入校验入口，也不能仅凭没有范围检查就把返回值标成合法反例。[固定 README](https://github.com/feluxe/sty/blob/6f1774ef260be04bac356c101e3fca0ae5b38c70/README.rst)、[分派实现](https://github.com/feluxe/sty/blob/6f1774ef260be04bac356c101e3fca0ae5b38c70/sty/primitive.py)、[默认对象](https://github.com/feluxe/sty/blob/6f1774ef260be04bac356c101e3fca0ae5b38c70/sty/register.py)、[低层渲染实现](https://github.com/feluxe/sty/blob/6f1774ef260be04bac356c101e3fca0ae5b38c70/sty/renderfunc.py)

三标量 RGB 数据与来源有部分共同域，但短元组/长元组进入对象后的参数数量分派，不能由适配器替它作答。对越界输入是否存在项目认可的容忍规范，本次没有找到足够依据，结论为**不确定**；不新增缺陷或适用性标签。

## ansicolors：元组接口最接近，行为差异的性质尚待裁决

`colors.colors:color(s, fg=None, bg=None, style=None)` 是普通函数；README 明确支持三元素 tuple/list，各元素为 0–255。将来源前景和背景分别映射到 `fg` / `bg`，可以原样传递全部八个元组，无需先解包或补写 RGB 包装器。[固定接口与实现](https://github.com/jonathaneunice/colors/blob/c965f5b9103c5bd32a1572adb8024ebe83278fb0/colors/colors.py)、[固定规范](https://github.com/jonathaneunice/colors/blob/c965f5b9103c5bd32a1572adb8024ebe83278fb0/README.rst)

同一实现的 tuple/list 分支直接拼接元素，未见长度与范围检查。静态观察因此提供一个**可能缺陷**线索，而不是已经确认的合法反例；“文档描述输入域”也不必然等于“承诺所有域外值必须抛异常”。没有运行目标、没有新抓 Evidence，也没有删掉来源消息。该项目保留 setup.py 与旧式元数据的工程事实，需要按现有准入规则处理，不能借此重新启用已暂缓的 legacy profile。[固定 setup.py](https://github.com/jonathaneunice/colors/blob/c965f5b9103c5bd32a1572adb8024ebe83278fb0/setup.py)

## colored：有上游测试确认的夹紧语义，仍须工程准入

官方不仅有 `Fore.rgb` / `Back.rgb` 类方法，也公开普通函数 `colored.colored:fore_rgb(r, g, b)`、`back_rgb(r, g, b)`。此外 `colored.cprint:cprint(text, fore_rgb=tuple, back_rgb=tuple)` 接受 RGB 元组；不能把本候选误写为只有类方法。[固定普通函数](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/colored.py)、[固定 cprint](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/cprint.py)、[官方函数文档](https://dslackw.gitlab.io/colored/api/functions/)

`Utilities.is_percentage` 将整数转换后逐通道夹紧到 0–255；固定上游测试 `test_fore_rgb_clamping` 明确检查越界输入被夹紧后的 ANSI 序列。这为“拒绝要求不适用于这个目标”的合法差异提供了独立于来源 Guard 的依据。它**不是本轮已确认反例标签**：还缺谱系审核、具体来源 case 的映射裁决、工程准入与隔离运行。[固定规范见证测试](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/tests_pytest/test_colored.py)、[固定夹紧实现](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/utilities.py)

三标量函数只自然映射四个越界 case。若未来审查 `cprint` 作为映射入口，全部元组可保留，长度错误由目标内部解包处理；这与适配器先解包不同。两种入口不能混在一次计数中，选入口也不能依结果挑有利的一个。固定 `colored.py` 有模块末尾终端初始化与条件 ctypes 使用，完整闭包检查不能因 Linux 分支看似不执行就跳过。[固定入口及初始化](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/colored.py)

## rgbprint：公开普通函数接受元组，内部类不应被忽略

`rgbprint.rgbprint:rgbprint(*values, color=..., sep=..., end=...)` 是普通函数，公开支持 RGB 元组，并构造 `Color` 后写入 stdout。前景四个来源 case 可原样传递；没有找到与来源背景输入等价的 `on_color` 参数，不把同一前景执行复制成背景样本。[固定函数](https://github.com/ddjerqq/rgbprint/blob/d001f45bc5a527220f881b47ff85ac1dc191a5d4/rgbprint/rgbprint.py)、[固定 README](https://github.com/ddjerqq/rgbprint/blob/d001f45bc5a527220f881b47ff85ac1dc191a5d4/README.md)

内部 `from_iterable` 拒绝非三元素与越界值，使用不同的 `ValueError` 消息；`Color` 带有元类、重载声明及 TYPE_CHECKING 导入。普通用户函数不等于完整闭包已经支持；也不能为避开它们，把内部 helper 改称用户接口。消息差异可保留为潜在合法差异，但未裁决、未运行。[固定 Color 与转换实现](https://github.com/ddjerqq/rgbprint/blob/d001f45bc5a527220f881b47ff85ac1dc191a5d4/rgbprint/color.py)

## 许可与谱系的有限结论

| 候选 | 固定许可文件声明 | 与 termcolor 的有限谱系观察 |
|---|---|---|
| colorist | [BSD 3-Clause](https://github.com/jakob-bagterp/colorist-for-python/blob/d23bee9dc3607e777f92a33df330243457d1b0ca/LICENSE.md) | 受检 README、src、许可未发现 termcolor 衍生声明；实现以逐通道类校验组织 |
| sty | [Apache-2.0](https://github.com/feluxe/sty/blob/6f1774ef260be04bac356c101e3fca0ae5b38c70/LICENSE) | 受检 README、sty、许可未发现 termcolor 衍生声明；实现使用 Register 与渲染器 |
| ansicolors | [ISC](https://github.com/jonathaneunice/colors/blob/c965f5b9103c5bd32a1572adb8024ebe83278fb0/LICENSE) | 受检 README、colors、许可未发现 termcolor 衍生声明；另有 CSS 解析分支 |
| colored | [MIT](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/LICENSE.txt) | 受检 README、colored、tests_pytest 未发现 termcolor 衍生声明；有夹紧规范与独立项目文档 |
| rgbprint | [LICENSE 为 GNU GPL v2 文本](https://github.com/ddjerqq/rgbprint/blob/d001f45bc5a527220f881b47ff85ac1dc191a5d4/LICENSE)；setup.py 只写 GNU | 受检 README、rgbprint、tests 未发现 termcolor 衍生声明；类型转换与元类结构不同 |

“未发现声明”只描述上述固定范围的文本检查，不证明没有借用代码。未以仓库 `fork=false`、不同作者、不同根提交或不同许可证推导谱系独立；完整历史与代码来源仍需独立审核。rgbprint 的确切许可表达及未来再分发义务不能从模糊包元数据猜定；本调查不复制其实现进产品，也不把 GPL 文本本身解释成禁止只读研究。

## 目前可以支持的决定

候选与 RGB 领域的关系已经比泛输入校验搜索更具体，但“同一领域”“存在规范差异”“能被现有安全执行链接纳”是三个不同条件。colorist 的消息差异、colored 的显式夹紧测试，以及 rgbprint 的前景元组拒绝，均值得保留为语义线索；它们不替代本批 preflight、完整闭包和逐 case 适配审计。ansicolors 的域外透传不能直接充当合法反例，sty 的渲染器也没有已确认的拒绝契约。

这份调查不批准新增 profile、不启动候选代码、不要求目标建立新来源 Evidence，不产生新的 scope 标签。若五项都被现有工程准入阻塞，应按约定停止扩搜，提交明确的准入投入或研究范围选择，不能继续增加第六个候选来掩盖零接纳结果。
