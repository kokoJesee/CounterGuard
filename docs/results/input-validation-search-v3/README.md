# 现代小项目与 ULID/Base32 定点续查

本轮核查 **9 个新仓库**：先检查 6 个现代小项目，再定点检查 3 个 ULID/Base32 项目。
新增 1 条现代真实输入拒绝修复线索；另有 **1 个目标候选实际通过现有静态角色检查**。
仍没有形成完整来源/独立比较对，新增正式跨项目场景为 **0**。

基线为 `547797c915721fbcb9ddd02eff3d884370d25673`；产品源码没有变化。
[逐候选记录](../../../benchmarks/v2/rechecks/input-validation-search-v3.jsonl)区分一手文档、ZIP 提前预算与实际 Git/角色检查，
[汇总](summary.json)给出摘要、原断言投影、失败证据与 hex 对的独立跟进结果。原始下载、日志与方案保留本地。

## 实际进展

**base32-lib** 固定 `042eca9b370bc262cf3aac544ae3fee30c53b376`：
完整 Git 树 19 个文件，`base32_lib.base32:decode` 的现有 closure.v2 / direct 角色为 review_required、无 finding；
实际 `inspect_target` 已物化静态目标记录。
原 `tests/test_base32.py::test_decode_raises_for_invalid_string` 完整 2/2 条断言、2 case 可投影。
这些通过没有提供执行授权；相关历史的拒绝断言早已存在，未取得同属现代支持范围的真实来源修复。
其实现还明确引用 datacite/base32-url 和 jbittel/base32-crockford，不能把这些项目随意分成独立谱系。
[固定实现及归因](https://github.com/inveniosoftware/base32-lib/blob/042eca9b370bc262cf3aac544ae3fee30c53b376/base32_lib/base32.py)

**ulid-transform** 找到真实漏拒绝修复：
B=`07cccc36fbc9ef409f04abf0bdb41e636617b7db`，F=`1c55bb384a52df0eb43ea3bc9a1145ab16a131e0`，唯一父关系已核对。
补丁修复负数在 `(-0.001, 0)` 秒内被整数转换截为 0 后放行，新增 OverflowError 检查和原回归；两侧已有现代项目声明。
原测试同时依赖 `impl` fixture、`gen` 分发和多实现；实际 AST 投影为 0/1 条、0 case，原因 `fixture_or_default_argument_requires_review`。
父包还在二进制与 Python 实现间选择，不能静默选内部纯 Python 函数。
[真实修复](https://github.com/bluetooth-devices/ulid-transform/commit/1c55bb384a52df0eb43ea3bc9a1145ab16a131e0)、
[原测试](https://github.com/bluetooth-devices/ulid-transform/blob/1c55bb384a52df0eb43ea3bc9a1145ab16a131e0/tests/test_init.py)

已有 TTE → webcolors 线索另完成[六个输入的规范覆盖核查](../../research/hex-validation-comparability.md)：
输入可全部不变地传递，目标自有文档覆盖非法格式；仍有完整树预算、原测试投影和导入语法阻塞。
这不是新候选数，也不是获批合法反例或实际重放。

## 九项结果

| 固定仓库 | 触达边界 | 当前结论 |
|---|---|---|
| [more-itertools](https://github.com/more-itertools/more-itertools/tree/4aeb4338ae1407d8da9723e86da99efeb446f719) | 现代零声明依赖；ZIP 39 文件 / 692,033 bytes；原测试与根包 | 拒绝测试为 unittest，公开根包 wildcard；没有换入口 |
| [Toolz](https://github.com/pytoolz/toolz/tree/451af60dec590a6010e2babdbf391ea8f815122f) | ZIP 81 / 290,337；原测试和父包 | 自有 raises/lambda、动态父包；PR #628 是未合并的消息改进，原来已拒绝负数，不计新增漏拒绝修复 |
| [uri-template](https://github.com/plinss/uri-template/tree/3bcddb09fd53aaa72012abffea639e4585ed585b) | ZIP 22 / 91,900；显式零依赖、原测试 | JSON 循环/类驱动测试，未找到可提取真实来源修复 |
| [uritemplate](https://github.com/python-hyper/uritemplate/tree/8e46228e5a1ad3f688b21c6b3917d15dd0f7c581) | 固定 pyproject | 无 `[project]`，未测完整大小 |
| [roman](https://github.com/zopefoundation/roman/tree/6c0a134c091df4b63fc60c7e720fe1fb645f521d) | ZIP 19 / 24,370；ZPL-2.1、原接口和测试 | unittest、自有异常，未改成内置异常 |
| [roman-numerals](https://github.com/AA-Turner/roman-numerals/tree/adeca8ee3c4afbeb456ac3706ca459a0f3abc038) | ZIP 32 / 79,579；元数据在 Python 子项目 | 原入口为构造器/类方法，并有属性写删 hook；未添加包装器 |
| [python-ulid](https://github.com/mdomke/python-ulid/tree/6013ea5c58f0a0e83f3cf1f0eb2949c61cf1acb0) | 当前及 2.6 原元数据/测试/父包 | 当前有条件依赖；历史 2.6 无声明运行依赖，但有多函数分发、类方法和动态父包；未核实精确 B/F |
| [base32-lib](https://github.com/inveniosoftware/base32-lib/tree/042eca9b370bc262cf3aac544ae3fee30c53b376) | ZIP 19 / 36,636 后实际完整 Git/角色检查 | 静态角色无 finding，2 条原断言完整提取；现代来源修复仍缺，尚未配对 |
| [ulid-transform](https://github.com/bluetooth-devices/ulid-transform/tree/84bf45fd84fc51172c010038974d523a829376b8) | ZIP 49 / 190,255、真实历史 B/F、原测试投影 | 新漏拒绝修复存在；fixture/分发及动态实现选择未支持 |

ZIP 的 central directory 预算只用于只读预筛，不是 Git 对象完整性或最终准入证明。
其中 7 项做了固定 ZIP 预算；只有 base32-lib 后续实际使用 CounterGuard 完整提交读取器与角色检查。
工具自己的 Git/AST 进程不等于执行目标 Python。

## 更正与限制

- ulid-transform 官方仓库已重定向到 bluetooth-devices；它与 base32-lib 的当前 HEAD 都有 `[project]`。
  “它们仍是 setup.py-only”是未验证的旧推测，本轮已排除。历史 B/F 的元数据仍须分别读取。
- python-ulid 2.6.0 的元数据无运行时依赖声明，不能按当前 HEAD 的条件依赖否决整个历史；原测试和父包阻塞独立存在。
- base32-lib 的 2019 生成长度修复没有同提交新增回归，当时还依赖 six；不把现代元数据嫁接给旧提交。
- Base32 算法同名不证明与 128 位 ULID 完整契约可比；独立性、共同域和自身合规性没有通过审核。
- GitHub API 403 后转用官方固定 ZIP；TTE 延迟取 blob 的 TLS 失败保留，改用固定 raw 文本后逐 blob 哈希核对。
  本地 clone 首次因沙箱 Windows 权限失败，正常权限的新目录复制后通过；没有把权限失败当候选不兼容。

没有运行外部 Python、原测试或 Docker，没有 fork/H、标签、拟合或数据冻结。
只增事实材料，检查摘要、数量、链接、隐私与差异；未重复快层或全量。
正式数据仍为 insufficient_data；现有 profile 保持原样，接受范围变更必须另行确认。
