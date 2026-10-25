# 只读仓库检查

`inspect` 是 MVP 冻结之后加入的源码开发功能。v0.1.0 的 wheel 和 tag 保持原样，这一版没有重新发行它们。

它读的是 Git 提交对象，不 checkout、不 import、不执行仓库代码。输出只描述「声明的映射是否覆盖了这次改动」，不表示测试通过，也不给执行许可。

## 可运行示例

先在新目录准备工具自带的两提交 fixture。它不是给未知项目用的安装程序：

```powershell
uv run python scripts/prepare_inspection_fixture.py --output artifacts/w3a-repo-v1
uv run counterguard inspect --repo artifacts/w3a-repo-v1 --base HEAD~1 --head HEAD --config examples/project-config/counterguard.yaml --format json
```

head 源码里有立即抛异常的顶层代码，inspect 只读 Git 对象，不会导入它。重复 inspect 应该得到相同摘要；重复 prepare 必须换新目录，不能覆盖历史仓库。

对自己的普通 Git 仓库，显式给出根目录、base/head 和配置：

```powershell
uv run counterguard inspect --repo D:/repo --base main~1 --head main --config D:/config/counterguard.yaml --format markdown
```

`.yaml` 文件内容只能是 JSON 子集，不接受缩进 YAML、注释或命令。见[示例](../examples/project-config/counterguard.yaml)和 [Schema](../schemas/project-config.schema.json)。运行时还会检查路径规范、唯一性和配额；Schema 形状校验不能替代语义检查。

## 映射与结果

每个目标声明这些字段：

- `target_id`、`guard_id`；
- `source_ref`（`.py`）、`symbol`（简单标识符）；
- `contract_ref`（`.json`），可选 `dependency_refs`。

`module` 只做只读检查时可以省略；要进入 Docker 授权就必须显式填写，并且和 `source_ref` 推导出的导入路径完全一致，例如 `src/pricing.py` 对应 `src.pricing`。

只有这些精确路径的变化才确定候选关系，不自动推断依赖。其他改动是 unknown。`ignored_paths` 必须逐路径声明，运行时也只接受一个窄集合：`.md` / `.rst` 文档，根级 LICENSE、NOTICE、CHANGELOG、CONTRIBUTING、SECURITY、AUTHORS 族，`.gitignore` 这类少量根元数据，直接位于 `.github/workflows/` 的 yml/yaml，以及 Dependabot 和 CircleCI 主配置。它不能隐藏映射输入、requirements、构建脚本、`.github/actions/` 或图片资源，也不接受 glob。

所以源码和 `.github/workflows/ci.yml` 同时变化时：配置精确声明这个 workflow 路径，结果是 source 对应目标 affected、整体可 ready；没有声明就整体 unknown。这个保守默认要求接入者把每类辅助文件审核一次，而不是让工具自行认定任意「非 .py 文件」都与行为无关。

| 退出码 | status / 含义 |
|---|---|
| 0 | ready：声明映射覆盖改动，或确定没有相关文件改动 |
| 2 | 配置、修订语法或显式输入无效；stderr 说明 |
| 4 | unknown：缺历史、布局不支持、未映射或超限等；JSON 保留原因 |
| 5 | rejected：链接、特殊元数据或对象完整性拒绝；JSON 保留固定原因 |

`target.impact` 是 affected / unaffected / unknown，不是 Scope 的 applicable / inapplicable。所有结果都是 `execution_allowed=false`、`execution_outcome=not_run`，这两个字段在 Schema 里是常量；ready 不代表测试通过、契约有效、符号存在或允许执行。

Docker 授权也不会修改这两个字段，而是从 ready 的 Inspection、当前配置和源码 pin、精确 replay 请求、固定 Docker policy 和镜像摘要另行生成。详见[安全模型](security-model.md)。

报告绑定请求修订、解析提交、配置原字节 SHA-256、映射文件对象/内容、Git 版本和包源码摘要。读固定提交，不读 dirty tree，也不含绝对仓库路径、源码正文或原始 stderr。不会为确定性虚构时间，当前只读报告没有 `created_at`。输入变化就得到新摘要，重复读不写仓库。

三种格式由同一份 InspectionReport 渲染，inspect 只输出到 stdout。保存文件由调用者选择新的 ID 和目录；来源变化后不要覆盖历史报告，冒充成同一次检查。

当前只支持有配额的普通 SHA-1 profile。浅克隆缺历史是 unknown，不自动 fetch；gitfile、worktree、reftable、外部对象库、子模块和链接都不在支持范围。重命名按 D+A 处理，删除或缺失 head 输入不会被当成无影响。完整边界见[安全模型](security-model.md)。
