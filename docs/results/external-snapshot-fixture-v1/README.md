# 独立外部用途的自有 fixture 资格

首轮 [acceptance.json](acceptance.json) 仅覆盖 JSON/Schema 方向，不覆盖 Python 模型实例。
提交前审阅实际复现了继承导致的实例接受：`SnapshotComparisonPlan.model_validate(external_plan)`
返回外部子类本身。首轮没有外部执行，不把首轮资格用于真实准入。
修正为互不继承的模型、共享字段约束及显式见证校验后，以新目录重新资格验证；
首轮 JSON/JUnit 与原始诊断均保留，不补签为修正版的事实。
以下结果对应修正版 [acceptance-v2.json](acceptance-v2.json)。

2026-10-21 验收[外部快照观察 API](../../external-snapshot-observations.md)。本目录的仓库均为工具自有，
源与目标没有 fixture 标记。真实外部执行为 0；未分配研究标签、训练或冻结协议，不增加正式跨项目场景数。

## 实测行为

来源完整契约 4 case：B=2 fail/2 pass、F=4 pass；最小 Guard 恰好保留 2 个失败 case，
B/F 自检各为 2 fail / 2 pass。独立目标的原 Guard 两次均为 2 fail，自身 oracle 两次均为 2 pass，
逐 case 结果一致。自身通过不替换来源消息或生成标签。

| 边界 | 实际结果 |
|---|---|
| 独立用途 | 无标记源需外部审核；旧 fixture review 拒绝，12 组 JSON 与 Python 实例双向拒绝 |
| 来源与许可 | B/F/H 许可 pin、不同可信锚及重签假许可拒绝 |
| 映射/比较 | 全最小 case 原样映射、来源与比较双锚、独立自身 oracle |
| 撤回 | unknown/run=null，实际零启动；纯专项另禁止渲染与发现 Docker |
| 晚到变化 | 保留实际 Run 并 stale，独立 verify 拒绝 |
| 宿主与原 pytest | 宿主 import/local fallback 哨兵；原配置/conftest 不挂载 |
| 网络/写入/环境 | 实际网络不可达、只读文件系统、宿主秘密不可见 |
| 时间/内存/PID | 实际 TIMEOUT、进程 -9、资源耗尽；不把通用启动错误当作阻止攻击 |
| 旧 fixture 回归 | 原来源/Guard、B1/B2、learned unknown、异接口跳过与晚到变化全链通过 |

新用途正常链 9 个容器（含一次晚到变化），六项攻击各 2 个，共 21；旧 fixture 回归 9 个，
总计 **30 个自有容器**。测试用 transport spy 核对实际调用数，另有 30 份原始 record。
它们不计入后续真实观察的预算。

## 命令和结果

| 检查 | 结果 |
|---|---|
| `uv run pytest -m "not slow" -q` | **1268 passed / 290 deselected**；191.75 秒 |
| 新外部纯专项及原快照/比较纯专项 | 63 passed；1.00 秒，包含在快速层内 |
| 新外部审核 Git 专项及原比较 Git 专项 | 2 passed；16.41 秒 |
| 新外部 Docker 专项及原比较 Docker 专项 | **8 passed / 1 deselected**；1072.38 秒，无 skip |
| `uv run ruff check .` / 本轮 10 文件 format check | 通过 / 通过 |
| 新 Schema / 原两组 Schema check | 12 份一致 / 原 8+8 份字节一致 |

专项的精确命令：

```powershell
uv run pytest tests/unit/test_external_snapshot.py tests/unit/test_snapshot_admission.py tests/unit/test_snapshot_comparison.py -q
uv run pytest tests/integration/test_external_snapshot.py::test_unmarked_source_requires_separate_external_review_and_independent_anchor tests/integration/test_snapshot_comparison_data.py -q
uv run pytest tests/integration/test_external_snapshot.py tests/integration/test_snapshot_comparison_docker.py -m docker -q
```

实际命令另指定全新短路径 basetemp/JUnit。原始日志与本机路径仅本地保存，摘要见 [acceptance-v2.json](acceptance-v2.json)。
各组有重叠，不相加为独立测试总数。Docker 使用已审核 root-pytest8 精确 ID
`sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16`；
记录为 Python 3.13.16 / pytest 8.4.2。integration 全标 slow，Docker 另标 docker。没有运行交付全量。
快层和 Docker 曾并行，耗时不用于性能比较。

首次纯专项因沙箱默认临时目录无法创建而出现 53 passed / 9 setup errors，未生成 JUnit，工具日志保留。
改用正常权限与全新短路径 basetemp 后通过，未修改断言标准或目标行为。

## 限制

新类型共享字段约束而不继承旧模型，独立覆盖版本/用途；具体 Session 复用封闭执行器，不接受选择权限的输入布尔值。
包声明 profile 相同，执行权限分开。源码变化须以新 ID/目录重建，不能补签旧产物。

W01/W03/W04 整体仍为部分。远程签名身份、最新撤回、防回滚、原子快照及恶意目标干扰容器内 JUnit 未关闭。
本次资格不证明真实目标语义、四方法研究或生产调度。冻结数据、既有 artifact 和发布标签不改。
