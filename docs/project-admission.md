# 新项目接入条件

符合已支持 profile、已有可信契约与双向 Evidence 的新项目可以接入。当前产品不承诺支持任意项目；Python 导入成功、pytest 可以启动，都不足以证明某条 Guard 适用。

这里的接入是 verify 消费已有可信来源。全新、未审计仓库的通用 Docker capture/compile 尚未实现；当前仓库捕获 profile 固定为 validators。④必须包含这一生成路径，不能改用本地 capture 绕过未审计仓库的隔离要求。缺少可复现修复、契约或 Scope 数据的项目，准备成本不确定，需要先看实际材料。

先决条件是仓库所有者提交的契约、真实 buggy/fixed 来源、可独立审核的 Guard，以及目标与 Scope 的可信绑定。新项目尚无这些材料时，verify 不通过猜测接口、运行一次测试或自动升级 Candidate 来补齐授权。具体由谁准备、六项人工决策和日常操作见[首次接入清单](onboarding.md)。

用户可以先自行运行[免安装/免插件候选检查](preflight.md#免安装免插件候选检查)，得到可检查的缺项和对应前置。这里不估算能覆盖多少项目；缺少代表性项目样本，比例既无依据，也不能决定单个项目是否可用。

预检中的 engineering_prerequisites 是工具维护者的工程工作，不是让用户写实现。用户应读取 v2 的 next_step/user_guidance；
可以通过 [contract draft](contract-drafts.md)准备未审核的测试投影，但当前仍不能自行启用通用 verify。
现可进一步用 [contract prepare / bootstrap bind](standalone-contracts.md)准备 H 内的受限通用契约并重建 B/F 来源；
这一步不产生 Evidence 或可执行 Guard，也不替代后续受控捕获与语义审核。
[路线与跟踪落点](roadmap.md)明确未承诺日期。已有一次 [boltons 试走](results/onboarding-boltons-v1/README.md)，
已记录首次遇阻时间，尚未得到完整接入耗时，不能把原工程人日表转换成用户等待时间。

## 按必要性排序

下面是单名熟悉现有实现的开发者、单一 Python/pytest profile 的工程估算，包含回归与攻击 fixture 验证。它们不是承诺工期，也不包括 native 构建、多平台、框架专用安装或独立安全审计；这些部分不确定，缺少具体项目与平台信息。

| 顺序 | 能力 | 必要性与当前状态 | 预计新增工作 |
|---|---|---|---|
| 1 | ① 显式导入布局与依赖闭包 | 通用接入的必要前置。`project-config.v2` 已支持 `src`，本次统一入口接入的是 validators 固定闭包；它尚不是任意包布局的依赖推断器 | 约 1–2 人日：声明与提交 pins、包根/相对导入检查、变更传播与 unknown 回归 |
| 2 | ④ 仓库级 Guard 通用化 | 非单文件项目的必要前置。`guard.v2` 已存在，但 `contract.v2` 的符号、oracle 和来源仍固定为 MAC 试点。不能只删除 Literal 约束就宣布通用 | 约 2–4 人日：新契约/来源/Scope 绑定版本，有限 oracle 词汇，独立验证器与反篡改测试 |
| 3 | ③ 受控依赖安装 | 仅当目标需要镜像外第三方包时必需；零依赖项目可跳过。当前执行阶段禁网、不安装 | 约 4–7 人日：完整依赖锁与 wheel 哈希、独立构建/审核、离线 wheelhouse、平台匹配和新镜像验收 |
| 4 | ② conftest / 插件受控加载 | **运行上游原生测试的兼容前置**。独立 Guard 只有经闭包与 oracle 审核确认无此需求，才保持关闭；运行时零依赖不是豁免条件 | 原估 5–10 人日仅针对一个受控 profile：配置/插件/引导文件白名单与摘要、加载清单、fixture 语义及 hook 篡改验证；通用兼容工期不确定 |

① 与④可以交错推进。②对原生测试路线是准入前置；独立 Guard 路线须逐个审核是否不需要②/③，
不应默认加载它们。boltons 的收集 hook 与选中函数无 fixture 参数并存，不能将文件级 finding 当作目标真实依赖。
[固定提交核查与便捷样本](research/pytest-project-bootstrap.md)不足以判断总体常态/少数；
没有代表性抽样，覆盖比例**不确定**。新增 [bootstrap plan](bootstrap-plans.md)把两层材料并列，旧 strict 语义保持。
当前的 validators 集成只扩展已审核 profile 的统一入口，没有把上述估算中的通用能力全部实现。

依赖安装必须位于独立构建阶段，不能在运行 Guard 的容器内临时执行 pip。首个受控方案宜只接收固定版本、完整传递依赖及哈希的 wheel，拒绝 sdist、VCS 和 editable 安装；pip 的哈希校验需要覆盖所有依赖，官方也建议用 `--only-binary :all:` 避免源码构建路径。哈希提供字节完整性，不证明包的行为安全。[pip 安装安全说明](https://pip.pypa.io/en/stable/topics/secure-installs/)

conftest/插件会执行 Python 并影响 pytest 行为。关闭第三方插件自动发现与禁止 conftest 是两个控制；不能把移除 `--noconftest` 当作无害配置调整。pytest 支持显式 `-p` 加载和 `--trace-config` 查看实际插件，但这只是机制，不能替代对 hook 和 fixture 语义的审核。[pytest 插件说明](https://docs.pytest.org/en/stable/how-to/plugins.html)

## 最小可接入范围

现有根布局 profile：独立模块、已审核源码快照、已提交的相同契约、无额外安装/插件/项目依赖映射。validators profile：固定 owner head、完整已审核包闭包、`src`、pytest 9.0.3、十个 MAC 契约 case 与两个最小失败 case。

两个 profile 均先查来源和状态，再做 Scope 与 Docker 授权；其他形态保持 unknown。需要跨新源码版本泛化时，另需经过审核的特征上下文、学习样本和 Scope 绑定，不继承 `scope_v1` 小样本实验的结论。
