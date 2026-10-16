# 静态准入、runner 收据和 CI 投影验收

[机器记录](acceptance.json)绑定实际包源码摘要，验证时基点为 `974089e` 且工作区有本轮修改；
没有把未提交实现伪称为旧提交的代码。原始日志、临时仓库和运行期产物只留本地。

| 检查 | 实际结果 |
|---|---|
| 快速层 `uv run pytest -m "not slow" -q` | 655 passed，203 deselected，60.05 秒 |
| 真实 Git/Docker 专项 | 3 passed，35.20 秒，无 skip |
| Ruff / 差异空白检查 | 通过 |
| src 零依赖 fixture 的完整提交树 | eligible_candidate，execution_allowed=false |
| 添加 conftest 后再从工作树删掉 | 仍 blocked，repository_conftest；不启动目标 |
| 两个本机 runner 的只读发现 | 收据 verified，精确 image available；镜像执行次数 0 |
| 新 CI 驱动的 Active regression | Docker 执行 1，violation 1、blocking 1，退出 1，仍有两份公开投影 |
| 原有真实 verify | Shadow/Active、重复决策、unknown 不执行、无本地回退通过 |
| GitHub 平台运行 / 完整套件 | 未运行 |

专项复验命令：

```powershell
# 先用 runner list 核验本机审核链和精确镜像；该环境变量只用于显式选择运行 slow 专项。
$env:COUNTERGUARD_RUNNER_IMAGE_DIGEST = "sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16"
uv run pytest tests/integration/test_admission.py tests/integration/test_ci_fixture.py tests/e2e/test_verify.py -q
uv run ruff check .
```

单位测试还包括：20 次输入乱序；import/pytest 别名、fixture/插件/动态加载/包根缺项；
四份 runner 收据逐个缺失、篡改、自摘要重签和超预算；catalog 自重签不能批准镜像；
Summary 与 JSON 计数一致、状态/退出码不漂移、未知文本不公开、损坏输入先写失败投影、历史目录不覆盖。

此结果不等于通用项目接入已交付。准入仍只是静态候选，未知 Python 行为不能被穷尽；
CI 仍缺实际平台运行、公开镜像交付、可携带来源/Registry 和远程权限。
固定 validators 的旧产物保持原字节，没有因本次包源码变化重新物化它们。
