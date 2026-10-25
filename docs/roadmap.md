# 新项目接入路线与用户下一步

这页按产品能力记录进度，不按个人开发日程安排发布日期。

## 能力现状

| 能力 | 状态 | 用户此刻能做什么 |
|---|---|---|
| 固定已审核 profile 的 verify、runner 来源查询、Shadow/Active 策略 | 已有本地实测 | 按 [verify](verify.md)核对是否满足同一来源和 Scope，不能只对照布局 |
| 新项目的只读分类与可操作指引 | 已实现 repository-admission.v2 | 运行 preflight，读取 next_step / user_guidance，不把内部工程编号当待办 |
| 现有测试的机械草案提取 | 已实现受限语法，不可执行 | 运行 [contract draft](contract-drafts.md)，人工审核并记录不支持的断言 |
| 通用 bootstrap 的输入计划 | 已实现只读模块闭包与测试环境分层 | 运行 [bootstrap plan](bootstrap-plans.md)；它不批准契约，也不启动 Docker |
| H 内通用契约与 B/F 来源绑定 | 已实现受限 contract.v3、准备与独立重建 | 按[来源绑定](standalone-contracts.md)审核，由所有者提交；来源核实不等于缺陷已复现 |
| 通用受限 Docker 双向捕获 | 已实现受限 source-only profile | 审核 H 契约和闭包后运行 [bootstrap capture](standalone-capture.md)，独立重建 Evidence；unknown 不能覆盖 |
| 受限最小 Guard、自检与精确快照 Scope/Shadow | 已实现新的 Guard/Scope/Registry 版本 | 按[独立 Guard](standalone-guards.md)编译、自检、登记，显式审核后 verify；其他源码仍 unknown |
| 0.5.0 Beta 安装与固定 runner 交付 | 受限范围，验收和发布分开记录 | 按 [Beta 说明](beta-release.md)核对下载摘要；[本版验收](results/beta-v0.5.0/README.md)列出实际检查和未覆盖范围 |
| 真实项目的可携带来源/Registry 与远程 CI 权限 | 未实现 | 不能搬运或改签本机条目；只有[受控 CI 示例](github-actions.md) |
| 上游原生测试的受控 pytest 引导 | 明确的接入前置，未实现 | 运行上游套件前必须审核配置、conftest/hooks、fixture、插件和依赖，不能因为运行时零依赖就跳过 |
| 受控依赖安装 | 未实现；目标或插件需要镜像外依赖时必需 | 需要时保留阻塞；独立契约能否避开它要重新审核，不能隐藏声明 |
| 完整快照的研究特征、拟合与四方法评测 | 工具自有 fixture 接口；外部研究尚未接入 | 按[独立研究接口](snapshot-study-evaluation.md)核对用途和[实际验收状态](results/snapshot-study-replay-fixture-v1/README.md)，不能把观察记录改名成训练数据 |

## 承诺边界

受限的 standalone 接入已经交付；任意项目兼容没有承诺日期，也没有功能专属的订阅条目。可以在 GitHub Watch 关注仓库更新。这页会记录准入和实测进展，但不把工程人日估算当成发布日期或用户等待时间。

满足受限条件的非固定项目，可以走[独立 Guard 路线](standalone-guards.md#非固定项目的支持边界)。不满足时，先按 finding 区分材料缺失和工具能力缺失：补齐真实来源或 owner H，不能覆盖动态闭包的 unknown；缺少受控依赖或原生测试引导能力时，要等相应支持。换一个项目本身不保证通过。

## 最小验收目标

目标是这样一个新的零依赖普通包：在原 Docker policy 下，从已审核的 head 契约和完整 B/F 提交捕获，编译最小 Guard，独立核验来源，再以人工审核的精确快照 Scope 进入 Shadow。

这些新契约、来源版本和反篡改验收已经在工具自有的根、src、Git 和 Docker fixture 中通过；已有 validators 和 scope_v1 的格式与结果保持原样。不能把它扩大成「任意外部项目已接入」，也不能靠删 Literal 或加宽松布尔开关来实现。

安装依赖、运行项目测试套件、自动提升 Active、学习跨提交泛化、远程发布，都不在这项最小范围里。

## 四个环节

通用 bootstrap 按四个可核验环节推进：

1. 输入计划：已实现，只读；
2. 所有者 H 内的新通用契约与 B/F 来源绑定：受限版本已实现，只读；
3. 受限 Docker 捕获与 Evidence 独立重建：已实现；
4. 最小 Guard 编译/自检与精确 Scope/Shadow：受限 profile 已实现。

来源绑定不会替所有者制造提交，也不会在没跑 B/F 时把 reproduced 写成 true。

原生测试兼容路线的第②项不再当作笼统的可选项。5–10 人日只是单一受控 profile 的原工程估算；任意插件和 fixture 的兼容工期不确定，也不保证不需要第③项。它和独立 Guard 路线谁先做，不由猜测的覆盖比例决定。依据见[固定提交研究](research/pytest-project-bootstrap.md)和[计时/阻塞复核](results/onboarding-audit-v1/README.md)。

## 已经串起来的部分

契约草案、输入计划、来源绑定、首次 Docker Evidence 和受限 Guard/Scope/Shadow 已经串联。更广泛的接入仍取决于实际材料、目标闭包与 oracle 兼容、人工审核，不能只看布局通过就宣称任意项目可用。

当前 [boltons 复跑](results/boltons-standalone-retrial-v1/README.md)已经生成新的契约准备，但保守调用分类和 owner H 还没闭环，Evidence/Shadow 仍未发生。后续应该先设计可审计的调用识别，不能拿这个案例当理由直接豁免。

优先级依据是[首次实际试走](results/onboarding-boltons-v1/README.md)，不是项目覆盖比例，也不是用户流失率的猜测。
