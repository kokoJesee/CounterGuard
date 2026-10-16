# validators 试点准入设计

2026-10-16，开始 W3-D 只读冻结与预检前确定；后续实测不能修改这份通过标准来迁就仓库。

完整执行试点通过须满足：W3-B 正式镜像四项攻击复验、镜像/依赖字节锁定、W3-C Registry 专项和真实登记/禁用记录；候选普通 Git profile/规模与 fsck 余量通过；配置覆盖所有改动且 Inspection.status=ready；至少一份未禁用、来源重验通过、语义匹配且 Scope applicable 的真实 Guard 经独立 Docker 授权执行。固定提交在新输出目录重复执行，逐 Guard 决策/执行分类计数一致。未决项必须解释，不把未运行当 pass。

Q2：unknown 是**安全拒绝路径的合格表现**，但不算完整执行试点通过。若准入失败，本轮只验证固定提交的静态排查、影响不明时拒绝执行、每 Guard 的未判断原因和 0 次仓库执行；不得宣称 Guard 对 validators 的缺陷检出/泛化或真实集成成功。

具体映射必须逐项审核：source_ref、source 对应 module、symbol、contract_ref、所有必要的包 initializer/依赖/数据文件；changed test 只有确有声明依赖关系时才进入 dependency_refs。`.github/workflows/<exact>.yml`、文档、许可证等允许精确 ignored_paths；运行/构建/依赖文件及未知 `.py` 不得为了得到 ready 被忽略。配置本身、Git head 的 source/contract/dependency pins 必须与实际请求一致。

当前 W3-A/B v1 有三个接入前提，不能悄悄改义：

1. Python 导入根固定为 `/workspace`，module 从 source_ref 唯一推导。项目依赖 `pythonpath=src` 或安装布局时必须显式设计下一版 import-root 授权，不自动安装或改全局 PYTHONPATH。
2. contract_ref 也要求来自检查提交的 Git blob。`integrations/pilot/contracts/` 是工具方冻结提案，不在上游提交中；当前 profile 不能把它冒充 head 文件。若需要工具方外置契约，必须设计独立可信 provenance / 新版配置和授权后再执行。
3. 现有两份 Guard 来自 membership_discount / bounded_integer_input，不能凭“参数都是字符串”就把 validators 函数标成适用。新增 validators Guard 须有真实缺陷/修复双向 Docker 证据；不能套用 scope_v1 的业务标签、伪造 Evidence 或仅跑一般测试声称闭环。

准备脚本只 clone --no-checkout，不执行 checkout、hooks、安装或仓库 Python。预检读取完整提交树，限 2048 文件/8 MiB，并复用 W3-A 的 fsck、路径/对象/引用安全 profile；工作树里删掉 conftest 不能隐藏提交中的要求。静态结果 eligible_candidate 也不证明依赖完整或允许调度，后续仍须上述全部检查。

manifest 冻结 URL、MIT 许可证字节摘要、base/head SHA、契约提案摘要、正式 image ID 与收据、Registry 状态来源、通过标准和阻塞原因。任何修改用新 manifest/结果目录；旧报告不重签。若本轮出现 blocked/unknown，止于只读诊断，不执行 pytest 或仓库代码。
