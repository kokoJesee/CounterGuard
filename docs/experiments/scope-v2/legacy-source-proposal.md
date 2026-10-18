# 旧式源码项目的受控接入提案

状态：**维护者已选择继续按现有 profile 采集，本提案暂不实施；不是已实现功能，也不构成运行授权**。依据是[两批来源探测](../../results/scope-study-feasibility-v2/README.md)，不是对生态兼容率的估计。

## 要解决的具体问题

mmcloughlin/luhn 的真实 Python 3 修复有可投影的 checksum/verify 断言，目标模块没有导入；当前 source-only 仍因 setup.py 和缺少 PEP 621 元数据为 unknown。现代 luhncheck 已提供一个布尔校验比较目标提案。但这两点还不能证明跨项目可行性成立。

Luhn 的 setup.py 会 open 源码/README 并从正则提取版本。**不建议执行 setup.py，或把整个脚本宣称成“可静态求值”。** 本提案只考虑一个独立的、显式选择的源码闭包 profile，构建/安装脚本始终不执行。

## 拟议最小设计

1. 保留既有 profile 的接受集合和 unknown 结果。新增版本化的 source-only profile；不直接删除 legacy_install_code_requires_review。新合同/绑定/审核/执行模型必须显式携带 profile、审核输入摘要与策略版本；若现有 Schema 无法表达则另开版本，禁止重解释旧产物。
2. 完整有界读取 B/F/H 的 Git 树，保留整树预算、路径、链接和对象完整性检查。只把审核后的模块闭包作为 Docker 运行输入；不安装仓库，不把 setup.py、conftest、插件或外部依赖带入运行闭包。
3. 分别核对元数据中的安装依赖声明与源码 import。setup 的依赖参数只能按明确的小语法识别；星号展开、动态 install_requires/依赖声明、条件多重 setup 调用或无法确认的重绑定均拒绝。其他动态元数据不求值，逐项列为未执行的安装输入。具体可接受语法需在实现前形成规格和反例；不能先保证这份 setup.py 必定通过。
4. 保留顶层普通函数限制、整模块 AST 检查、标准库遮蔽检查和动态操作拒绝。缺少可解析依赖事实或闭包存在未解析 import 时不靠审核理由放行。明确区分“声明无依赖”和“已证明所有 Python 动态行为不存在”，后者不在静态扫描能力内。
5. 所有者必须在真实 F 的直接子提交 H 中只添加契约，仍由绑定器独立重建。没有用户授权时不创建 fork、提交或外部 PR。审核凭据继续绑定精确来源/工具实现/runner；不补签旧绑定。
6. 保持 Docker、无网络、只读输入、资源限额和精确 image ID。旧 Evidence/Guard 不变；新捕获与编译使用新 ID，来源检查不通过就不执行。

## 验收与成本

必须覆盖动态依赖/重绑定/伪造 profile/修改后复用审核/混入安装脚本/包遮蔽/闭包逃逸等拒绝测试；证明默认 profile 的旧 unknown 不变。新版本模型、绑定重建、capture/verify/compile/replay 的 profile 必须一致。真实进程测试标 slow，Docker fixture 在最终准入时专项运行。

初估设计与安全审查 0.5–1 人日，模型/实现/专项 2–4 人日；若需要新增 Guard/Evidence 版本及独立 verifier，另加 1–2 人日。**这是工程估计，不含 owner H 等待、runner 恢复、Docker 验收与更多场景采集；不保证一次即可收录 Luhn。**

即使此 profile 完成，也只消除一类工程阻塞。Luhn verify 与 luhncheck 的共同输入域、规范差异、代码谱系及后续合法反例仍须独立审核；一个修复对不能支撑 30–50 个场景或一般泛化主张。

## 当前不扩张的部分

不同时增加 callable-object、动态 getattr/setattr、regex compile 识别、unittest/Hamcrest/doctest 或任意重导出投影，不改 learner/特征词汇，不缩减数据标准。另一条可选路径仍是按现有 profile 继续有限采集；若改为同项目探索，应另有协议和明确范围确认，不能冒充原定跨项目主轨。
