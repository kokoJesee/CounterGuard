# Changelog

## 0.1.0 — 2026-10-15

首个可信本地 Python/pytest MVP：

- 双向 buggy/fixed Evidence、不可覆盖的来源和原始执行日志、显式重捕获沿革。
- 只保留实际失败 case 的最小 Guard、fixed 自检和独立来源验证。
- AST 逐样本对账、独立 context、仅训练成员的 initial/refined Scope 与 clause 见证。
- Scope-aware Replay，区分 pass、violation、unknown、inapplicable、stale 和执行异常。
- 冻结四方法评测、离线候选 Verification Gate、Pipeline 与 JSON 同源 Demo/CLI 展示。
- D13 补齐独立 Evidence/Guard/Replay 的原始事实与身份核验，以及限定范围的诊断脱敏；旧版 verify 不能继承这些新增保证。
- 快慢测试分层；安装 wheel 时可选 runner extra 声明既有 pytest 依赖。
- 攻击面清单、历史验证边界、安装说明及 D14 本地验收记录。

不含 Docker 沙箱、未知仓库接入、Registry/CI、实时模型保证、通用 YAML、新 oracle 或输入 shrinking。冻结评测保持 D9 的版本和口径；本地打包验收不代表已经公开发布。
