# GitHub Actions 与脱敏 Summary

提供[可复制 workflow](../examples/github-actions/counterguard.yml)、
[可信 fixture 驱动](../scripts/run_ci_fixture.py)和只读 `ci-report`。
workflow 是 JSON 形式的合法 YAML，便于无额外 YAML 依赖地检查权限和上传路径。
它只支持人工 workflow_dispatch 的**工具自带受控示例**，没有在本仓库启用，也没有真实 GitHub Actions 运行记录。
本地 Git/Docker 专项验证不等于 GitHub 平台已验收。

## 从 verify JSON 生成 Summary

```powershell
counterguard ci-report --report <verify-output>/report.json --output <new-public-output>
```

生成 `summary.json` 和 `summary.md`。读取输入有 8 MiB/4096 行预算；重新核对报告 schema、
自摘要、逐行结论、decision digest、汇总计数和退出策略，再从同一 JSON 生成 Markdown。
原 report 的退出码被保留：Shadow 违规 0、Active 违规 1、执行异常 3、unknown 4、完整性失败 5。
缺失/截断/篡改报告产生明确失败 Summary，返回 5；已有输出目录不得覆盖。
`ci-report` 不重新执行或审核来源链，也不把能重签整份 JSON 的攻击者认证为可信运行者。

公开投影只保留计数、行序号、枚举状态和有限原因码、输入摘要；不含 Guard/target 名称、
源码/契约/原日志、actor、路径、argv、异常文本或环境。未在词汇内的原因显示 other_reason_redacted。
逐 Guard 的真实身份及完整原因留在私有原 report；公开 Summary 的行号用于本地对应。
这不是任意文件的通用脱敏工具；不能把 raw `report.json`、Registry 或整个输出树上传替代投影。

## 受控示例如何运行

管理员先审核并填写 workflow 的固定 CounterGuard commit，并配置公开 HTTPS runner 归档地址
`COUNTERGUARD_REVIEWED_RUNNER_URL`；归档必须与模板内的**已审核 tar SHA-256**一致。
目前没有公开 runner 归档下载服务，所以模板默认在准入步骤明确失败；不能把缺镜像转换为 skip/green。
新镜像必须经过新的构建锁、攻击验收和 catalog 发布，不能只更改模板哈希来放行。

workflow 在临时 GitHub-hosted Ubuntu runner 上运行，完整历史、contents:read、禁用 checkout 凭据持久化；
Actions 自身固定完整 commit SHA。安装的仅是指定 CounterGuard 可信提交，**不安装或执行 PR 的项目代码**。
runner tar 校验原始字节后才 docker load，随后校验安装包审核链及精确 image ID。
当前宿主工具安装仍不是完整离线/哈希锁定供应链，不能借此宣布 Beta 安装验收完成。

驱动在当前任务的新目录捕获 CounterGuard 自带可信 demo，创建本次有效的 Registry，
再把其 Git 目标交给 Docker verify；不会搬运、重签本机的旧 Registry，也不是用户项目通用 bootstrap。
只有显式 active-regression 示例提升这个全新**演示 Guard**，不自动提升用户 Guard。

| scenario | 预期结果 | job 状态 |
|---|---|---|
| fixed | 1 次执行、pass | 0 |
| shadow-regression | 1 次执行、Shadow violation | 0，Summary 告警计数 |
| active-regression | 1 次执行、Active violation | 1，刻意失败以演示阻断 |
| unknown | 不在审核快照内、0 次执行 | 4，保留 unknown |

即使验证非零，always 步骤仍写 GITHUB_STEP_SUMMARY 并只上传两个公开投影文件。
没有 continue-on-error 掩盖原退出码。若安装或准入在生成投影前失败，Summary 说明未完成，上传缺失文件仍报错。
遵守 GitHub 关于[不可信输入与权限](https://docs.github.com/en/actions/reference/security/secure-use)、
[Step Summary](https://docs.github.com/en/actions/reference/workflow-commands-for-github-actions#adding-a-job-summary)的规则。

本地复验同一驱动：

```powershell
uv run python scripts/run_ci_fixture.py --workspace artifacts/ci-demo/new-run --scenario active-regression
```

## 真实项目 PR 接入的剩余门槛

当前 Registry 的 source_workspace 是本机绝对路径，来源和授权另绑定工具实现；
Windows 上的原条目不能拷到 Linux 后改路径、重签或当成 CI 的 Active 权限。
真实项目需要可携带且可独立审核的来源交付、job 内新登记与明确状态授权；validators 的 owner head 也尚非远程可获取的完整交付。
已审核镜像的公开交付、宿主工具供应链、权限/撤销和真正远程运行仍未关闭。

因此不要把模板改为 pull_request_target/workflow_run 后执行外部 PR，不在持久自托管 runner 上执行不可信贡献，
不从 PR 下载脚本、Guard、状态事件或安装目标项目。自动 PR 工作流应另行设计和验收，
明确可信工具/规则来自哪里，目标代码仅作为静态数据进入准入并只在 Docker 运行。
GitHub 的[安全说明](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)也明确指出特权事件下执行不可信内容的风险。
