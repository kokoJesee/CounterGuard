# 只读仓库检查

W3-A 是 MVP 冻结后的源码开发功能。v0.1.0 wheel/tag 保持原样，本轮不重新发行它们。

## 可运行示例

先在新目录准备工具自带的两提交 fixture；它不是未知项目安装程序：

```powershell
uv run python scripts/prepare_inspection_fixture.py --output artifacts/w3a-repo-v1
uv run evidenceguard inspect --repo artifacts/w3a-repo-v1 --base HEAD~1 --head HEAD --config examples/project-config/evidenceguard.yaml --format json
```

head 源码含立即抛异常的顶层代码；inspect 只读 Git 对象，不导入它。重复 inspect 应得相同摘要；重复 prepare 必须用新目录，不能覆盖历史仓库。

对自己的普通 Git 仓库，显式给出根目录、base/head 和配置：

```powershell
uv run evidenceguard inspect --repo D:/repo --base main~1 --head main --config D:/config/evidenceguard.yaml --format markdown
```

.yaml 文件内容**只能是 JSON 子集**，不接受缩进 YAML、注释或命令。见 [示例](../examples/project-config/evidenceguard.yaml) / [Schema](../schemas/project-config.schema.json)。运行时还检查路径规范、唯一性和配额；Schema 形状校验不能替代语义检查。

## 映射与结果

每个目标声明 target_id、guard_id、source_ref（.py）、symbol（简单标识符）、contract_ref（.json），可附 dependency_refs。仅这些精确路径的变化确定候选关系；不自动推断依赖。其他改动 unknown；ignored_paths 仅可显式列出 .md/.rst，不能隐藏代码/依赖或已映射输入。

| 退出码 | status / 含义 |
|---|---|
| 0 | ready：声明映射覆盖改动，或确定没有相关文件改动 |
| 2 | 配置/修订语法/显式输入无效；stderr 说明 |
| 4 | unknown：缺历史、不支持布局、未映射或超限等；JSON 保留原因 |
| 5 | rejected：链接、特殊元数据或对象完整性拒绝；JSON 保留固定原因 |

target.impact 为 affected/unaffected/unknown，不是 Scope 的 applicable/inapplicable。所有结果 execution_allowed=false、execution_outcome=not_run；ready 不表示测试通过、契约有效、符号存在或允许执行。没有 Registry Guard 加载或 pytest 启动。

报告绑定请求修订、解析提交、配置原字节 SHA-256、映射文件对象/内容、Git 版本及包源码摘要。读固定提交，不读 dirty tree；不含绝对仓库路径、源码正文或原始 stderr。不为确定性虚构时间，当前只读报告没有 created_at。改变输入得到新摘要，重复读不写仓库。

三格式由同一 InspectionReport 渲染，inspect 只输出 stdout。保存文件由调用者选择新 ID/目录；来源变化后不覆盖历史报告冒充同一次检查。

当前仅支持有配额的普通 SHA-1 profile。浅克隆缺历史 unknown，不自动 fetch；gitfile/worktree/reftable、外部对象库、子模块、链接不在支持范围。重命名为 D+A，删除/缺失 head 输入不当作无影响。完整边界见 [安全模型](security-model.md)。
