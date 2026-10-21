# TTE / webcolors 的完整快照只读准备

这轮将此前的 API/局部文件诊断推进到完整 B/F 文件实检，**没有外部 Python/Docker 执行、fork/H、研究标签或正式场景**。它不是外部执行准入通过，也不将历史 `unknown` 直接改为许可。

## 实际取得的材料

来源仍为[同一 TTE 修复](https://github.com/ChrisBuilds/terminaltexteffects/commit/b360e0723d2c8e88e7db4f98c162b99b87442bd9)：B=`bb541505aa05d12e6f43d62d803b05836a5db09a`，F=`b360e0723d2c8e88e7db4f98c162b99b87442bd9`。新建 depth=2 的只读 Git 存储，以 B 为 shallow 边界，取得两个提交的完整树与对象；没有检出或执行代码，也没有省略媒体。它不是完整历史 clone，不替代既有独立谱系审读。

F 全树 **369 文件 / 108,610,617 bytes**，对象库存储实测 **98,746,121 bytes**；B/F 各有 **80 个完整包文件**，包内变动仅 `terminaltexteffects/utils/colorterm.py`。F 唯一父提交为 B，Git 完整性、原始 blob framing/摘要、路径、分批大小/累计/时间与 Python/依赖声明检查实际通过。

原 `test_fg_invalid_hex` 的 **6 个参数、ValueError 及消息 `Invalid RGB hex color code`** 已由新 projector 完整机械提取，生成了未提交 H 的契约提案。仍是[原六个输入](../../research/hex-validation-comparability.md)，没有重写测试、删参数或先验造一个最小失败集。实际 B 哪些 case 失败，必须等待获批后的真实捕获。

固定 webcolors `6c8da6832eb4ae2591a1883a0d1371263d6cd4db` 的 `webcolors:normalize_hex` 完整只读检查也通过：**39 文件 / 204,253 bytes、完整包 6 文件**。目标 LICENSE、格式文档、函数/原测试依据均保持原始 pin。独立自身 oracle 草案仍为 ValueError + 字面量 `not a valid hexadecimal color value`，不替换来源消息，不生成标签。

## 发现并修正的真实误判

首次完整准备拒绝 TTE：`snapshot_uninstalled_static_import:__future__`。全包只读 AST 诊断确认，非允许列表项只有这个编译指令模块，未发现其他显式第三方依赖；PEP 621 静态零运行时依赖、requires-python=`>=3.8`，无根 setup.py/setup.cfg。

`__future__` 属于标准库，已在独立快照 profile 中按标准库处理，并禁止目标包遮蔽它；没有安装依赖或改变旧 preflight。新增单测，源与目标的真实 Docker 自有 fixture 也包含 future 指令。原失败回执保留，修正后的新目录记录另存，不覆盖旧结论。

实际准备的机器事实与私有回执摘要见 [summary.json](summary.json)。完整契约/自身 oracle 提案、执行方案和原始 Git/日志只留本地，未因只读准备而公开或执行。

## 下一道门

当前通道只接受工具自有 fixture，真实 TTE 没有 fixture 标记，也不会补标记取得执行能力。后续必须单独批准并实现外部用途、通过其自有 fixture 资格，审核完整来源/目标和两个独立执行锚，再由所有者 fork/H 流程把原契约纳入实际 H。

之后才能进行双向捕获、真实最小 Guard、自检、完整目标映射及独立自身观察。任一 Git/容量/许可/源链/运行条件未过就停止，不能以只读检查通过代替它们。语义裁决、特征/拟合适配与足够的项目隔离数据也未完成，正式研究场景仍为 **0**。
