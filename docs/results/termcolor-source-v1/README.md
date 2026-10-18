# termcolor 真实修复的来源闭环

在维护者明确批准[契约](../static-reexport-v1/termcolor-contract.json)，并授权 fork、H 和 Docker 捕获后，
已完成 **真实 B/F/H → 双向 Evidence → 最小 Guard 自检 → 本地 Candidate 登记**。
来源修复闭环数为 **1**；有独立自然比较目标的跨项目研究场景仍为 **0**。尚未进入 Shadow、学习或研究评测。

实现：`c1a2d24bc271e8d482644f61c1c338e4a41e9b2a`。
[manifest](manifest.json)固定来源和 runner，[acceptance](acceptance.json)保存有限字段运行事实，
[audit](audit.json)核对来源/隐私/历史保留。原始 Evidence、Guard、Registry 和日志留在本地，未公开上传。

## 真实提交与许可

| 角色 | 提交及来源 |
|---|---|
| B · buggy | `db6b299abfec18223a98827f4cd6a7e475b7dfb5` |
| F · fixed | `520facb24e5310a6f48736dddfe86164057a322c` |
| H · 契约 | [`fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5`](https://github.com/kokoJesee/termcolor/commit/fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5) |
| 所有者 fork | [counterguard-rgb-range-v2 分支](https://github.com/kokoJesee/termcolor/tree/counterguard-rgb-range-v2) |
| 上游 | [termcolor/termcolor](https://github.com/termcolor/termcolor)，MIT；[许可副本](../static-reexport-v1/COPYING.termcolor.txt) |

H 只有 F 这一个父提交，只新增 `contracts/termcolor.colored.rgb-range.v2.json`，与获批契约字节一致。
提交说明含 **NOT upstream**；其余源码、测试与 F 的 Git blob 完全一致。它是维护者授权的工具契约，
不代表上游认可。创建真实 Git 提交并推送后才读取 H，没有在执行时构造虚拟提交树。
目标工作树未 checkout；来源核验始终读取 Git 对象。Git 完整性仍不能代替远程所有者身份认证。

## 实测结果

| 环节 | 结果 |
|---|---|
| bind / verify-binding | 全部退出 0；B/F/H 均无 finding、review_required；独立重复绑定逐字节相同 |
| 首次 Docker capture | reproduced=true；B：8 failed、pytest=1；F：8 passed、pytest=0 |
| 独立 verify-evidence | 退出 0，从 Git、当前授权与原始 JUnit 重建 |
| Guard 编译与双向自检 | guard.v4；保留实际失败集的 8 个 case；B 全失败、F 全通过 |
| 独立 verify-guard | 退出 0；根包入口、完整 B/F 闭包及消息 oracle 均保留 |
| 第二次完整 capture / 独立核验 | 同样 B 8 failed、F 8 passed；失败集和逐 case 结果一致，run ID 不同；核验退出 0 |
| 本地 Registry | entry.v4，重复登记幂等；Candidate、verification_schedulable=false |

原 F 测试的 2 条 raises × 4 组 RGB 参数形成 8 case，本次全部在 B 失败，所以最小失败集恰好等于完整契约。
没有为了让 Guard 看起来更小而删除 case、简化输入或改动 ValueError/message 预期。
调用始终为 `termcolor:colored`，不是绕过根包去执行定义模块。

本次共 **6 次真实外部 Docker 目标执行**：两轮捕获各 B/F 一次，加 Guard 的 B/F 自检。
已审核镜像为 `sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16`，
runner 为 root-pytest8，实际 Python 3.13.16 / pytest 8.4.2。
授权输入只有 H 的契约、各角色根包与定义源码；测试由工具单独生成并绑定摘要。
没有执行上游测试、conftest、插件或安装脚本，目标 Python 未走宿主执行器。

执行前发现 Engine 停止，正常启动 Docker Desktop 后复核 Engine 29.4.1 和精确镜像；没有修改持久设置。
H 的 GitHub Actions 查询观察到 0 次运行；匿名查询首先受 API 限额拒绝，随后用现有授权身份只读完成检查。
没有输出/保存令牌，也未启用或修改 workflow。该观察不是对未来自动执行的保证。
登记后的验收脚本曾读错嵌套字段 `entry.guard.guard_id`；修正读取脚本后重验，不改产品代码、不重复 Docker。

## 重复命令

使用上述**实现提交的源码**；已发布的旧 Beta wheel 不自动包含 contract.v5 支持。
在 clone 之外的工作目录执行，所有输出目录须全新。

```powershell
git clone --no-checkout https://github.com/kokoJesee/termcolor.git <termcolor-clone>
counterguard bootstrap bind --repo <termcolor-clone> --head fd89a72ca8295bd454b3ab37ae1d02e9f4ee03e5 --contract-ref contracts/termcolor.colored.rgb-range.v2.json --output <fresh-binding-directory>
counterguard bootstrap verify-binding <fresh-binding-directory>/binding.json --repo <termcolor-clone>
counterguard runner list
counterguard bootstrap capture --repo <termcolor-clone> --binding <fresh-binding-directory>/binding.json --runner-id root-pytest8 --evidence-id evd_termcolor_rgb_range_reproduction_v1 --review-reason "已审核原测试的 RGB 输入、消息 oracle、根包导出和完整闭包" --output <fresh-capture-directory>
counterguard bootstrap verify-evidence <fresh-capture-directory>/evidence.json --repo <termcolor-clone>
counterguard bootstrap compile --repo <termcolor-clone> --evidence <fresh-capture-directory>/evidence.json --guard-id grd_termcolor_rgb_range_reproduction_v1 --review-reason "已复核实际失败集和完整 B/F 快照边界" --output <fresh-guard-directory>
counterguard bootstrap verify-guard <fresh-guard-directory>/guard.json --repo <termcolor-clone>
counterguard registry add <fresh-guard-directory>/guard.json --cwd . --repo <termcolor-clone> --root <fresh-registry-directory>
```

Docker、当前源码或来源前置失败时停止，不能用本地执行、换浮动镜像或补签授权代替。
本次没有运行学习或研究桥接入口，没有给 8 个 case 分配研究标签，也没有把它们算成 8 个独立修复。
Shadow/Active 仍需后续明确审核，不能把 Candidate 登记当作日常 verify 已启用。

## 计时与尚未完成的条件

计时记录见 acceptance：首次 capture 47.47 秒、Guard 编译/自检 61.58 秒、重复 capture 48.88 秒。
独立核验约 6–7 秒/次，另列 fork、Git 提交、绑定与 Registry 复验的实际耗时。
人工审阅、跨会话等待和 Engine 启动总耗时未完整计时，**总接入耗时为 null**，不据此声称满足 30 分钟门槛。

自然可比且谱系独立的目标仍未确认，因此研究可行性 gate 未全过，不进入研究桥接、采集扩张或冻结协议。
本轮取得的是一个真实来源修复及其可复核 Guard，不是跨项目适用边界收益的结论。
旧候选行/回执、冻结数据、examples 原实现/契约、既有 artifacts、运行时依赖与发布标签均未改写。
