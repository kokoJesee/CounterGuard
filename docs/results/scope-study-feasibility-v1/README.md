# 首批候选的只读探测

机器回执见 [probes.json](probes.json)，来源与下一步见[数据卡](../../experiments/scope-v2/data-card.md)，有限候选登记见 [candidates.jsonl](../../../benchmarks/v2/candidates.jsonl)。实现版本为 `f07ac5f620ff049e08d9a2dd38aaff1ef37d2d53`；运行包源码与上一份盘点一致。

本批接触五个仓库的开发期来源。四份 strict preflight 均退出 4；base58 的 bootstrap plan 退出 4，base58check 的类方法选择不受支持而退出 2。另对两份 Luhn 来源调用既有只读 Git/AST 闭包 API；luhn 无闭包 finding，stdnum 在完整对象读取时被单 blob 大小限额拒绝。baluhn 只读了固定树中的来源文件，未运行 CLI 准入。

Luhn 的真实 B/F 修复已生成一份 contract.v3，1/1 条已有字面量断言被投影。prepare 退出 4，并明确报告 B/F 两侧元数据 unknown。未创建 H，没有捕获 Evidence、编译 Guard 或启动任何目标代码；也未将准备文件注入 Git。

当前接纳场景数为 **0**。这不是“这些项目均不兼容”的普遍结论：每份实际触达层级、未测部分和下一步分别列出。共享 Base58/Luhn 描述也不是标签或可比接口的证明。

Docker 查询在本次环境中发现 Engine pipe 不存在，catalog 审核记录完整性通过但镜像可用状态为 unavailable；目标运行前须重新检查。本批均为只读，不用本地执行器替代 Docker，也没有修改机器配置。

原始 stdout/stderr、Git clone、准备文件和完整 argv 留在本地；公开回执不带本机路径、原始 Git 历史或身份凭据。读取来源的开发者已见这些材料，未声称它们是未见 holdout。

本次新增的是候选数据与说明，没有新运行代码；沿用[研究工具的快层验收](../scope-study-inventory-v1/validation.json)，未重复执行全量、快层或 Docker 攻击套件。对本批只核对 JSON/JSONL、固定 Git blob 摘要、文档链接、隐私与 diff。
