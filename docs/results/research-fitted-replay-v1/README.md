# 学习规则研究重放验收

交付[研究重放 v2](../../research-fitted-replay.md)：两份获审训练 fit、独立拟合/执行锚、
查询实际定义与特征对账、新版准入 trace 和 v7 授权，复用原 Docker 运输及原始 JUnit 核验。
范围仅为工具自有 fixture，不是正式 scope_v2 或外部跨项目实验。

执行命令：

```powershell
uv run pytest -m "not slow" -q
uv run pytest tests/unit/test_study_fitted_models.py tests/unit/test_study_fitted.py tests/unit/test_study_replay.py tests/unit/test_study_fit_provenance.py -q
uv run pytest tests/unit/test_study_fitted.py -q -k "resigned_upstream or independent_fit_anchor"
uv run pytest tests/integration/test_study_fitted.py -q
uv run ruff check .
uv run python scripts/export_study_fitted_schemas.py --check
uv run python scripts/export_study_schemas.py --check
uv run python scripts/export_study_feature_schemas.py --check
uv run python scripts/export_study_fit_schemas.py --check
uv run python scripts/run_scope_study.py inventory
```

真实 Docker 项须先把 `COUNTERGUARD_RUNNER_IMAGE_DIGEST` 设为 catalog 中
root-pytest8 的精确已审核 ID；没有该环境变量会跳过，不能据此声称实测通过。
本批精确结果、时长、实现 pins、原始私有 JUnit 摘要和保护文件核对见 [acceptance.json](acceptance.json)。
快速层 **1129 passed / 260 deselected**；来源/旧版/模型专项 **46 passed**，
加强重签子集 **6 passed**，真实 Git/Docker 项 **1 passed、无 skip**。
Ruff、14 个文件格式、新版 5 份与既有 19 份 Schema 检查均通过。
各组有重叠并曾并发运行，不能相加成独立用例总数或用时性能比较。
首次来源专项通过后，六项攻击加强为保持合法 Schema、重算自摘要以及嵌套 admission 摘要的修改，另有专项结果。

## 验证了什么

完整来源替身专项保留原 B/F/H → Evidence → Guard 的独立核验，
包括旧 C1 v1/v6 行为回归、新 v2/v7 拒绝旧 parser、拟合阶段交换、不同可信锚、
同格式重签的 fit/context/audit/review、嵌套结果伪造和输出不能进入训练仓库。
执行后训练来源变化保留实际 Run 并 stale，不伪装成零启动。
这些 transport double 不计真实容器。

真实 Git/Docker 项现场创建工具自有 source B/F/H、四个训练历史和独立查询历史：
source 捕获与 Guard 自检使用原两条断言，最小 Guard 仅保留实际失败的一条异常消息断言。
查询的映射保留全部最小 case、原输入和 oracle；source H 契约原始字节不改写。
训练本身不执行目标，initial 学出 version，refined 学出 version AND interface。

同一 stdout 查询、同一执行审核下的检查要求为：

| 方法 | 决定 | 运行观察 |
|---|---|---|
| B1 | applicable | 原来源 oracle 的 test_failed |
| B2 | inapplicable | skipped_inapplicable，run=null |
| learned initial | applicable | test_failed；固定提交重复计数一致，真实 run ID 不同 |
| learned refined | inapplicable | skipped_inapplicable，run=null |

另有 value-return 查询检查 refined 确实执行原 oracle；初始训练只有正例、缺少合法反例时，
独立获审协议的 initial fit 保留 no_counterexample / scope=null，重放和真实 CLI audit 都保持 unknown。
所有跳过分支验证零容器启动，宿主目标 import 和本地 executor 有禁止哨兵。
每份结果均通过独立 verify，而非只相信自摘要或重放调用的返回值。
真实容器合计 8 次：来源捕获/Guard 自检 4 次，B1 一次、initial 两次、refined value-return 一次；
跳过分支为 0 次。该项耗时 850.55 秒，完整来源复验成本较高，标记 slow/docker，不进入常规快层。

## 限制

fixture 的元数据、适用性和规范来自明确的人工合成设定；这些差异不证明真实项目上的收益。
本批没有重新执行原四项 Docker 隔离攻击，没有运行全量，没有执行 colored 或重捕获 termcolor，
也没有新增真实标签、冻结外部协议、开放生产 learned Scope 调度或新增依赖。
远程身份/签名/防回滚、谱系独立性、并发原子快照、恶意目标干扰 JUnit 等仍不在增量保证内。

新增源码改变全包实现指纹。本批真实 fixture 在当前源码下使用新目录重建完整链；
旧 artifact、Schema、冻结 benchmark/examples/experiment 和发布 tag 保持原样。
真实研究来源计数与完整跨项目场景没有因这项工程验收增加；外部执行仍需原准入与批准。
实施计划、原始 Git 工作区、系统日志和 JUnit 只留本地，不作为公开发行物。
