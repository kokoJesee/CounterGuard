# 新项目接入路线与用户下一步

这里按产品能力记录进度，不按个人开发日程安排发布日期。

| 能力 | 状态 | 用户此刻能做什么 |
|---|---|---|
| 固定已审核 profile 的 verify、runner 来源查询、Shadow/Active 策略 | 已有本地实测 | 按 [verify](verify.md)核对是否满足同一来源/Scope，不能只对照布局 |
| 新项目的只读分类与可操作指引 | 已实现 repository-admission.v2 | 运行 preflight，读取 next_step/user_guidance，不把内部工程编号当待办 |
| 现有测试的机械草案提取 | 已实现受限语法，不可执行 | 运行 [contract draft](contract-drafts.md)，人工审核及记录不支持的断言 |
| 通用 bootstrap 的输入计划 | 已实现只读模块闭包与测试环境分层 | 运行 [bootstrap plan](bootstrap-plans.md)；它不批准契约、不启动 Docker |
| 通用受限 Docker bootstrap | **下一项产品开发；未实现** | 可准备真实 B/F、草案和导入映射；当前用户不能靠配置自己打开它 |
| 真实项目的可携带来源/Registry 与远程 CI 权限 | 未实现 | 不能搬运/改签本机条目；仅有 [受控 CI 示例](github-actions.md) |
| 上游原生测试的受控 pytest 引导 | **明确的接入前置；未实现** | 运行上游套件前必须审核配置、conftest/hooks、fixture、插件及依赖；不能因运行时零依赖跳过 |
| 受控依赖安装 | 未实现，目标/插件需镜像外依赖时必需 | 需要时保留阻塞；独立契约能否避开它须重新审核，不能隐藏声明 |

**当前没有通用新项目 verify 的承诺日期，也没有功能专属的订阅条目。**
可以在 GitHub Watch 关注本仓库更新；本页会记录准入与实测进展，不把工程人日估计当发布日期或用户等待时间。
不满足现有 profile 的用户，目前正确动作是保存材料并等待工具支持；换一个项目也不能保证通过尚未实现的产品前置。

下一项的最小验收目标是：一个新的零依赖普通包，在原 Docker policy 下，从已审核 head 契约与完整 B/F 提交捕获，
编译最小 Guard，独立核验来源，并以人工审核的精确快照 Scope 进入 Shadow。
它需要新的通用契约/来源版本及反篡改验收，保留已有 validators 和 scope_v1 格式/结果；不通过删 Literal 或新增宽松布尔开关实现。
安装依赖、运行项目测试套件、自动提升 Active、学习跨提交泛化与远程发布都不属于这项最小范围。

通用 bootstrap 按三个可核验环节推进：输入计划（已实现、只读）；所有者 H 内的新通用契约与 B/F 来源绑定（下一步）；
受限 Docker 捕获、编译、独立验证与精确 Scope/Shadow（未实现）。本轮没有把后一环节标为完成。
原生测试兼容路线的②不再作为笼统的低优先级“可选项”；5–10 人日仅是单一受控 profile 的原工程估算，
任意插件/fixture 的兼容工期不确定，也不保证不需要③。它与独立 Guard 路线的优先顺序不由猜测覆盖比例决定。
依据见[固定提交研究](research/pytest-project-bootstrap.md)及[计时/阻塞复核](results/onboarding-audit-v1/README.md)。

契约草案与输入计划已补齐只读准备工具；真正决定“能否完成首次接入”的下一道硬门槛仍是通用 Docker bootstrap。
优先级依据是[首次实际试走](results/onboarding-boltons-v1/README.md)，不是项目覆盖比例或用户流失率猜测。
