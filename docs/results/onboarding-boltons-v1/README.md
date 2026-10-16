# boltons 首次接入试走

[计时与来源记录](trial.json)。操作者是项目开发代理，已有工具知识；这不是外部用户研究，也没有测量流失率。
库预选与后续工具开发时间未计入六步；六步记录的是墙钟时间，包含工具往返和排障，不能等同人工专注时间。

项目：[mahmoud/boltons](https://github.com/mahmoud/boltons)，BSD-3-Clause，选定树 111 个文件。
上游声明无需运行时依赖；该版本 pyproject 省略 dependencies 且未将它标记为 dynamic。
这与依赖元数据的静态含义一致，但当前 minimal-python.v1 要求显式 []，因此仍报告待审，不能据此声称一定要安装依赖。
规范依据见 [PEP 621](https://peps.python.org/pep-0621/#dynamic)。没有为接纳该项目修改这一冻结检查条件。

真实修复 [1e61524](https://github.com/mahmoud/boltons/commit/1e61524a798ea73632029a013a7686036d5c126f)
同时修改 `boltons/strutils.py` 和 `tests/test_strutils.py`，修复 singularize 对双 s 结尾单数的错误截断。
真实父提交为 `55dfe5077bcb5fa76611b5f2a557ea6c442ad87c`。这是静态确认的 B/F 来源，**没有运行来证明复现**。
未 checkout、未创建 fork/owner 提交，代码从未在宿主或 Docker 执行。

| 接入步骤 | 首轮耗时 | 实际完成程度与卡点 |
|---|---:|---|
| 1 选择缺陷、提交和许可 | 416.893 秒 | 来源材料已识别，未证明复现；包含安全获取脚本遗漏本机 Git 代理的失败与排障，配置路由后实际克隆 9.966 秒 |
| 2 准备契约 | 48.483 秒 | 用一次性辅助脚本准备人工审核草案，12 条直接断言；第 13 条嵌套幂等性另列；最终 owner-head 契约未提交 |
| 3 导入/依赖预检 | 2.175 秒 | 代理沙箱下返回 repository_unavailable，尚未分类项目兼容性；保留这次失败 |
| 4 Evidence 双向捕获 | 未尝试 | 缺 owner-head 最终契约、通用 Docker bootstrap，项目预检也未通过 |
| 5 初始 Scope | 未尝试 | 无已核验 Evidence/Guard，不生成空的 Scope 授权 |
| 6 Shadow 审阅登记 | 未尝试 | 无可登记来源，不伪造 Candidate/Shadow 或 actor 授权 |

首次从开始到停止是 **468.304 秒（7 分 48 秒）**，分步骤实测合计 467.550 秒，其余是步骤交接。
**完成时间为 null**，不是“7 分 48 秒接入成功”，也不能把未尝试步骤记成 0 秒通过。
获取脚本的代理缺陷不是普通 Git clone 的性能数据；没有修改 Docker/Git 全局设置。

## 正常权限复核与工具改进

随后在正常本机权限下用同一版本复核，耗时 2.745 秒，退出 4/blocked。
完整树中确有 tests/conftest.py，以及旧配置、fixture/装饰器、导入路径/动态代码等待审项；
预检并没有证明这些都是实际目标闭包的依赖。保守扫描完整项目导致的额外人工审核，是本轮暴露的接入成本。
这些判断不能通过删配置、改标签、补签契约或在宿主执行项目来绕过。

新增 `contract draft` 后，同一固定测试重复提取两次，实测 **4.205 / 3.607 秒**，产物字节一致：
13 条源断言 = 12 条已表达 + 1 条 nonliteral_expression；退出 4/partial，草案仍写出。
12 组输入/预期与先前人工草案一致；嵌套调用没有被静默移除或伪装成已支持。
操作者已经熟悉该测试，而且与测试运行有并发，不能据此计算因果加速比例或外部用户耗时。

复验提取命令（先自行获取完整仓库，不 checkout/执行；repo/output 替换为新目录）：

```powershell
counterguard contract draft --repo <boltons-clone> --revision 1e61524a798ea73632029a013a7686036d5c126f --test-ref tests/test_strutils.py --test-function test_singularize_double_s --target boltons.strutils:singularize --output <new-proposal-directory>
counterguard preflight --repo <boltons-clone> --revision 1e61524a798ea73632029a013a7686036d5c126f --profile minimal-python --import-root .
```

新预检 v2 保留 blocked 与原有原因，另输出明确用户动作、维护者职责和无 ETA 的跟踪落点。
原始源码、草案、命令输出、代理相关诊断及失败尝试只留本地；这里不公开机器路径、代理地址或个人 Git 身份。
机器记录绑定实际包源码摘要，验证时基点是 `38f9288` 且工作区有本轮修改，不冒称旧提交实现。

本轮结论是：受限机械提取值得先做，但**最先阻止完整接入的产品能力是通用 Docker bootstrap 与审核后的闭包/契约接入**。
没有获得完整 Shadow 时间；30 分钟仍是待验证目标，而非已知能完成的承诺。

交付验证：683 项快速测试通过（204 项 deselected，88.86 秒）；4 项真实 Git/Docker 专项通过
（无 skip，56.70 秒），Ruff 通过；未跑全量。新 Git 专项只读处理恶意测试文本及 conftest，
Docker 专项执行的是既有可信工具 fixture，boltons 的执行次数仍为零。
基础 wheel 在仓库外独立安装、不带 runner extra，也生成相同的 partial 草案摘要；
wheel/源码包已检查未收集本地 Git 指南。原始测试、验证与打包摘要分别保存在同目录的机器记录中。
