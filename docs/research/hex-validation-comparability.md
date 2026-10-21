# 两种 hex 颜色接口的只读可比性调查

这是一份候选调查，**没有目标执行、语义标签或正式跨项目场景**。
它接续[新候选回执](../results/input-validation-search-v2/README.md)，核对完整原输入能否映射到有独立规范的目标；
不是已经完成准入的声明。逐文件摘要、历史范围和诊断结果见[本轮汇总](../results/input-validation-search-v3/summary.json)。

## 固定来源与目标

来源为 TerminalTextEffects 的[真实修复](https://github.com/ChrisBuilds/terminaltexteffects/commit/b360e0723d2c8e88e7db4f98c162b99b87442bd9)：
B=`bb541505aa05d12e6f43d62d803b05836a5db09a`，F=`b360e0723d2c8e88e7db4f98c162b99b87442bd9`。
原入口是 `terminaltexteffects.utils.colorterm:fg`；原测试为
[`tests/utils_tests/test_colorterm.py::test_fg_invalid_hex`](https://github.com/ChrisBuilds/terminaltexteffects/blob/b360e0723d2c8e88e7db4f98c162b99b87442bd9/tests/utils_tests/test_colorterm.py)。
它有一条 `ValueError` 加字面量消息 `Invalid RGB hex color code` 的断言，参数表完整包含六个输入。
没有将背景函数重复计为另一个独立修复，也没有仅保留预计会漏拒绝的参数。

比较目标固定为 webcolors `6c8da6832eb4ae2591a1883a0d1371263d6cd4db` 的公开 `webcolors:normalize_hex`。
它将合法 hex 表示规范化；来源函数将颜色转换成 ANSI 序列。两者的成功返回格式不同，
**不能宣称通用可替换**。这里只核对原 Guard 所断言的非法 hex 输入拒绝行为，成功输入与输出等价性不在这份提案中。

## 六个原输入的规范依据

webcolors 的[固定格式文档](https://github.com/ubernostrum/webcolors/blob/6c8da6832eb4ae2591a1883a0d1371263d6cd4db/docs/conventions.rst)
只接受 `#` 后接 3 或 6 个十六进制字符；其[函数文档](https://github.com/ubernostrum/webcolors/blob/6c8da6832eb4ae2591a1883a0d1371263d6cd4db/src/webcolors/_normalization.py)
规定无法解释为合法颜色值时抛 ValueError。独立于来源 Guard 的[上游拒绝测试](https://github.com/ubernostrum/webcolors/blob/6c8da6832eb4ae2591a1883a0d1371263d6cd4db/tests/test_normalization.py)
使用消息片段 `not a valid hexadecimal color value`。

| 原输入（全部保留） | 不符合目标格式的原因 | 调用表示 |
|---|---|---|
| `fgffff` | 无前导 #，且含非 hex 字符 g | 原字符串作为唯一位置参数 |
| `fffff` | 无前导 #，长度不符 | 同上 |
| `ffffff0` | 无前导 #，长度不符 | 同上 |
| `#ffffffjunk` | 包含尾随非 hex 内容 | 同上 |
| `ffffff#` | # 位于末尾 | 同上 |
| `##ffffff##` | 多个 # | 同上 |

没有补文本参数、改关键字、截断字符串、代替目标校验，或删消息来制造一致。
目标文档的格式规则覆盖全部六个输入；这解决的是规范覆盖问题，**还没有证明实际目标运行满足该规范**。
目标测试的独立消息要求与来源要求不同，可作为待审适用性差异的依据；不能先看 Guard 失败再回填标签。
实际最小失败集仍必须由获批后的真实 B/F 捕获确定，本轮没有预测并保存一个虚假的失败集。

## 来源独立性的有限核查

对固定 F 的可达提交，TerminalTextEffects 为 1877 个，webcolors 为 352 个，共同提交为 0。
受检根提交分别为 `5fa0652957dbed6d457f8bb89e8e15dda7fe191f` 与 `7ca0061d49524f72f7a9ab7752110580c0990923`。
前者使用不含媒体 blob 的过滤 clone，仅用于提交历史与逐文件只读诊断；它不通过完整对象准入。
不同历史不证明没有代码借用。完整谱系、接口 cohort、适用性与自身契约合规审核仍未批准。

## 只读调查阶段的阻塞

- 来源完整固定树仍为 108,610,617 bytes，违反现有 8 MiB 全树与 1 MiB 单 blob 限额；没有删除媒体。
- 原 `pytest.param` 字面量表在现有提取器中为 unsupported，不能改写原测试后冒充机械提取。
- 补查 26 个被选中 Python 文本并逐一校验 Git blob 哈希，仅用于导入形状诊断，**不是完整树准入**。
  结果仍为 unknown，3 个文件出现保守 finding：`base_config.py` 的 dataclass 属性查找、`argutils.py` 的 argparse 属性读写，
  以及 `terminal_input.py` 的 `re.compile`。这是三份文件的语法 finding，不是三个已证实漏洞；`re.compile` 也不是内置 Python compile。
- webcolors 现有角色检查仍因保守 `re.compile` 名称匹配与 evaluated annotation 为 unknown。

因此，在该次只读调查所用的旧 profile 下，增加容量、补 `pytest.param` 或识别标准库 regex 中的任何单项，
都不足以解锁完整来源链。该轮没有修改默认 profile、创建 H、签执行授权或运行外部 Docker。

后续建立了独立、版本化的完整快照外部观察用途，并先通过工具自有 fixture 资格；
[固定 TTE → webcolors 观察](../results/tte-webcolors-observation-v1/README.md)随后保留全部六个输入完成双向捕获、
最小 Guard 自检和两类目标重复观察。旧 profile 的阻塞和结论没有被改写为通过。
