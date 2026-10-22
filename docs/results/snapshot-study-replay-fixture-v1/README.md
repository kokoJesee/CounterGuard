# 完整快照四方法工程验收

本批只验证工具自有 Git/Docker fixture，接口见[四方法研究重放](../../snapshot-study-evaluation.md)。
没有外部执行、真实标签、外部训练或正式协议冻结；不增加真实场景数。
这是已知人工 fixture 查询的工程矩阵，不能作为封存留出或跨项目研究收益。

## 验收范围

新增独立计划/执行审核/准入/授权/结果，以及完整 N×4 计划/标签审核/评测审核/结果/失败记录。
旧比较、外部观察和生产 parser 不接受新用途。三个审核锚与 CLI roster 字节锚独立保管，
同一 Guard 的所有查询固定同一对 fit 与 B2 来源接口。
沿用原 learner、特征语法、最小 Guard 的完整 case、Docker transport 及指标公式。

单元专项27项及另补两查询专项1项已通过：四方法决定、fit重建、三态零启动、独立锚、旧类型/外部用途拒绝、
完整矩阵/标签依据/计数重建、途中变化保留部分记录、逐行换 fit 拒绝、真实失败与执行异常区分、
CLI锚和holdout早拒绝。两查询专项检查2×4完整矩阵及第二行标签变化在首次执行前拒绝。

完整快速层1313 passed / 292 deselected，470.89秒；另补的两查询测试在快层收集后单独运行，1 passed。
Ruff通过，新增5份执行和5份评测Schema与当前模型一致，原11份训练Schema也一致。
真实Docker专项1项通过，5816.46秒。成功复跑使用10个工具自有容器：来源Evidence/Guard 4个、
首个四方法矩阵2个、重复矩阵2个、refined可适用通过场景1个、unknown矩阵1个。
两份主矩阵的逐方法预测和原始case结果一致；initial为1条、加入合法反例后的refined为2条，
refined可适用场景真实通过。单独实验的initial拟合拒绝被显示为unknown且`run=null`，没有启动额外容器。
有限机器回执见[qualification.json](qualification.json)。没有跑全量。

首轮Docker来源捕获及Guard自检4容器已完成，查询审核因新计划被旧事实loader的精确类型检查拒绝；
没有目标执行。修复为新接口的显式只读事实视图及独立 `_facts` 实现，未放宽旧parser。
该轮原始JUnit、运行目录及后续复跑记录分开保留，不退计实际容器。
本机沙箱另有临时目录/硬链接权限失败，未修改不可变写入策略来绕过。
因此本批累计14个工具自有容器（10个成功复跑、4个保留的失败轮次），外部容器为0。

这项真实专项耗时约97分钟，主要成本是报告、导出、比较和逐项重放再次从完整来源链重建事实；
目标pytest运行本身约2秒。当前回执固定了实际执行过的测试源码，未在验收后改写测试来缩短数字。
后续可在不减少“独立完整核验 + 重复矩阵 + refined通过 + unknown零启动”的前提下合并重复读取；
本批不把尚未验证的性能优化写成结果。

## 结论边界

来源Bug表单列原最小Guard的未加作用域自检，并明确角色；它不证明learned Scope仍能检出来源缺陷。
指标只来自已知fixture人工标签，不验证真实语义、谱系独立性或泛化效果。
结果固定 `research_support=fixture_engineering_only_not_scientific_evidence`。

没有重跑隔离攻击矩阵；远程身份/签名、防回滚、最新撤回、原子快照和容器内JUnit干扰保持未覆盖。
W01/W03/W04整体继续为部分。既有artifact、冻结scope_v1、原examples与发布标签未改。
新增包源码改变实现摘要；需要当前结论的链必须用新ID/目录重建，旧产物保持历史字节。

## 候选诊断更正

只读重查webcolors固定提交`6c8da6832eb4ae2591a1883a0d1371263d6cd4db`：
`src/webcolors/_normalization.py`文件摘要为
`sha256:5fecd93499670c22de2c155421395e1c82a32fa17de0019193b25e970188d987`，
选中`normalize_hex`的第47行使用NamedExpr，函数体内没有Try/TryStar。
原语法读取器返回`study_control_flow_or_binding_unsupported`，静态根导出另返回`export_evaluated_annotation`。
先前“webcolors的Try不支持”的具体描述有误，已在训练回执与数据卡写回更正；原机器回执不改字节。
本次不支持新语法、不生成外部FeatureRecord/标签，也没有外部容器。

另只读检查TTE原六个字符串向colored:cprint的候选比较；完整快照检查因根setup.cfg返回
`snapshot_legacy_install_unsupported`。该配置实际仅含pycodestyle/flake8节，但当前profile没有例外。
没有删除配置、借旧闭包准入代替完整快照，或新增legacy支持；因此新增可执行场景仍为0。
