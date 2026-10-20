# Changelog

## Unreleased

- 新增工具自有 fixture 的四方法纯指标汇总与算术重算 CLI：复用冻结公式，按项目、Guard 和总体报告，保留 unknown、零分母和配对变化；不执行目标、审核标签或代替正式 evaluate。详见[接口与边界](docs/study-metrics.md)。
- colored 的受限真实观察后补查独立固定文档与历史；错误长度的异常/消息规范仍未确定，该 pair 保留探索用途，不进入正式 refinement。详见[一手依据](docs/research/colored-arity-policy.md)。

- 新增显式 static-reexport-v2：contract.v6 / binding.v4、多个静态根导出、带源码 pin 的有限 raise 类钩子观察；旧 profile 保留原 grammar。比较目标可用 `bootstrap inspect-target` 生成不可执行的完整提交回执，无需虚构 B/F/H；跨项目执行仍需独立研究映射与授权桥接。详见[版本与边界](docs/static-reexports-v2.md)。

- 新增受限根包具名重导出声明核验：独立 contract.v5 / binding.v3，B/F/H 分别核对公开入口到普通函数定义的路径与摘要，生成测试保留原根包调用。动态绑定/一般导出链保持待审，旧契约及产物不改写；详见[范围与重算规则](docs/static-reexports.md)。
- 契约提取与 Docker 生成测试支持受限的 `pytest.raises(..., match=...)` 字面量消息断言；复杂正则和动态表达式明确 unsupported。新增 proposal v2、contract v4、capture v2、Guard v4 与 Registry entry v4，旧格式不接受新字段，既有产物不改写。范围与重算规则见[消息 oracle](docs/literal-message-oracles.md)。

## 0.5.0 Beta — 2026-10-17

- 完成交付全量验收：998 passed、无失败或跳过，JUnit 记录 1684.71 秒，包含真实 Docker 和固定 validators 试点的来源审计。干净 wheel 完成 Demo、独立复验、真实仓库重放和 CI 驱动验收；首次失败和重试分开保留，详见[验收记录](docs/results/beta-v0.5.0/README.md)。
- 提供 wheel/sdist、哈希锁定的工具依赖清单、已审核 runner 归档及人工触发 CI 模板；模板尚未在 GitHub 托管 runner 实测，远程 Registry 权限和通用原生 pytest 引导不在本版范围。
- 新增 `bootstrap compile/verify-guard`、最小 B/F Docker 自检、完整闭包快照 Scope、Registry entry v3 和 verify-report.v3；Candidate/Shadow/Active/Retired 仍走明确的追加式审核策略。
- 新 Guard 只保留真实失败 case，不混合 B/F 依赖快照；运行前后重验来源/状态，unknown 不启动 Docker。单次核验复用刚重建的上游事实，不跨调用缓存有效性。
- 新增 source-only Docker CI fixture 驱动；项目许可元数据明确为 Apache-2.0。版本更新不增加运行时依赖，不移动既有标签或改写历史产物。

- 新增 `bootstrap capture/verify-evidence`：从当前 H 契约与 B/F 绑定生成受限测试，在已审核 Docker 中双向运行；独立重建授权、原始 JUnit、失败集和复现结论，新增 evidence.v4/授权 v4，不改旧格式。发布 Evidence 前核对两次记录，保留真实失败证据。
- 新增 contract.v3 / standalone-literals.v1、`contract prepare`、`bootstrap bind/verify-binding`：从 H 内 Git blob 重建线性 B/F/H、完整来源 pins 与测试投影，保留 unsupported，拒绝篡改与重签结论。当前绑定 v2 指向另行审核的捕获入口，自身始终 not_run；旧 v1 不补签。

- 新增只读 `bootstrap plan`：模块级候选导入闭包与上游测试环境分层，完整提交 pins、草案未支持项和人工审核要求均保留；不改变旧 strict 预检或授予执行能力。
- 复核 boltons 收集 hook、配置节与文件级 fixture 待审的真实含义；将受控 pytest 引导明确列为原生测试路线前置，记录旧计时无法完整归因的限制。

- 新增 `contract draft`：从提交内的受限字面量断言/参数化生成未审核、不可执行的 contract-proposal.v1；逐项报告 unsupported，不执行或导入仓库代码，不扩展已有可执行契约。
- repository-admission.v2 为内部工程前置补充用户下一步、维护者责任与无承诺日期的跟踪落点；读取失败不冒充兼容性判断。
- 记录真实 boltons 首次接入试走及后续草案复验。首次遇阻时间与完整接入时间分开；没有完成 Evidence/Scope/Shadow，也没有绕过现有准入。

- 新增 `preflight --profile minimal-python --import-root .|src`：静态检查免安装/免插件候选条件，逐项说明缺失前置；新增用户接入责任清单，不把候选分类当作通用 verify 支持。
- runner 发现与解析逐项核对随包交付的构建/攻击收据，缺失、篡改或重签时在 Docker 探测前拒绝；catalog/review 的既有 pin 保留。
- 新增 `ci-report`，由 verify JSON 生成受限公开 Summary 并保留退出码；提供人工触发的受控 GitHub Actions 示例。真实项目的可携带来源/权限、镜像公开交付和远程平台验收仍未关闭。

- 新增 `runner list/show`：展示精确 image ID、构建/攻击复验来源与本机可用性；`verify --runner-id` 只使用安装包目录中已审核的镜像，未知原始 ID 不再被接受。
- `verify-report.v2` 绑定 runner review；固定 validators 的仓库 Guard、src/pytest9 和精确快照 Scope 接入统一入口，采用新运行目录与授权 v3，不修改历史 owner 提交或产物。

- 新增统一 `verify`：提交差异、Registry、审阅状态、已审核快照 Scope、Docker 重放与 JSON/Markdown 报告；unknown、跳过、执行异常和违规分开汇总。
- 新增追加式 Guard 生命周期及 `guard transition/history`；Candidate 不默认升级，Shadow 违规不阻断，Active 的确认违规返回 1，Retired/disabled 不复活。
- 当前入口限于根布局快照和固定 validators profile，不扩展冻结 scope_v1 的学习结论；通用依赖、插件与远程 CI 权限尚未实现。

## 更名说明 — 2026-10-16

本项目原名 **EvidenceGuard**。开源前做同名冲突检查时发现：

更名范围：

- 包名与 CLI 命令：`evidenceguard` → `counterguard`
- 环境变量前缀：`EVIDENCEGUARD_` → `COUNTERGUARD_`
- 已冻结的 `guard-test.v1/v2` 将旧变量名写入 Guard 的测试内容摘要；执行器只根据核验后的目标元数据生成内部兼容别名，不读取或透传宿主上的旧前缀变量
- `benchmarks/context/scope_v1.json` 的内容随之变化，其 `artifact_digest` 已按新内容重算；`SCOPE_V1_CONTEXT_DIGEST` 常量同步更新
- 身份和路径隐私清理只改写 Git 历史及公开文档；冻结协议与摘要绑定记录保持原样

## 0.1.0 — 2026-10-15

首个可信本地 Python/pytest MVP：

- 双向 buggy/fixed Evidence、不可覆盖的来源和原始执行日志、显式重捕获沿革。
- 只保留实际失败 case 的最小 Guard、fixed 自检和独立来源验证。
- AST 逐样本对账、独立 context、仅训练成员的 initial/refined Scope 与 clause 见证。
- Scope-aware Replay，区分 pass、violation、unknown、inapplicable、stale 和执行异常。
- 冻结四方法评测、离线候选 Verification Gate、Pipeline 与 JSON 同源 Demo/CLI 展示。
- 补齐独立 Evidence/Guard/Replay 的原始事实与身份核验，以及限定范围的诊断脱敏；旧版 verify 不能继承这些新增保证。
- 快慢测试分层；安装 wheel 时可选 runner extra 声明既有 pytest 依赖。
- 缺 pytest 元数据或模块时提前退出 3，提示安装 counterguard[runner]，不创建运行目录或启动 pytest。
- 本地 v0.1.0 annotated tag 作为通过验收后的 MVP 冻结锚点；原始验收记录保留在语义命名的版本目录中。
- 攻击面清单、历史验证边界、安装说明及本地验收记录。

不含 Docker 沙箱、未知仓库接入、Registry/CI、实时模型保证、通用 YAML、新 oracle 或输入 shrinking。冻结评测保持原有版本和口径；本地打包验收不代表已经公开发布。
