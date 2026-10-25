# 支持范围与已知限制

CounterGuard 目前只覆盖很窄的场景。这一页把边界写清楚，避免把工程验证当成通用能力。打包和安装以[发布说明](release.md)为准，攻击面覆盖见[排查清单](attack-surface-checklist.md)。

## 支持哪些输入

- Python 3.12 起、pytest 8.4、根目录或 `src/` 布局、零运行时依赖的项目；
- 只支持显式目标，以及当前契约类型和断言模板；
- `mvp.yaml` 只接受 JSON 子集，不支持 YAML 的缩进、注释或锚点；
- 标准 Demo 用录制候选、固定可信模板和本地 fixture，没有接实时模型，也不生成任意新 oracle；
- pytest 是可选 runner extra。基础安装缺它时，Demo、Pipeline 和执行器会提前拒绝并提示安装，退出 3，不把缺依赖当成测试违规；
- 契约和模块 context 需要人工确认。自动 AST 提取不替代语义判断。

## 执行边界

- Docker 授权只覆盖已审核的 replay、capture、compile 路径，以及新增受限字面量契约的双向捕获；
- 任意仓库还没有通用自动准入、完整依赖证明或自动学习 Scope，也不能调用 trusted-local 入口绕过限制；
- 只读仓库检查的 `ready` / `affected` 只表示声明的文件映射结果，不审核依赖完整性、符号存在或契约语义；所有结果都是 not_run，`execution_allowed` 在类型和 Schema 上恒为 false；
- 普通 SHA-1 Git profile 之外的布局或缺失历史保守返回 unknown，链接和损坏对象直接拒绝；
- 宿主 Git、Docker daemon、WSL2、TOCTOU、容器内恶意目标干扰 pytest，以及 runner 供应链的剩余风险，见[安全模型](security-model.md)。

## 证据能证明什么

Registry 的 `enabled` 只表示可以继续核验候选，不是 Active，也不是执行授权；每次使用都会重验原工作区来源，移动或损坏就拒绝。缺索引不会自动重建，禁用是终态。

Evidence 要求 buggy 实际断言失败、fixed 通过；Guard 只保留这次失败且修复后通过的 case。验证器会校验引用文件的摘要，并从原始 JUnit 重建 case 集、结果和执行分类。pytest 退出 1 只有配上完整且准确的断言失败映射才算 violation；退出 2–5、收集错误、缺失或矛盾的 JUnit、超时和启动失败，都不能冒充缺陷证据。

摘要用于一致性和来源关联，不是签名，也不是作者身份认证。能同时改写源码、原始日志、所有关联记录及其摘要的攻击者，已经超出当前信任边界。验证也无法独立证明创建时间或执行主机的身份。

单次契约通过不证明程序等价，也不证明穷尽正确；最小失败 case 的筛选不等于输入 shrinking。Scope 的不可删除条件见证，不证明规则全局最小或能泛化到样本外。当前没有自动接受变异样本、lazy/ICE learner 或自动推断反例标签。

## 实验与 unknown

scope_v1 只有公开的 15 行示例（9 训练 / 6 留出）和两族 Guard。它验证的是机制与工程一致性，不是盲测，也不足以外推到任意仓库。静态特征审计会检查全部 15 行，但训练成员和正负标签只来自冻结的 train。

标准 Demo 的六个训练目标都有完整元数据，所以没有 unknown。独立展示 unknown 时用的是缺少声明契约的真实 replay，结果是 unknown / not_run / skipped、退出 4，原因会保留，但不加入六行 Demo 或留出分母。unknown 不等于已经确认 inapplicable，也不是通过。

历史来源、日志和代码 pin 都不会自动刷新。代码或环境变化后的新运行使用新的 ID 和目录；旧评测、管线和报告只能在其原始源码下复验，不能靠重签旧 manifest 冒充当前运行。失败或部分完成的目录也不会自动恢复。

## 历史结论的边界

独立来源校验和诊断保护补齐之前的历史 verify 结果，不覆盖四类攻击面：Evidence 重签失败集或来源身份、Guard 自检与原始 JUnit 矛盾、独立 Replay 执行 / trace / 身份重签、以及诊断回显私有路径或显式凭据。

这是按入口限定的保证。旧的 Gate / Evaluation / Pipeline 有部分原始事实重建，但不代表旧的每个独立 verify 都有同样的保护；诊断泄漏属于输出边界，verify 成功本身也不证明报告可以公开。四类修复和对应测试见 [A01–A04](attack-surface-checklist.md)。

历史记录只证明「在指定的代码和输入下，当时的检查通过」。现行验证器因源码绑定拒绝旧产物，不等于发现了篡改；切回旧代码复验，也不会把它升级成当前版本的独立验证保证。需要当前保证时，在新 ID 或新版本目录里重新物化可重跑的来源链，并记录当前检查。冻结的 holdout 结论保持原版本和覆盖声明，不重跑调参，也不重签旧 manifest。

## 诊断与公开分享

CLI 自己生成的错误摘要会移除显式凭据赋值和绝对路径；启动异常的 `error_detail` 只保留异常类型。这个规则范围明确，不是通用秘密识别器，Typer 参数校验、任意应用字符串和无上下文的秘密值都不在覆盖范围内。

原始 stdout / stderr / JUnit 仍保存原字节和摘要；RunRecord 的 argv、case message、来源代码和契约里也可能带本机路径或业务数据。JSON 和 Markdown 报告是对证据的忠实展示，不是已经脱敏的公开导出包。当前把这些本地证据视为私有，公开分享前需要另行检查。

默认不会把 API key 环境变量传给子 pytest，录制 AgentContext 也不包含环境、fixed 实现或 benchmark 标签。但这个边界不阻止可信目标主动读取本机文件或自行访问网络。

## 仓库接入试点（validators / fork）

试点限定为 validators 的固定 B/F/H 和 MAC 全部 10 个回归 case。`pilot-scope.v1` 是已审核的精确快照绑定，不是学习作用域，没有验证跨提交或跨仓库的泛化。

其余 25 个新增区域标识符 case、全仓上游测试、pytest 插件、conftest、自定义安装和其他装饰器仍未覆盖。元数据 `dependencies=[]` 也不证明所有可选功能和未来执行路径都无需依赖。

统一 verify 支持固定 owner head / profile 的仓库；默认 preflight 仍是 pytest 8.4.2 的 root profile，不会自动推断其他项目的 src / pytest9 能力。`H` 是仓库所有者在 fork 中单独添加契约与配置的工具方提交，不是上游维护者提交。

首轮因为相对 cwd 解释错误，捕获记录被独立验证器拒绝，没有发布 Guard；第二轮完成了真实自检，但完整来源复核出现二十多分钟重复开销，被显式中断；最终在第三个命名空间重新验收。两轮的原始记录和失败说明都保留，没有把失败重签成功。

Git 读取优化只合并了 blob I/O：先检查大小，再批读并逐个验证 Git 对象哈希；映射路径数、单 blob 1 MiB、总 blob 8 MiB 和 5 秒 / 30 秒预算都没变。重复来源链复核仍有额外开销，不能只看 pytest 内的执行时间。

## 统一 verify 的边界

- `contract draft` 只投影受限测试语法，不运行目标，不证明原测试正确或独立，也不输出可执行契约；
- boltons 试走记录的是遇阻时间，没有产生 Evidence / Scope / Shadow；
- preflight 的 minimal-python 检查只分类免安装、免插件候选，不能穷尽动态行为，也不能替代单独的 Docker 授权；
- 新项目初次没有合法反例时，只有经审核的精确快照边界，源码更新后仍可能频繁 unknown；
- CI Summary 是有限字段的展示投影，不是通用脱敏器或执行认证，受控 workflow 没有实际 GitHub 运行记录；
- 本地 Docker 测试通过，不等于 Beta CI 或跨平台验收完成；
- 生命周期是本地追加的审阅记录，不提供身份、角色、签名或防回滚，远程 CI 授权未实现；
- runner 目录随安装包固定摘要，只读发现不会构建、拉取或运行镜像；没有 Docker 或镜像时明确 unavailable，不能用相同 tag 或任意新 ID 代替；
- 通用 Docker 捕获只支持已审核的 source-only 字面量契约和线性 B/F/H，不加载项目 pytest 配置、conftest、插件或原生测试；
- 容器内的恶意目标仍可能干扰 pytest / JUnit；宿主里的全链重写没有签名保障；
- 新增实现会改变全包源码绑定，旧的 Inspection、Docker 授权和仓库 Evidence / Guard 可能过期。保留原字节，在新命名空间重新物化，不重签历史记录。
