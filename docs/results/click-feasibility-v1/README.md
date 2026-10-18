# Click RGB 目标的定点可行性评审

结论：**Click 有自然 RGB 共同域，但接入成本明显超出一项测试语法补丁；本轮不实施 Click profile 扩张。**
优先保留固定目标提案，继续按现有能力寻找较小独立实现。当前已验证来源修复仍为 1，已接纳独立比较目标和完整跨项目场景均为 0。

本轮只有只读规划、Git/AST 诊断和文档，外部目标执行数为 0。没有安装依赖、执行上游测试、启动 Docker、创建 fork/H、生成可执行契约、分配研究标签或修改生产准入。
产品源码版本仍为 `c1a2d24bc271e8d482644f61c1c338e4a41e9b2a`，本轮基线提交为 `443d88f7e01724876a7e6029e2247b7057cbef01`。

语义与谱系的一手依据见[专项调查](../../research/click-rgb-contract-comparability.md)，
逐行检查结果见[诊断数据](diagnostics.json)，保护项核验见[audit.json](audit.json)。前一轮的[候选核查](../input-validation-search-v1/README.md)保留。

## 来源和比较目标分别需要什么

来源 Guard 已有 termcolor 的真实 B/F、所有者 H、Docker Evidence 和最小失败断言。
**比较目标不需要再找到自己的缺陷修复 B/F，也不必新建来源 Evidence/Guard。** 本次 Click B 只帮助解释上游补丁，不是目标资格的额外门槛。

比较目标需要：独立固定提交、许可和受检谱系依据、自身行为规范、与来源输入的语义比较及受审调用映射、完整安全准入。
它的自身行为可由既有测试/规范给出，不要求先把全部上游测试转换成新的来源契约。
未来研究桥接还须定义目标快照和执行授权，不能直接改生产 Guard 的仓库、入口或精确快照 Scope。

这也不放宽来源契约必须来自 H 的要求。任何走现有 standalone capture 的新来源，都继续经过原 B/F/H 路径；
没有一个“目标”开关可让外置契约绕过该安全检查。研究目标描述是尚待实现的独立版本化输入，不是已有命令的执行许可。

## 语义可比性

优先讨论 Click F=`07c909f23f0f83b5ca137c167b9a134d66201f67`，不混用当前 HEAD。
其 B=`7925a3410d7098c28cfca3b2baa6c852666bbd14`，父子关系与补丁已核对。
共同域先限于普通文本、单侧前景/背景、整数 RGB 元组；非法域为长度错误或分量越界。

| 项目 | 明确提案 | 当前状态 |
|---|---|---|
| 调用 | termcolor `color/on_color` 映射到 Click `fg/bg`，文本保留原 case | 未实现、未授权执行 |
| 着色条件 | termcolor 的 force_color=True 是来源到达校验的设置；Click.style 直接构造 ANSI，不接收该参数 | 不可盲传所有 kwargs，也不可用适配器篡改异常 |
| 行为 oracle | 保留来源 ValueError 和完整字面量 match；另核对 Click 自身 Unknown color 断言 | 不删消息、不将不同消息自动贴为 inapplicable |
| 合法反例假设 | Click F 合法拒绝相同无效 RGB，却不满足来源专属消息 | 规范支持的待审假设；尚无 Docker 证据或正式标签 |
| 谱系 | Click RGB 历史早于 termcolor RGB，受检实现与历史不同 | 支持独立候选；未穷尽外部借用史，不作绝对独立证明 |

如果这个合法反例成立，验证的是**消息策略被错误迁移后的适用边界**，不是 Click 未拒绝非法 RGB。
只有这种负例还不足以支撑跨项目缺陷检出收益；留出 true_bug 分母为零时必须报告 null，不可借来源自检填补留出分母。
不能为了主结论好看另删 match 或事后重写标签。本文没有裁决标签或修改研究主张。

## 实测阻塞：逐层分开

### 正式只读入口

本轮实际运行现有 `bootstrap plan`，公共目标为 `click:style`，固定 F、原测试 `test_styling_invalid_color`：

- 退出 **4**，plan.status=blocked，execution_allowed=false，execution_outcome=not_run。
- 原测试 1 条断言，当前代表 0 条、0 case；argument_expansion_requires_review。
- 目标闭包为 unknown、16 个 Python 模块。单次计划命令耗时 5.71 秒；不是接入总耗时。

原测试有两个参数轴：2 个参数名 × 18 个值，理论调用数为 **36**。AST 形状可静态确定，但当前提取器未实现这项语法；
不得把“可讨论的 36 个调用”报成“已成功提取 36 case”。仅作为比较目标，这项来源提取能力是可选项。

### 公开根入口绑定

实际调用现有 `resolve_static_reexport` 得到 `export_root_statement_unsupported`。
Click 根包有多个子模块导出和 `__getattr__`，超出一条根包导入到普通直接子模块的 grammar。
`click.termui:style` 的直接定义诊断不能替换原测试的 `click:style`；导入子模块同样先初始化包。
不能复制 helper、伪造包初始化、改上游源码或通过包装器修正异常来绕过它。

### 完整导入闭包

固定 F 的 16 个模块合计 **398,787 字节、11,470 个物理行、44,496 个 AST 节点**。
当前检查器产生 **30 条 finding**，按 `(code, path, detail, severity)` 去重；另定位到 58 处对应语法触发点。
这不是“30 个已发现漏洞”或“58 个运行效果”。逐行路径、作用域、表达式和源码 pin 均在诊断数据里。

| finding 类别 | 数量 | 具体依据 / 仍需做什么 |
|---|---:|---|
| dynamic_code_or_lookup_requires_review | 5 | 包含 `re.compile` 和真正的 getattr；需分辨解析身份与动态查找，不能一律认为是 exec |
| dynamic_import_framework_requires_review | 2 | 根包兼容钩子、版本选项回调中的 importlib.metadata；不能未经证明就删除路径 |
| import_state_mutation_requires_review | 4 | 现有规则也匹配赋值 RHS 中的 os.path、sys.modules 读取；这些位置本身不证明修改导入状态 |
| module_lookup_hook_requires_review | 7 | 包含真实模块级钩子，也匹配多个类的 __getattr__；需要准确区分作用域 |
| resource_or_native_access_requires_review | 3 | 存在文件打开、终端/编辑器等资源访问语法；没有数据流或可达性证明支持裁剪模块 |
| unresolved_or_external_import | 9 | msvcrt、termios、typing_extensions 的逐文件导入记录；部分位于平台/类型分支，不能直接等同 Linux 安装需求 |

例如 `_compat.py` 的 `tmp_filename = os.path.join(...)` 和 utils 的 `_main = sys.modules["__main__"]`，
会命中现有“状态变更”保守规则。修正诊断精度值得独立设计，但即使去掉这些触发，也没有解决其他运行闭包问题。
同样，发现类钩子不证明模块钩子；辨明这一点不能成为忽略根包真实 `__getattr__` 的理由。

本轮不改检测器、不修改允许列表，不静态计算上游条件后把未证明路径裁掉；现有 profile 继续 unknown。
没有因为 Docker 提供隔离就绕过上游准入，也没有根据这些保守 finding 指控 Click 不安全。

### 特征表达与研究执行桥接

本轮直接调用当前 `extract_ast_features`，结果如下：

| 固定输入 | 当前结果 | 含义 |
|---|---|---|
| Click F `style` | 仅 `branch:none` | token 表示参数与 None 比较；不代表无分支，也未表达 helper 中的 RGB 校验 |
| Click F `_interpret_color` | unsupported | 含 GeneratorExp，超出 ast-features.v1；不能用人工填 token 代替 |
| termcolor F `colored` | unsupported | 同样超出既有特征 grammar；来源捕获成功不等于 learner 已能消费它 |

还诊断了 Click B，结果独立保存，不将其来源/目标角色混用。
这说明研究桥接需要自己的特征和输入规范，不能把现有 v1 protocol 的 Literal、预期计数或词汇表松开就运行新数据。
该设计属于研究桥接工作；**不要求在候选阶段提前实现整个研究评测器**，也不将它变成循环的准入条件。

## 如果选择接入，工作包与成本

以下是基于当前代码的工程初估，不是实测耗时或交付承诺；验收应先验证必要项，再决定是否继续投入。

| 工作包 | 比较目标是否必须 | 量级初估 | 验收要求 |
|---|---|---|---|
| A：受限静态 `**dict` 提取 | 否；需要把 Click 测试变成新来源契约时才做 | 1–2 人日 | 完整 36 调用语义、无 eval；动态键/调用/非字符串/冲突/重复键/预算拒绝；旧投影不变 |
| B：多导出根包的显式符号绑定 | 使用 click:style 时必须 | 1–2 人日 | 新 profile 逐快照 pin；保留初始化器，动态/重绑定不能蒙混通过；直接定义不能冒充公共入口 |
| C：完整包的受控闭包评审 | 必须 | 5–10 人日，不确定 | 区分作用域/读写/平台与类型分支；逐项审核真实效果；仍未知则拒绝，Docker 攻击 fixture 和异常路径须实测 |
| D：独立研究目标/调用适配/执行桥接 | 跨项目研究执行必须，属于原研究桥接范围 | 2–4 人日初估 | 精确目标快照、公开入口、源 Guard、映射、环境和审核镜像 pin；不改变生产 snapshot Scope |
| E：研究特征表示 | 学习研究必须，属于桥接设计的一部分 | 2–4 人日初估，可能与 D 重叠 | 新版本 extractor/context；helper/生成器或明确不支持；逐行对账、无标签/身份泄漏、20 次乱序确定性 |

Click 的必要准入项 B+C 合计初估 **6–12 人日**，还不含研究桥接、人工等待或未发现问题；不是补 A 的 1–2 人日。
C 中对现有规则精度的改进、条件分支/真实资源能力支持边界，以及独立安全审核时间尚不确定。
若选定范围必须进一步支持任意动态导入、安装依赖或执行 conftest，则超出本提案，应停止并重新讨论范围。
没有因为数据不足自动批准这组工作包。

## 摘要和重新物化范围

本轮只改文档和新增诊断数据，产品 implementation_digests、冻结数据、旧 artifact、现有来源 H 与发布标签不变，
不需要重新物化来源 Evidence/Guard。

若以后修改 CounterGuard 包中任何 Python 源码，`inspection_implementation_digests()` 会绑定整个包，
现有绑定/执行链可能因当前源码不匹配而失效，即使变更名义上只是“诊断优化”。需要分别列出：

- 源码身份变化：按新实现生成新 plan/binding、授权及需重验的 Evidence/Guard/Registry 派生记录；不覆盖旧产物。
  契约内容和投影未变且旧模型仍受支持时，可重新核对并复用原 H，不为更新工具源码伪造新 H。
- 接受范围/投影含义变化：新增 profile 或契约/绑定版本，禁止旧版本默默放宽。是否需要新的所有者契约提交取决于实际内容变化。
- 研究数据/特征/映射变化：新 study 版本重新物化目标 pin、特征、split/protocol 和下游 Scope/replay/report，
  与已冻结 scope_v1 分开；不得回写标签或通过改期望值追平结果。

旧记录仍证明历史事实；当前核验拒绝时不能改摘要让它变成“仍通过”。所有实际重算范围必须在实施前按依赖表核定。

## 决策和下一步

本轮完成 Click 的有界静态评审，**暂停它的执行接入，保留比较提案，不实施 A–E**。
理由是已有来源不缺，当前缺的是低成本、安全可审的目标；Click 的准入投入较大，且现有完整 oracle 首先测到消息策略差异。

下一轮仍按维护者已选择的现有 profile，做**最多 5 个较小独立 RGB/整数范围校验目标的有界筛查**：

1. 先读固定许可、元数据、公开函数和包初始化；明显需要 legacy、类方法或动态根导出时停止，不追完整历史。
2. 通过后只核对与来源 8 个输入的共同域、自身规范和调用；保留消息 oracle，不要求目标另有 B/F/H 来源链。
3. 再检查完整树/闭包和精确 runner 前置。可审材料全过后，另在研究桥接设计中解决目标执行，不走本地解释器。
4. 这批结束仍为 0 时，停止同方向扩搜并向维护者提交范围选择：继续投入通用包准入，或缩窄研究主张。
   不自动切换同项目探索轨、不宣称跨项目验证完成，不把候选名或 case 数充当独立场景数。

## 重复命令和验证边界

使用上述 CounterGuard 实现版本及 Click 完整 clone；输出目录必须全新、位于 clone 之外。

```powershell
counterguard bootstrap plan --repo <click-clone> --revision 07c909f23f0f83b5ca137c167b9a134d66201f67 --target click:style --import-root src --test-ref tests/test_utils/test_style.py --test-function test_styling_invalid_color --output <fresh-plan-directory>
```

预期现行版本退出 4；应查看 status、target_closure、test_projection 和 execution_allowed，而不是只看文件存在。
静态导出和特征可在工具自己的 Python 环境中核对（不 import Click）：

```python
from pathlib import Path
from counterguard.repository import read_committed_files
from counterguard.static_exports import resolve_static_reexport
from counterguard.features import extract_ast_features

_, files, pins = read_committed_files(Path("<click-clone>"), "07c909f23f0f83b5ca137c167b9a134d66201f67")
# 分别调用，分别记录成功或明确拒绝；一个抛错后不能把后续未调用项记成已测。
resolve_static_reexport(files, module="click", symbol="style", import_root="src")
extract_ast_features(files["src/click/termui.py"], "style")
extract_ast_features(files["src/click/termui.py"], "_interpret_color")
```

纯文档/诊断交付按 audit 核对源码身份、冻结输入、摘要、链接、隐私及 Ruff，不跑全量或 Docker。
私有诊断脚本有两次失败：未捕获工具自定义 FeatureExtractionError，以及错误假设 B 含 F 新增测试；
分别修正脚本后完整重验，首轮原始记录保留。未更改产品异常、测试、上游源码或判断标准。
