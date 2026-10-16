# 只读仓库检查

W3-A 是 MVP 冻结后的源码开发功能。v0.1.0 wheel/tag 保持原样，本轮不重新发行它们。

## 可运行示例

先在新目录准备工具自带的两提交 fixture；它不是未知项目安装程序：

```powershell
uv run python scripts/prepare_inspection_fixture.py --output artifacts/w3a-repo-v1
uv run counterguard inspect --repo artifacts/w3a-repo-v1 --base HEAD~1 --head HEAD --config examples/project-config/counterguard.yaml --format json
```

head 源码含立即抛异常的顶层代码；inspect 只读 Git 对象，不导入它。重复 inspect 应得相同摘要；重复 prepare 必须用新目录，不能覆盖历史仓库。

对自己的普通 Git 仓库，显式给出根目录、base/head 和配置：

```powershell
uv run counterguard inspect --repo D:/repo --base main~1 --head main --config D:/config/counterguard.yaml --format markdown
```

.yaml 文件内容**只能是 JSON 子集**，不接受缩进 YAML、注释或命令。见 [示例](../examples/project-config/counterguard.yaml) / [Schema](../schemas/project-config.schema.json)。运行时还检查路径规范、唯一性和配额；Schema 形状校验不能替代语义检查。

## 映射与结果

每个目标声明 target_id、guard_id、source_ref（.py）、symbol（简单标识符）、contract_ref（.json），可附 dependency_refs。`module` 对只读 W3-A 可省略；要进入 W3-B Docker 授权则必须显式填写，并与 source_ref 推导的导入路径完全一致（如 `src/pricing.py` 对应 `src.pricing`）。仅这些精确路径的变化确定候选关系；不自动推断依赖。其他改动 unknown；ignored_paths 必须逐路径声明，且运行时只接受以下窄集合：`.md/.rst` 文档、根级 LICENSE/NOTICE/CHANGELOG/CONTRIBUTING/SECURITY/AUTHORS 族、`.gitignore` 等少量根元数据、直接位于 `.github/workflows/` 的 yml/yaml、Dependabot 和 CircleCI 主配置。它不能隐藏映射输入、requirements、构建脚本、`.github/actions/` 或图片资源，也不接受 glob。

因此源码与 `.github/workflows/ci.yml` 同时变化时：配置精确声明这个 workflow 路径，结果是 source 对应目标 affected 且整体可 ready；未声明时整体 unknown。这个保守默认要求接入者审核每类辅助文件一次，避免工具自行认定任意“非 .py 文件”都与行为无关。

| 退出码 | status / 含义 |
|---|---|
| 0 | ready：声明映射覆盖改动，或确定没有相关文件改动 |
| 2 | 配置/修订语法/显式输入无效；stderr 说明 |
| 4 | unknown：缺历史、不支持布局、未映射或超限等；JSON 保留原因 |
| 5 | rejected：链接、特殊元数据或对象完整性拒绝；JSON 保留固定原因 |

target.impact 为 affected/unaffected/unknown，不是 Scope 的 applicable/inapplicable。所有结果 execution_allowed=false、execution_outcome=not_run；这两个字段在 Schema 中是常量，ready 不表示测试通过、契约有效、符号存在或允许执行。W3-B 也不修改它，而是从 ready Inspection、当前配置/源码 pin、精确 replay 请求、固定 Docker policy 和镜像摘要另行生成授权；详见 [安全模型](security-model.md)。

报告绑定请求修订、解析提交、配置原字节 SHA-256、映射文件对象/内容、Git 版本及包源码摘要。读固定提交，不读 dirty tree；不含绝对仓库路径、源码正文或原始 stderr。不为确定性虚构时间，当前只读报告没有 created_at。改变输入得到新摘要，重复读不写仓库。

三格式由同一 InspectionReport 渲染，inspect 只输出 stdout。保存文件由调用者选择新 ID/目录；来源变化后不覆盖历史报告冒充同一次检查。

当前仅支持有配额的普通 SHA-1 profile。浅克隆缺历史 unknown，不自动 fetch；gitfile/worktree/reftable、外部对象库、子模块、链接不在支持范围。重命名为 D+A，删除/缺失 head 输入不当作无影响。完整边界见 [安全模型](security-model.md)。
