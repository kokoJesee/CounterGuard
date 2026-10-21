# 独立研究快照的自有 fixture 验收

2026-10-21 完成 `source-only-python-snapshot.v1` 的工具自有 fixture 验收。接口与边界见[研究快照](../../research-snapshots.md)，严格模型见 `schemas/research-snapshot-v1/`。本次不执行外部项目，不创建 fork/H，不分配研究标签；正式跨项目场景数仍为 0。

## 执行和结果

| 命令 | 实测结果 |
|---|---|
| `uv run pytest -m "not slow" -q` | 1216 passed / 280 deselected；323.17 秒 |
| `uv run pytest tests/unit/test_snapshot_projection.py tests/unit/test_snapshot_repository.py tests/unit/test_snapshot_admission.py -q` | 45 passed；包含在快速层内，不相加 |
| `uv run pytest tests/integration/test_snapshot_admission.py -q` | 5 passed；61.33 秒 |
| `uv run pytest tests/integration/test_snapshot_docker.py -q` | 7 passed / 无 skip；733.30 秒 |
| 六项攻击原始记录补充检查 | 6/6 通过，调用下文同一断言 helper，不启动新容器 |
| `uv run ruff check .` | 通过 |
| 本轮 17 个源码/测试/脚本及新增接口文档的 format check | 通过 |
| `uv run python scripts/export_snapshot_schemas.py --check` | 8 份新 Schema 一致 |

没有运行交付全量。真实进程测试标 slow，Docker 文件另标 docker。Docker 专项约 12 分钟，成本包含反复完整来源重建；不进入日常快速层，不声称秒级。

全库 `ruff format --check .` 曾发现 13 个格式差异，其中本轮新增文档已按 formatter 修正；其余 12 个属于未涉及的既有文件，包含冻结 runner 源码和历史回执，未为格式重写。Ruff lint 全库通过不等于全库 format 通过。

Docker 测试使用 catalog 已核验的 root-pytest8 镜像：
`sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16`。
重跑时必须设置 `COUNTERGUARD_RUNNER_IMAGE_DIGEST` 为这个精确 ID；否则测试 skip，不能记为已测。
原始私有 JUnit 摘要、实现 pins 和计数见 [acceptance.json](acceptance.json)。不发布本机路径、操作者日志或原始 Git fixture。

## 正常链与攻击观察

自有源码包含普通动态 `re.compile`、类钩子及完整包资源。包内和包外各有一个超过旧 1 MiB 限额的媒体 blob；完整清单保留两者，只挂载完整包内资源。原测试模块、根/测试 conftest 均有拒绝执行哨兵，原 pytest 配置要求不存在的插件及不兼容版本；它们均不加载。

| 阶段 | B | F |
|---|---|---|
| 完整原测试投影 | 4 case：2 pass / 2 fail | 4 pass |
| 最小 Guard 双向自检 | 2 fail | 2 pass |
| 精确 F 重放，重复两次 | 不运行 B | 各 2 pass，case/计数一致 |

最小 Guard 恰好保留实际失败 case，不修改原值或消息。宿主 import 和 local executor 有禁止哨兵。独立 verify 重建来源/审核/规范测试/授权及原始 JUnit；测试最后还保留重签失败 case 声明的拒绝。

| 攻击 fixture | F 的实际观察 | 结论范围 |
|---|---|---|
| 连接外网 | `test_failed`，Errno 101 / Network is unreachable，4 case | 列明目的地址无法连接 |
| 改写挂载源码 | `test_failed`，Errno 30 / Read-only file system，4 case | 列明源码路径只读 |
| 读取宿主哨兵环境变量 | `test_failed`，AssertionError，4 case | 哨兵未进入容器 |
| 无限循环 | `timeout`，exit=null | 原 runner 超时路径实际触发 |
| 分配 512 MiB | `process_error`，pytest exit=-9，runner 仍报告 3.13.16/8.4.2 | 自有分配进程被杀；不伪装成普通缺陷 |
| 启动 128 个子进程 | `test_failed`，Resource temporarily unavailable，4 case | 原 pids=64 限制下无法完成创建 |

所有攻击的 reproduced=false，后续 compile 拒绝且不创建 Guard 目录。不能只用 reproduced=false 当作攻击成功：另核对实际 runner 版本、真实退出/完整 case 与上表具体观察，排除未启动容器的假阳性。当前 Docker 测试使用 `tests.snapshot_support.assert_snapshot_attack_observed`；该加强断言也单独调用于本轮保留的六份原始 Run，并全部通过。

合格 Docker 轮实际 18 个容器：正常链 6 个，六项攻击双向捕获 12 个。此前两轮失败各执行 2 个容器，本任务累计 22 个；没有把它们删去或算成成功。

## 保留的失败与更正

- 初次本地 unit 调用遇到 pytest 临时目录权限错误；切换到明确的任务临时目录后 45 项通过，不把环境错误记为产品行为。
- Git 专项首轮发现 runner catalog 调用同时传 ID 和 image，违反其互斥参数接口；修正后 5 项通过。
- Docker 首轮实际 B=2 fail/2 pass、F=4 pass，但契约原顺序与 RunRecord 的 ID 排序不同，汇总误判 case 集不匹配。新 profile 单独核对规范运行集合，并按原测试顺序保留失败子集；不修改旧记录排序或原 case。
- 第二轮在补充源码校验期间得到 `snapshot_run_authorization_mismatch`。该拒绝及实际双向 Run 保留，不归类成 Docker 不可用，也不补签。随后固定源码，使用全新目录完成上述合格轮。

来源摘要更新意味着历史链仍可能 stale；它表示来源绑定拒绝，不代表历史执行未发生。新实现必须使用新 ID/目录，不能重签旧产物。

## 仍未完成

当前只支持已审核 B/F 自有快照的来源捕获和精确重放，尚未把这个 profile 接入独立外部比较目标、映射/特征/训练或四方法正式实验。TTE/webcolors 的完整 Git 容量、依赖、owner H、独立语义和外部用途仍需分别通过前置；本轮没有证明它们已准入。

fixture 标记和本机审核不提供身份签名、远程撤销、防回滚或恶意候选无法干扰 JUnit 的证明；任意插件/conftest、依赖安装、生产 Shadow/Active 也未新增。W01/W03/W04 总体保持部分。
