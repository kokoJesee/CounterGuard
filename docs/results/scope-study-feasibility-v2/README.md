# 第二批候选的只读探测

本批新增 5 个仓库，累计登记 **10 个候选、接纳场景 0、目标执行 0**。机器回执见 [probes.json](probes.json)，候选与固定来源摘要见 [candidates.jsonl](../../../benchmarks/v2/candidates.jsonl)。实现版本为 `197f1944f586d404f249823ad3dfab3352de3cd2`，运行包源码没有改变。首批回执保持原样。

检索顺序沿用静态项目声明、现成断言和真实修复的条件：先看四个大小写转换库，再沿既有 Luhn 方向加入 `luhncheck`。没有运行 learner，也没有按学习效果取舍。该有限便利样本不能估算整个 Python 生态的兼容率；完整检索、下载和人工时间未独立计时，总接入耗时为 null。

| 候选 | 实际触达层级 | 结果与尚缺材料 |
|---|---|---|
| [textcase](https://github.com/zobweyt/textcase/tree/e2090f2de3fe509facd1af41675a74b77d375b63) | preflight 0；plan 4；固定 B/F prepare 4 | HEAD 的 6 条 snake 断言可投影。真实标点修复 F=`1db6a938a03783f368a85c0085ffccb41545ec36`、B=`2da8667a79eae897190f2cf276ea2a182c340f59`；F 的 `test_strip_punctuation` 有 5 条断言，仅 2 条 upper 调用被投影，其余 3 条属于其他目标。B/F 的 upper 都是可调用对象，实际 runtime assessment 为 unknown / target_binding_requires_review，不能执行。F 没有同提交新增测试；尚未证明现有两条 case 能区分 B/F |
| [caseutil](https://github.com/makukha/caseutil/tree/79b91361862dc1af6a9bb6643dcb4b07fce9684f) | preflight 4；HEAD 静态角色评估 | tox 配置使严格预检 unknown；source-only 角色评估另因 re.compile / getattr 的词法命中为 unknown。测试使用 unittest、doctestcase 等结构。找到修复 `73fd1532c3e9931f250c65fca07c28cb81296230`，但未将类测试冒充顶层函数，未 prepare；其 F 的可执行性未测 |
| [casefy](https://github.com/dmlls/python-casefy/tree/7222a2945bd42da3d053be3016df798a78cdbb8e) | preflight 4；HEAD 静态角色与测试投影 | PEP 621 省略 dependencies：严格预检为 unknown，而现有 source-only 对直接模块 `casefy.casefy:snakecase` 的评估为 review_required、无 finding。测试只有 `main()`，其中有尾部 print、混合目标和期望值在左侧的比较；整体投影为 0/153，返回 test_setup_or_control_flow_requires_review。根包重导出与直接模块身份也没有审核桥接。未把功能扩展提交冒充已确认缺陷 |
| [case-conversion](https://github.com/AlejandroFrias/case-conversion/tree/14ea3306249b54b35bd2f9cf3f952dae24947625) | preflight 4；HEAD 静态角色评估 | 严格预检因省略 dependencies 为 unknown；source-only 另因闭包 alias.py 的 setattr 为 unknown。目标转换测试使用 unittest + parameterized；未选定 B/F、未 prepare |
| [luhncheck](https://github.com/dralshehri/luhncheck/tree/26c4f875beb01d841ff5ebe072bf872ef3e1a9c2) | preflight 0；plan 4；HEAD 静态角色与投影 | `luhncheck:is_luhn` 是普通函数，角色评估 review_required、无 finding。`test_number_validation` 的 **1 条参数化断言展开为 9 个 case**，不是 9 条独立断言。保留为比较目标提案；没有确认适合作为来源缺陷的 B/F，也没有 H 或 Evidence |

preflight 0 只表示静态候选；plan 的 review_required 也不是授权。textcase 的模块闭包没有 finding，但角色评估检查目标声明时拒绝可调用对象，说明这两层不能互相替代。casefy 的语法拒绝没有证明其 153 条断言都不可表达；当前工具没有可靠地投影它们。

## 更具体的跨项目提案

为避免把“整数 checksum”与“布尔校验”混为一个接口，另从首批 Luhn 的真实 B/F 提取 `test.py::test_valid`：`luhn.verify('356938035643809')` 应为真，1/1 条断言可投影。prepare 实际退出 4，B/F 仍因 legacy_install_code_requires_review 与 project_metadata_unavailable 为 unknown。没有补造 H；也没有把同一修复的 checksum/verify 两个入口计作两个独立场景。

`luhn:verify` 与 `luhncheck:is_luhn` 可以继续审查的共同输入域是“非空 ASCII 十进制字符串，包含校验位，省略所有可选参数，返回模 10 校验布尔值”。这是固定源码与文档支持的**可比性提案**，尚未冻结 cohort、确认代码谱系独立性或执行审核。空字符串、非 ASCII 数字、空格、连字符、length/prefix 过滤与非十进制模式均不能自动纳入这个域。

例如，从固定源码静态推导，Luhn 对空串的 checksum 为 0，verify 会返回真；luhncheck 的 isdigit 检查会返回假。这是未执行的源码推导，不是实测标签。不得为扩大 cohort 删除差异、把同名函数当兼容证明，或以 bool 是 int 子类为理由复用 checksum 的整数 oracle。

casefy 的 README 明示其继承 stringcase 工作；后续不能把两者随意分到独立项目组。另三个转换库的谱系与完整边界规范仍待核实。

## 重复命令与证据边界

完整参数保存在 probes.json 的 observations[].command。先用完整 clone 核对对应提交，输出目录必须全新。例如：

```powershell
git clone --no-checkout --config core.hooksPath=/dev/null https://github.com/dralshehri/luhncheck.git <luhncheck-clone>
counterguard preflight --repo <luhncheck-clone> --revision 26c4f875beb01d841ff5ebe072bf872ef3e1a9c2
counterguard bootstrap plan --repo <luhncheck-clone> --revision 26c4f875beb01d841ff5ebe072bf872ef3e1a9c2 --target luhncheck:is_luhn --import-root src --test-ref tests/test_luhncheck.py --test-function test_number_validation --output <fresh-plan-directory>
counterguard contract prepare --repo <luhn-clone> --buggy b64d5682b2f2e0655b88543169bffddfa5bd1680 --fixed b611e357da3a5e17abf9b8dfe40b111eb1cdc50d --contract-id luhn.verify.python3.v1 --target luhn:verify --import-root . --test-ref test.py --test-function test_valid --output <fresh-preparation-directory>
```

本次分别退出 0、4、4；后两者不表示已经通过执行准入。所有命令只读目标 Git 对象，输出留在目标仓库之外。静态角色评估另外调用固定版本的 `bootstrap_binding._runtime_assessment`，用回执里的 target/source_ref/import_root 组成参数；不 import 候选模块，不代表公开稳定 API。源码、回执摘要和 CLI stdout/stderr 摘要均保留。

第一次 Luhn verify 准备的 PowerShell 重定向只保留 shell 退出 1，原始 child 退出码不确定。为消除这处歧义，用 subprocess.run 在全新目录重做，捕获 child 退出 4；前次文件没有覆盖，两次 contract 字节一致。这是只读准备重复，不是缺陷执行重试。

本批没有重新查询 Docker；上一批 unavailable 不能当作本批实时结果。没有启动目标/Docker、安装候选依赖、修改机器设置、创建所有者提交、冻结数据或执行研究适配。原始 clone、进程日志、准备文件与本机路径只留本地；公开投影的自摘要支持内容核对，不构成身份签名或执行证明。

## 准入结论

候选可行性 gate **仍未通过**。目前最具体的待推进组合是 Luhn verify 来源 + luhncheck 比较目标；缺项包括旧项目元数据的受控支持、owner H、源码谱系与可比域审核，之后才可能进行 Docker 双向捕获。完整跨项目研究仍不足数据。

不进入新评测器或数据冻结。维护者已选择继续按现有 profile 有限采集；[旧式源码支持设计](../../experiments/scope-v2/legacy-source-proposal.md)暂不实施。后者改变接受范围，不能用“人工解释一下”静默跳过现有拒绝。

本批只改候选材料与文档，校验见 [validation.json](validation.json)。未重复快层、全量或 Docker 攻击测试，不沿用旧测试结果声称新目标执行已通过。
