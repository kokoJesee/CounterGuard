# 新项目接入条件

符合已支持 profile、已有可信契约与双向 Evidence 的新项目可以接入。当前产品不承诺支持任意项目；Python 导入成功、pytest 可以启动，都不足以证明某条 Guard 适用。

这里的接入是 verify 消费已有可信来源。全新、未审计仓库的通用 Docker capture/compile 尚未实现；当前仓库捕获 profile 固定为 validators。④必须包含这一生成路径，不能改用本地 capture 绕过未审计仓库的隔离要求。缺少可复现修复、契约或 Scope 数据的项目，准备成本不确定，需要先看实际材料。

先决条件是仓库所有者提交的契约、真实 buggy/fixed 来源、可独立审核的 Guard，以及目标与 Scope 的可信绑定。新项目尚无这些材料时，verify 不通过猜测接口、运行一次测试或自动升级 Candidate 来补齐授权。

## 按必要性排序

下面是单名熟悉现有实现的开发者、单一 Python/pytest profile 的工程估算，包含回归与攻击 fixture 验证。它们不是承诺工期，也不包括 native 构建、多平台、框架专用安装或独立安全审计；这些部分不确定，缺少具体项目与平台信息。

| 顺序 | 能力 | 必要性与当前状态 | 预计新增工作 |
|---|---|---|---|
| 1 | ① 显式导入布局与依赖闭包 | 通用接入的必要前置。`project-config.v2` 已支持 `src`，本次统一入口接入的是 validators 固定闭包；它尚不是任意包布局的依赖推断器 | 约 1–2 人日：声明与提交 pins、包根/相对导入检查、变更传播与 unknown 回归 |
| 2 | ④ 仓库级 Guard 通用化 | 非单文件项目的必要前置。`guard.v2` 已存在，但 `contract.v2` 的符号、oracle 和来源仍固定为 MAC 试点。不能只删除 Literal 约束就宣布通用 | 约 2–4 人日：新契约/来源/Scope 绑定版本，有限 oracle 词汇，独立验证器与反篡改测试 |
| 3 | ③ 受控依赖安装 | 仅当目标需要镜像外第三方包时必需；零依赖项目可跳过。当前执行阶段禁网、不安装 | 约 4–7 人日：完整依赖锁与 wheel 哈希、独立构建/审核、离线 wheelhouse、平台匹配和新镜像验收 |
| 4 | ② conftest / 插件受控加载 | 仅当契约确实依赖 fixture/hook 时必需。独立生成的 Guard 不需要项目测试环境时，应继续关闭它们 | 约 5–10 人日：配置/插件/引导文件白名单与摘要，实际加载清单、fixture 语义审核及防止 hook 改写断言/结果的专门验证 |

① 与④可以交错推进。③与②是有条件的兼容需求，不应成为所有项目的默认执行能力。当前的 validators 集成只扩展已审核 profile 的统一入口，没有把上述估算中的通用能力全部实现。

依赖安装必须位于独立构建阶段，不能在运行 Guard 的容器内临时执行 pip。首个受控方案宜只接收固定版本、完整传递依赖及哈希的 wheel，拒绝 sdist、VCS 和 editable 安装；pip 的哈希校验需要覆盖所有依赖，官方也建议用 `--only-binary :all:` 避免源码构建路径。哈希提供字节完整性，不证明包的行为安全。[pip 安装安全说明](https://pip.pypa.io/en/stable/topics/secure-installs/)

conftest/插件会执行 Python 并影响 pytest 行为。关闭第三方插件自动发现与禁止 conftest 是两个控制；不能把移除 `--noconftest` 当作无害配置调整。pytest 支持显式 `-p` 加载和 `--trace-config` 查看实际插件，但这只是机制，不能替代对 hook 和 fixture 语义的审核。[pytest 插件说明](https://docs.pytest.org/en/stable/how-to/plugins.html)

## 最小可接入范围

现有根布局 profile：独立模块、已审核源码快照、已提交的相同契约、无额外安装/插件/项目依赖映射。validators profile：固定 owner head、完整已审核包闭包、`src`、pytest 9.0.3、十个 MAC 契约 case 与两个最小失败 case。

两个 profile 均先查来源和状态，再做 Scope 与 Docker 授权；其他形态保持 unknown。需要跨新源码版本泛化时，另需经过审核的特征上下文、学习样本和 Scope 绑定，不继承 `scope_v1` 小样本实验的结论。
