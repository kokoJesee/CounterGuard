# 输入校验候选核查

结论：本轮按指定优先级核对 7 个仓库，再补查更接近 RGB 共同输入域的 Click。
发现 **4 个具有漏拒绝补丁的上游线索，但新增可接纳目标为 0**。
现有 termcolor 来源闭环仍为 1，完整跨项目场景仍为 0；研究桥接、学习和数据冻结没有启动。
“找到补丁”来自 Git 源码核对，不能写成已在 Docker 复现。

实现基线 `31910800f7b44cb592f71e64a72428f4ba79f0c5`，产品代码最后变更为
`c1a2d24bc271e8d482644f61c1c338e4a41e9b2a`。本轮没有扩大 profile 或修改产品代码。
逐项 SHA、源码/许可 pin、18 次静态角色评估、8 次 CLI preflight、4 次 AST 测试投影和摘要见
[机器记录](../../../benchmarks/v2/rechecks/input-validation-search-v1.jsonl)；[边界核验](audit.json)另列保护项。

## 查找与停止规则

1. 优先复查池中原先 preflight 为 0 的 textcase、luhncheck，再依次核对 pathvalidate、semver、isodate、luhn、base58。
   这两项 preflight 0 本轮已重新实测，不能解释成来源捕获或执行授权通过。
2. 只保留“非法值此前被接受、补丁新增拒绝”的来源线索；异常改返回 False、错误消息修正、兼容性修复分别记录。
3. 对历史 B/F 分别读取完整 Git 树和角色闭包；现代 HEAD 的元数据不能移植给历史提交。
4. 核对独立来源、真实测试、共同输入域、调用与 oracle；同属输入校验不自动属于同一可比 cohort。
5. validators 按维护者要求不再使用；pytimeparse 按维护者明确要求排除，没有重新采集或作新的许可判断。
   不使用 termcolor 衍生仓库。原始日志、本机路径和安装环境不公开。

没有 checkout、import、安装候选代码或执行上游测试，也没有创建新 fork/H、运行 Docker 或补签执行授权。
预检、AST 分析使用工具自己的 Python/Git 进程；**外部目标 Python 执行数为 0**。

## 逐项结果

| 顺序 | 候选 | HEAD preflight | 本轮处置 |
|---|---|---:|---|
| 1 | textcase | 0 | 已查真实转换修复不属于本轮漏拒绝方向；snake 为 callable-object，定义角色仍 unknown |
| 2 | luhncheck | 0 | HEAD 普通函数角色无 finding；历史校验补丁 B/F 均 legacy 元数据 unknown；现成测试是异常 → False |
| 3 | pathvalidate | 4 | 找到非法路径漏拒绝及改写的回归断言；历史/HEAD 元数据、完整闭包、类方法投影均未通过 |
| 4 | python-semver | 5 | 找到尾换行/非 ASCII 数字拒绝及新回归测试；HEAD/B/F 整树均 symbolic_tree_entry，停止角色评估 |
| 5 | isodate | 4 | 找到尾随垃圾字符拒绝补丁；选定 F 未改测试，历史元数据、动态测试及完整闭包仍不支持 |
| 6 | luhn | 4 | 已有来源是 Python 3 map 可切片修复，不是漏拒绝；历史元数据支持也未开放 |
| 7 | base58 | 4 | 已审消息修复在 B 就拒绝非法字符；不把新消息当新增校验，Hamcrest/legacy 边界保留 |
| 8（补充） | Click | 4 | 找到 RGB 范围/类型拒绝修复；原测试参数展开不支持，完整运行闭包 unknown |

严格 preflight 与 standalone source-only 不是同一道检查：测试配置/缺少显式 dependencies 的 preflight 4
不必然否决 source-only，故本轮还分别做了实际角色评估。反过来，静态闭包无 finding 也不是人工审核、H 或执行授权。
表中的最终阻塞以逐角色结果为依据，不只是复述 preflight。

### pathvalidate：真实路径漏拒绝

B=`d1c58d2c6f2a6b8d9e316ff21c5fd572766833a7`；F=`9c0b77ef1f75b2eeca31a23c71153a2901b47b65`，父子关系已核对。
修复把每个路径分量交给文件名验证器，Windows/universal 的尾点、尾空格从允许变为拒绝；Linux 的合法输入仍保留允许。
原测试的同一组平台语义不能混成“所有尾空格都非法”。
[补丁与测试](https://github.com/thombashi/pathvalidate/commit/9c0b77ef1f75b2eeca31a23c71153a2901b47b65)

F 的 `Test_validate_filepath.test_exception_space_or_period_at_tail` 使用 `ValidationError` 和布尔校验双重断言。
实际投影返回 `Select one top-level test function present exactly once`，不是受支持的顶层函数。
自定义异常也未获当前 oracle 支持，不能改成更宽的 ValueError；`is_valid_filepath` 入口不能用来绕过原断言。
HEAD/B/F 实际角色评估都有 legacy_install_code_requires_review、project_metadata_unavailable、动态查找、
导入状态和未获审的 ntpath/posixpath 等 finding。这里的 unknown 不证明代码恶意，只说明当前审核能力未覆盖。
HEAD/F 有 MIT LICENSE pin。

### semver：类型符合，但完整树拒绝

B=`0f18aa0b1e0cabba65ee1b506e637faabcdf5d05`；F=`1e8757912f633684e1a65d9d7c7e2270c3c79928`，父子关系已核对。
F 将正则末尾 `$` 改为 `\Z` 并加入 `re.ASCII`，新增 `tests/test_strict_parsing.py`，
明确拒绝版本尾换行与嵌入的非 ASCII 数字。
[补丁与测试](https://github.com/python-semver/python-semver/commit/1e8757912f633684e1a65d9d7c7e2270c3c79928)

完整树的 `tests/coerce.py`、`tests/semverwithvprefix.py` 为 mode 120000；HEAD、B、F 都被正式读取器拒绝。
没有删除链接、只拣 src 或扩张安全策略。后续的运行闭包/投影**未执行**，不能写成通过。
只读查看补丁还发现公开测试调用 `Version.parse` / `Version.is_valid` 类方法，这超出普通函数 target 的表示范围；
即使解决整树边界，也不能跳过该限制。LICENSE.txt 为 BSD-3-Clause；F 的提交文本公开含 AI 协作署名，
本轮已读其测试，不把它当未见留出。

### isodate：真补丁不等于已有可提取回归契约

B=`b9917aff3319ec112cf59c1f5ca84fa1bd3a7538`；F=`2e68c720d50806b91b3d025eb5cbafd3a0957b44`，父子关系已核对。
日期正则新增 `\A` / `\Z`，同一分支后续 `4f422ae415e8c9591677b97faf0776ece6d7afb8` 对时间作类似更正。
这里只选择前一个日期修复，不把相连补丁凑成多个独立场景。
[日期补丁](https://github.com/gweis/isodate/commit/2e68c720d50806b91b3d025eb5cbafd3a0957b44)、
[时间补丁](https://github.com/gweis/isodate/commit/4f422ae415e8c9591677b97faf0776ece6d7afb8)

日期 F 只改 `isodates.py`；原测试是工厂生成 unittest 类和 test_suite，不是字面量顶层断言。
实际选择 test_suite 的投影为 0 case、no_assertion_syntax，不能当作“没有测试”或自动新写一个 oracle。
异常 ISO8601Error、现行 HEAD 的 isodate.version 构建生成文件缺失、完整闭包的动态查找/模块钩子，
以及历史 B/F 的 setup.py 和项目声明缺项分别保留为阻塞。没有生成版本文件或运行构建来消除 unknown。
HEAD 有 BSD-3-Clause LICENSE；旧 F 无独立 LICENSE 文件，但源码含 BSD 风格许可头，旧版许可审计未完成，
不将“缺独立文件”直接推导为无许可。

### luhncheck / luhn / base58：避免错算缺陷与独立性

luhncheck 的 F=`5142c55264930de138cccfd1e5e55e09ac27dbf8` 新增 isdigit 拒绝。
固定测试 `"110179827B"` 在 B 是转换异常，在 F 是 False，不能算“原先接受”。
空串在 B 为 True、F 为 False 是源码推导，但受检的 10 个历史测试 blob 无对应字面量；本轮没有补写。
实际 F 测试投影 1/1 条、9 case 仅证明语法支持，不证明满足本轮缺陷条件。
[详细调查与范围](../../research/luhncheck-input-validation.md)

此前 [data card](../../experiments/scope-v2/data-card.md) 给出的 Luhn verify ↔ luhncheck 比较只是一份提案。
本轮发现较早核心实现有显著文本相似性，借用/共同来源**不确定**；在独立性审计完成前不能形成独立项目对。
luhn 的既有 map → list 修复只解决 Python 3 兼容性，不换标签充数。
[Luhn 修复](https://github.com/mmcloughlin/luhn/commit/b611e357da3a5e17abf9b8dfe40b111eb1cdc50d)

base58 本轮查看 HEAD 可达提交标题（136 个）及选定的非法字符测试/消息补丁，未找到满足本轮条件的现成 B/F。
新增 `test_invalid_input` 的提交只加测试；消息补丁的 B 已从 KeyError 转换成 ValueError。
这不是对所有分支、所有行为“没有缺陷”的证明。
[新增测试](https://github.com/keis/base58/commit/8b6cd321ddb4e48bf926c8352ed302e3b4809cb8)、
[消息更正](https://github.com/keis/base58/commit/92b69a814826c34146f4ec84205b1cc88556f782)、
[既有转义更正](https://github.com/keis/base58/commit/04e0182bc83d1f6c2e4edc6be330f50492791ba8)

### 补充 Click：最接近现有 RGB 来源的线索

指定队列查完后，另发现 B=`7925a3410d7098c28cfca3b2baa6c852666bbd14` →
F=`07c909f23f0f83b5ca137c167b9a134d66201f67`，父子关系已核对。
旧 `_interpret_color` 会直接格式化越界 RGB；F 新增 0–255、长度、整数且排除 bool 等校验。
`test_styling_invalid_color` 包含 `(-1,0,0)`、`(0,256,0)` 等非法 RGB，并检查 ValueError 的 `"Unknown color"` 消息。
这些与 termcolor 的无效 RGB 范围有自然共同域，优于仅按“输入校验”把路径和版本号硬凑在一起。
这是源码依据，尚未双向执行验证。
[固定补丁与测试](https://github.com/pallets/click/commit/07c909f23f0f83b5ca137c167b9a134d66201f67)

两项独立工程边界仍在：

- 实际 AST 投影为 0/1 条、0 case，原因 argument_expansion_requires_review：原调用为 `click.style("x y", **{param: value})`。
  现有 match 支持已足够表达其消息，不能因此偷偷支持动态 kwargs 或只抽出 RGB case 后声称完整原测试已投影。
- HEAD/B/F 普通定义 `click.termui:style` 的完整闭包均 unknown，含模块钩子、动态导入/查找、资源访问和未审导入。
  root package 也不是当前一条显式导出的受限模型。严格 preflight 另报 conftest 和 examples 子项目依赖；
  不需要运行原 conftest 的 source-only 路径仍有上述实际闭包阻塞，不能混淆两者。

Click 有 BSD-3-Clause 许可及自己的历史 RGB 支持，未发现它是 termcolor 衍生的证据，但代码借用谱系全面审计未完成，
不能仅凭 GitHub 不是 fork 宣布已独立。消息、参数名 fg/bg 与 color/on_color、force_color 环境也有差异。
这些差异可能形成待核实的合法反例或受限调用适配提案，**不能预先贴 applicable / inapplicable 标签**。

## 可比性与下一步

termcolor 已发布的最小 Guard 含完整 ValueError 消息，不能删 match、换成宽异常、把字符串/路径强转为 RGB 来制造可迁移性。
“不同消息”本身也不要求排除目标：需要先按各自规范审共同域与调用，再决定是否是合法反例；
规范差异、真实缺陷与基础设施失败必须分开。本轮没有给任何目标分配研究标签。

后续优先保留 **termcolor ↔ Click 的 RGB 共同域提案**，其次保留 semver 的真实严格解析修复作另一个来源方向。
这两项都不能在当前 profile 下直接执行。若继续仅用现有能力，就继续筛更小的独立 RGB/范围校验实现；
若要优先接入 Click，需要另外设计、审核参数展开投影和完整源码闭包支持，不能只放开一个 kwargs 语法就宣称接入完成。
legacy profile 继续不实施；也不因累计候选不足把旧 validators、工具 fixture 或同族近重复塞进研究。

## 可重复核对

逐项完整 URL、HEAD/B/F、definition_target、source_ref、import_root 均在机器记录中。使用上述工具实现版本、完整 clone，
不 checkout 候选，输出须放在 clone 之外的新目录。预检不执行候选代码：

```powershell
git -c core.hooksPath=<trusted-empty-hooks-directory> clone --no-checkout <repository-url> <candidate-clone>
counterguard preflight --repo <candidate-clone> --revision <full-head-sha>
git -C <candidate-clone> rev-parse <full-fixed-sha>^
git -C <candidate-clone> diff --name-only <full-buggy-sha> <full-fixed-sha>
git -C <candidate-clone> ls-tree -r <full-revision-sha>
git -C <candidate-clone> show <full-revision-sha>:<source-or-test-ref>
```

直接定义的诊断评估不是合法 contract/binding。其复核方式如下（在工具工作目录的 Python 环境中运行）：

```python
from pathlib import Path
from types import SimpleNamespace
from counterguard.repository import read_committed_files
from counterguard.bootstrap_binding import _runtime_assessment

_, files, pins = read_committed_files(Path("<candidate-clone>"), "<full-revision-sha>")
report = _runtime_assessment(files, SimpleNamespace(
    target_module="<definition-module>", target_symbol="<ordinary-function>",
    source_ref="<definition-ref>", import_root="<import-root>",
))
print(report)
```

读取器先拒绝时必须停止，不能改用不受限的读取结果继续上述角色评估。
机器记录列了原 preflight stdout/stderr 摘要与完整 findings；本地保留实际原文，没有因日志含本机路径公开它们。
私有投影核查脚本首轮因 DraftUnsupported JSON 序列化失败，修正脚本后重验；产品源码和判断标准未改，首轮失败记录保留。
本轮只增加调查材料，未重跑快层、全量或 Docker；文档链接、摘要、保护项、隐私和 Ruff 按 audit 实测结果报告。
