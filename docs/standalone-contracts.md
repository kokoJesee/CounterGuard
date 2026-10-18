# H 内通用契约与 B/F 来源绑定

本环节提供 `contract.v3` / `standalone-literals.v1`、契约准备和独立来源重建。
它不再固定 validators 的模块和 oracle；完成审核后可接续[通用 Docker capture](standalone-capture.md)和[最小 Guard/Shadow](standalone-guards.md)。
旧 contract.v1/v2、Guard、Scope、runner 和已发布产物不改写。

含[受限消息断言](literal-message-oracles.md)时，prepare 自动生成独立 contract.v4；原 contract.v3 保留原字段与字节语义。
[受限根包重导出](static-reexports.md)使用独立 contract.v5，仍按原公开入口生成测试，B/F/H 分别重建定义声明。
相同的源码闭包、人审和 Docker 要求仍适用；legacy profile 未增加。

## 准备、由所有者提交、绑定

先选择线性修复：B 是 buggy，F 是其唯一直接子提交。使用固定测试中的受支持断言准备契约：

```powershell
counterguard contract prepare --repo <repo> --buggy <B-full-sha> --fixed <F-full-sha> --contract-id regression.v1 --target package.module:function --import-root src --test-ref tests/test_regression.py --test-function test_regression --output <fresh-preparation-directory>
```

生成 `contract.json` 和 `preparation.json`，返回 **4** 表示须人工审核；它不写入目标仓库、不 commit。
用户/所有者审核所有输入、预期、调用绑定、模块初始化、资源、未表达断言与测试间独立性，
再将契约以独立提交 H 添加到自己的仓库。本版 H 必须是 F 的唯一直接子提交，**只新增这一份契约文件**，
F 中的所有文件逐字节保留。不要把工具准备文件误称为上游维护者已认可的契约。

本版映射内嵌于契约，H 无需另加 counterguard.yaml；同时添加配置/README、覆盖已有契约、合并修复或多步修复均不在此历史 profile 内。
需要这些形态时另行设计来源规则，不为迁就案例静默放宽。
**工具不会把外置文件注入提交树，也不会代替项目所有者制造 H。**

```powershell
counterguard bootstrap bind --repo <repo> --head <H-full-sha> --contract-ref contracts/regression.v1.json --output <fresh-binding-directory>
counterguard bootstrap verify-binding <fresh-binding-directory>/binding.json --repo <repo>
```

绑定只接受 H 的真实 Git blob，工作树中的同名文件不参与判断；不要求工作树 checkout 到 H。
H 中没有契约时，写出 `binding-failure.json` 并返回 5，不尝试本地执行。

## 契约字段与可表达范围

| 字段 | 内容与核对规则 |
|---|---|
| schema_version / profile / contract_id | contract.v3、standalone-literals.v1、新语义 ID |
| buggy_commit / fixed_commit | 完整 SHA；F 的唯一父提交必须是 B；运行时输入至少一项发生变化 |
| target_module / target_symbol / source_ref / import_root | 显式模块、符号、源码路径及 `.` 或 `src`，路径必须对应同一普通模块/包 |
| runtime_refs | B/F/H 模块级候选闭包的并集，唯一且排序，含父包初始化；不将 F 新增模块复制给 B |
| test_origin | F 内测试路径、函数、Git blob、原始字节摘要、提取器版本和完整投影摘要 |
| cases | 该测试所有受支持 case，按稳定 ID 排序，必须与重新提取结果一致；不能自行改期望、删 case 或替换 oracle |
| authority | 固定 repository_declaration_not_execution_authorization |

采用[已有字面量投影](contract-drafts.md)的 case 词汇：eq/ne、None/bool 的 is/is_not、truthy/falsey、
白名单 raises；保留参数、断言位置及摘要。没有任意 Python、类名查找、fixture、helper、自然语言 oracle 或 eval。
未表达断言完整保存在 preparation/binding 的 `projection_coverage`，不会变成“通过”或从分母中静默消失。
首版不提供从单个投影中任意挑选子集的功能；需要另选明确的独立测试函数。

契约最多 128 KiB、256 case；每 case 至多 32 个参数，字面量深度至多 8、总节点至多 10,000，
沿用字符串、整数与容器上限。拒绝重复 JSON key、非有限数字、无效 oracle、不安全路径和非规范排序。
契约准备与绑定发布前分别执行 128 KiB / 4 MiB 字节预算，不产生超过读取器上限的“成功”文件。
契约不含自己的 H SHA，避免 Git 内容自引用；H 与契约原始字节摘要只写入绑定记录。
[JSON Schema](../schemas/standalone-contract.schema.json)由模型导出，语义约束仍由验证器重建。

## 绑定证明了什么

当前 `bootstrap-binding.v2` 固定三棵完整提交树、契约原始字节、父子关系、H 新增文件的来源、
重新提取的 case/unsupported，以及逐角色闭包和配置/hook 的静态观察。每次独立验证都重读 Git 对象，
不只核对自摘要，也不信任之前的 plan/preparation。所有报告排序、无随机 ID/时间/宿主路径；
相同提交、实现、参数的重复结果逐字节一致，乱序 20 次稳定。输出使用新目录，不覆盖历史。

本版 source-only profile 在静态 PEP 621 project 元数据中接受 dependencies 省略且未标为 dynamic，
也接受显式空数组；旧 minimal-python.v1 的显式空数组政策不变。
非空运行时依赖保持 blocked；动态/legacy 安装代码、未知导入、资源/反射、目标装饰器等保留 unknown/待审。
conftest/配置存在与目标是否依赖它分开记录，不因忽略上游测试环境而自动批准执行。

| 绑定/输入结果 | 退出码 | 含义 |
|---|---:|---|
| sources_verified + review_required | 0 | 可重建来源事实；仍须语义审核，不能执行 |
| sources_verified + unknown/blocked | 4 | 来源可重建，但运行输入有未闭环事项 |
| binding-failure / rejected | 5 | H 契约、父子关系、case、闭包或 Git 安全边界不满足 |
| 仓库读取条件不足 | 4 | 保留 unknown 失败记录；不能判断来源已核实 |
| 参数非法 | 2 | 尚未建立有效请求 |

`verify-binding` 对被篡改、重签、源码版本过期的记录返回 5；不替历史记录补签。
绑定仍为 `execution_allowed=false`、`execution_outcome=not_run`、`reproduced=null`。
v2 以 `capture_entry_point` 和 `capture_authority` 指向另行审核/重建的捕获授权，不翻转绑定本身。
历史 v1 的 `capture_available=false` 保留原样；当前源码绑定已变化，旧记录不补签，须新目录重新 bind。
Git 对象完整性不能认证提交者就是仓库所有者；记录不会宣称已提供身份认证。
即使一个模块实际 import 会抛异常，只读来源核验仍可能成立；这不是可复现缺陷的 Evidence。
本轮实现只证明来源与受限投影一致，不证明 oracle 语义正确、buggy 真失败或 fixed 真通过。

## 进入 Docker 捕获

专用授权器、可信测试生成器、B/F 双向 RunRecord、原始 JUnit/日志与独立 Evidence 重建已由
[`bootstrap capture` / `verify-evidence`](standalone-capture.md)实现，沿用已审核 runner 与封闭 Docker policy。
只有实际证明 buggy 的断言失败、fixed 全通过才可声明 reproduced。之后通过独立编译入口生成最小 Guard、自检和精确快照 Scope，显式审核后进入 Shadow。
旧执行器/Registry 不消费 contract.v3 或 binding.json；不能用旧本地 capture、手工重签或配置开关绕过。
