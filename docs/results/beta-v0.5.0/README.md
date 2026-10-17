# CounterGuard 0.5.0 Beta 验收

本轮完成受限首次接入、统一 verify、本地生命周期、可复制 CI 模板和 Beta 安装交付。
机器结果见 [acceptance.json](acceptance.json)；发布内容见 [release-notes.md](release-notes.md)。
该收据不是原 Evidence、授权或签名，也不能代替当前来源链独立核验。

## 实际检查

- 最终全量 **998 passed，0 失败、0 错误、0 skip，JUnit 记录 1684.71 秒**，包含快慢测试、真实 Docker、根/src 首次接入以及显式启用的 validators Registry/两次重放来源审计；计数与耗时由实际 JUnit 提取（控制台总计 1684.72 秒）。
- 首轮全量发现旧 holdout CLI 文案断言未同步；拒绝行为和退出码 2 已正确。
  更新断言并增加“读取协议即失败”的哨兵后，单项 1 passed；包源码、标签、指标和拒绝标准未改。
  首轮随后被中断，恢复时进程已不存在且没有最终 JUnit；因此不报告首轮通过总数或完整耗时。
  原始部分工作区及单项失败/修复诊断保留。经维护者明确追加授权，在新目录执行第二轮全量，未覆盖首轮为通过。
- 根镜像四项攻击包含在全量内；pytest9 镜像另跑同组四项，4 passed、无 skip，12.99 秒。
- checkout 外两个新环境安装同一 wheel，使用 Python `-I`，确认 site-packages 来源和全包源码摘要相同。
  基础环境不含 pytest，Demo 返回 3、给出 runner 安装提示，无 traceback、无执行输出目录。
- runner 环境的首次 Demo 因目录太深触发既有 240 UTF-16 路径限制，退出 2，原始失败保留。
  改用全新短目录后完整 Demo 退出 0，独立 verify-only 退出 0；没有更改门限、ID 或原失败记录。
- 同一干净 wheel 实际运行工具自有 CI 驱动：Docker capture → compile → Shadow → verify → 公开投影，1 次执行、1 pass、退出 0。
- validators 固定 MAC 试点以新 manifest/运行目录重新物化；两次源码入口计数与决策摘要一致、run ID 不同。
  干净 wheel 另做一次 Docker 重放，1 次执行、1 pass、退出 0。原 manifest/产物未覆盖。
- Ruff 通过；新增 schema 与模型一致；检查 wheel/sdist 文件清单、许可元数据、文档链接和公开变更隐私。
  固定协议、标注、上下文、原 examples/契约、既有 artifact、Docker policy/catalog 与 v0.1.0 标签未改。

根/src 集成用例覆盖 Candidate 不执行、Shadow 告警、Active 阻断、fixed 通过、unknown 零执行、退休不调度、
来源篡改即使在退休态也失败；重复运行仅要求计数/决策一致，真实时间和 run ID 保持各自独立。
测试最后故意破坏 Guard 测试文件，因此这些测试目录的当前 Guard 是拒绝样本，
不能把先前成功报告解释为测试末尾仍通过独立核验。原始运行和篡改均保留，没有恢复或补签旧记录。

## 复验

普通开发只需快速层和受影响专项；最终交付才运行一次全量：

```powershell
uv sync --frozen
uv run counterguard runner list
$env:COUNTERGUARD_RUNNER_IMAGE_DIGEST='sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16'
uv run pytest -m "not slow" -q
uv run pytest tests/integration/test_standalone_bootstrap.py tests/integration/test_docker_runner.py -q
uv run ruff check .
```

复验 pytest9 攻击时换为目录中 validators-pytest9 的精确镜像 ID，并仅运行 test_docker_runner.py。
所有真实进程测试标记 slow。未加载审核镜像、未设置真实来源 manifest 或两份报告导致的 skip **不算对应检查通过**。
本次全量提供了这些前置；原始 JUnit 留在本地，公开收据没有把它作为可搬运执行授权。

全量命令和前置在 acceptance.json 内。固定 validators 的真实来源审计还需要本机已审核 owner H、
新捕获/Guard/Registry 和两份真实报告，详见[试点设计](../../../integrations/pilot/design-fork-v1.md)。
由于原 owner Git bundle 含身份元数据，本轮没有上传它，也没有声称其他机器能仅从公开 Git 拉取完整 H。
新机器可复验通用的工具自有 Git/Docker fixture；不能用该成功替代缺失的外部仓库来源。

干净安装步骤见 [Beta 说明](../../beta-release.md)，CI 驱动及失败策略见 [CI 文档](../../github-actions.md)。
新版模板固定已实测的 wheel、哈希依赖和 runner 归档；没有在本仓库 .github 中自动启用。
GitHub API 检查时 workflow 数为 0，**未进行 GitHub 托管 job 验收**；本地驱动实测与模板结构检查分别记录。

## 范围与隐私

新 Guard v3 / Registry entry v3、快照 Scope 与执行授权 v5 使用新产物格式和命名空间；旧格式不补签。
源码实现基点及全包摘要写入收据，文档、模板和依赖清单的收尾没有更改该包源码。
没有新增运行时依赖；两份哈希清单由同一 uv.lock 导出。

工具自有根/src fixture 证明受限通用路径，真实 validators 证明固定 MAC profile；两种证据不混为同一泛化结论。
未知源码快照仍 unknown。原生 pytest 引导、目标依赖安装、远程角色/撤销、可携带 Registry、
恶意目标干扰 JUnit、内核/daemon 信任和全面攻击矩阵仍未关闭。

公开材料仅含必要计数、摘要、许可及枚举状态；不上传原始报告/日志、Registry、绝对路径、操作者文本或原始 Git bundle。
项目 Apache-2.0、validators MIT，第三方镜像/依赖许可各自保留。
公开 Release 的实际上传时间、资产摘要和标签提交由后续独立交付收据记录；不回写本验收收据。
