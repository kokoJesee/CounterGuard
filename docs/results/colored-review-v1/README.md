# colored 源码与调用映射审阅

映射审计实现：[9945f11](https://github.com/kokoJesee/CounterGuard/commit/9945f1175ab2b839b81c0e021a75382e19023d61)。

这是只读材料审阅，**不是执行批准或研究标签**。固定目标为
[`colored:cprint`，f3d7998](https://gitlab.com/dslackw/colored/-/tree/f3d799873a7cde62f3c43d74ed6ffc258240d956)。
上一批[静态 profile 验收](../static-reexport-v2/README.md)已完成；本批补充完整候选闭包的源码审读、谱系观察和可重复的输入映射检查。
没有执行 colored，没有创建它的 fork/H，没有改变生产快照 Scope。

## 输入映射保留了什么

[原工作表](../bounded-rgb-targets-v1/colored-cprint-proposal.json)包含 termcolor 两条来源断言展开的全部 8 case。
新增 [只读 auditor](../../../scripts/audit_rgb_mapping.py)逐 case 核对：

- text、完整 RGB 元组及其字面量类型不变；只将 `color/on_color` 映射到 `fore_rgb/back_rgb`。
- ValueError、原消息字面量子串及 assertion digest 不变；不删 case、不解包元组、不截断/夹紧。
- 来源的 `force_color=True` 显式作为 source-only 控制，不传给目标或 print。
- 工作表和目标回执仍须是未执行、未批准、未标注状态；不能通过自签一个 approved 字段放行。

[完整映射回执](mapping-audit.json)为 8/8，重复运行的完整文件逐字节一致。
20 次工作表行乱序保持语义摘要一致；实际输入字节变化仍记入字节摘要和产物摘要，不冒充完全相同的输入。
这只证明数据一致性，既不认证目标回执，也不替代真实 Git 重建、当前 Evidence/Guard verify 或维护者语义审核。

在仓库根目录运行，输出使用尚不存在的子目录：

```powershell
uv run python scripts/audit_rgb_mapping.py --source-contract docs/results/static-reexport-v1/termcolor-contract.json --worksheet docs/results/bounded-rgb-targets-v1/colored-cprint-proposal.json --target-inspection docs/results/static-reexport-v2/colored-target.json --output <new-directory>
```

预期退出 **4**，表示一致但仍需审核；输入不一致退出 5，非法参数退出 2。
脚本没有 approve 或执行入口，重复 ID 拒绝覆盖。它放在 scripts，单独绑定脚本摘要，没有改变包源码指纹。

## 8 个 case 不等于 8 个合法反例

| 输入 | 数量 | 目前证据 | 尚缺什么 |
|---|---:|---|---|
| 三通道整数越界 | 4 | 固定上游 `test_fore_rgb_clamping` 与 `Utilities.is_percentage` 的夹紧政策 | cprint 的独立 stdout 合规见证、实际 Docker 观察和人工裁决 |
| 二/四通道整数元组 | 4 | cprint 在目标内部解包；源码预测会报错 | 未找到同等的上游规范测试来规定这些输入的异常类别/消息；保持待审 |

后四项不能删除，也不能因为 Python 解包可能抛 ValueError 就认定满足来源的消息 oracle。
前四项也不能仅凭 cprint 返回 None 认定正确夹紧；建议以独立 stdout 字面量见证检查实际输出。
见证 grammar、环境前提和外部运行尚未获批，不写成已通过。
适用性的研究单位仍是 `(Guard, target)`，8 个参数不会变成 8 个独立场景。

## 源码审读与谱系边界

[源码审读记录](source-review.json)绑定 12 个候选闭包文件、50 文件完整树回执及许可摘要。
审读包含根包初始化、三个元类钩子、类体调色板生成、局部 `vars()` 写入、环境读取、TTY 与条件 Windows/ctypes 初始化。
保留全部原始分支，未通过删文件、绕过根包或执行 setup.py 来放行。
这是执行者的静态审读，维护者尚未批准；不证明任意 Python 效果安全，也不保证目标不会干扰 pytest/JUnit。

[谱系观察](lineage-history.json)记录：colored 固定版本有 577 个可达提交，termcolor F 有 233 个，未发现共同 commit ID；
检查了根提交、当前/初始文档和相关 RGB 实现，未发现衍生声明或复制依据。
**这不证明没有代码借用**；不同根提交、作者或许可证不能代替独立性审核。分组仍待维护者裁决。

可重复的只读历史检查包括 `git -C <clone> rev-list <fixed-sha>`、
`git -C <clone> rev-list --max-parents=0 <fixed-sha>`，以及对两个输出集合求交。
源码和规范依据用 `git -C <colored-clone> show <fixed-sha>:<path>` 检查；不在宿主 import 上游。
精确仓库/提交和检查范围写在 JSON 中；本批不公开原始本机日志或整份上游源码副本。

## 验证与剩余门槛

| 命令 | 实测结果 |
|---|---|
| `uv run pytest -q tests/unit/test_rgb_mapping_audit.py` | 30 passed，JUnit 0.321 秒 |
| `uv run pytest -m "not slow" -q` | 1006 passed，215 deselected，JUnit 129.974 秒 |
| `uv run ruff check .` | exit 0 |

没有跑全量或 Docker；这批没有新增执行路径。受保护的 343 个既有文件、包源码、旧产物与发布标签保持不变，
详细摘要见 [acceptance.json](acceptance.json)。新 JSON 是只读审阅材料，不是生产 Schema。

来源/可比性材料与研究工程分开准入。接下来请求确认[研究桥接 C1 提案](../../experiments/scope-v2/research-bridge-proposal.md)：
先以工具自有 Git/Docker fixture 验收严格研究授权、原 oracle 映射及独立 stdout 见证，不直接运行 colored。
新包源码落地后，真实来源链须在代码稳定且另获执行批准时用新 ID 重建，不能重签旧产物。

仍只有 1 个已验证来源、1 个待审比较候选，完整研究场景为 0；不满足独立 initial/refinement/holdout。
现有 AST 提取器也不支持 termcolor 的 For/GeneratorExp；接口分类、特征与 context 尚未冻结。
不修改无负样本时 learner 的拒绝规则，不用假特征、自动标签或更换分母填补缺口。
