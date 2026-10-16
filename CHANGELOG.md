# Changelog

## 更名说明 — 2026-10-16

本项目原名 **EvidenceGuard**。开源前做同名冲突检查时发现：

- PyPI 上存在 `Tool Evidence Guard`（定位接近：验证工具输出与结构化断言后再交给 agent 使用）
- GitHub 上存在 `EvidenceGuard`（LangGraph 的 AI 安全问卷 Copilot，口号 "No Evidence → No Claim"）
- 另有 `Product Evidence Guard`（商品事实核验）

为避免与上述项目混淆并保持名称唯一，更名为 **CounterGuard** —— 面向 AI 生成代码的缺陷回归防线。

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
