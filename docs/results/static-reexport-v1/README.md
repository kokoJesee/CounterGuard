# 根包重导出验收与 termcolor 重查

实现：`c1a2d24bc271e8d482644f61c1c338e4a41e9b2a`。
[接受范围](../../static-reexports.md)、[机器回执](recheck.json)、[原始准备报告](preparation.json)、
[待所有者审核的契约](termcolor-contract.json)、[验证计数](validation.json)。
这里只重查受本功能影响的 termcolor，未宣称又完整筛过 13 个候选。

**根包导出这一项静态阻塞已解除；termcolor 尚未执行，完整接纳场景仍为 0。**
待审契约不是 Evidence、Guard 或所有者认可，也不能作为研究执行授权。

## 原测试入口保持不变

- 上游：<https://github.com/termcolor/termcolor>，MIT；提取测试的许可随附 [COPYING](COPYING.termcolor.txt)。
- B：`db6b299abfec18223a98827f4cd6a7e475b7dfb5`。
- F：`520facb24e5310a6f48736dddfe86164057a322c`，真实 RGB 范围修复。
- 测试：`tests/test_termcolor.py::test_invalid_rgb`，从根包导入 `colored`。
- 公开目标仍为 `termcolor:colored`；声明指向 `termcolor.termcolor:colored`，没有替换调用入口。
- B/F 各自核对 `src/termcolor/__init__.py` 与 `src/termcolor/termcolor.py`，闭包均无 finding，状态为 review_required。
- 保留原有 2 条消息断言、4 组 RGB 参数，共 8 case；没有删 match、改预期或改变 case ID。

prepare 实际返回 **4**：需要人审和所有者 H，不能解释为可直接执行。
新契约 ID 为 `termcolor.colored.rgb-range.v2`、格式为 contract.v5，字节摘要为
`sha256:5f6cf46635476a74668d61c1ea7f5cf99c6601bc3fde705001eb394bde76c180`。
旧消息扩展回执及原 v4 契约不改写。

```powershell
counterguard contract prepare --repo <termcolor-clone> --buggy db6b299abfec18223a98827f4cd6a7e475b7dfb5 --fixed 520facb24e5310a6f48736dddfe86164057a322c --contract-id termcolor.colored.rgb-range.v2 --target termcolor:colored --import-root src --test-ref tests/test_termcolor.py --test-function test_invalid_rgb --output <fresh-preparation-directory>
```

输出必须在 cwd 下、目标 clone 之外，并使用全新目录。只读准备既不 checkout 也不执行目标。
完整仓库 strict preflight 的 pytest 配置等历史 finding 未被删除；该入口另行审核 source-only 契约闭包，
不载入上游配置/插件，不声称整个原生测试套件已经兼容。

## 工程验收与研究数量分开

- 快速层：`uv run pytest -m "not slow" -q`，**882 passed、214 deselected、129.28 秒**。
- 新增 slow/docker 专项：**1 passed、0 skip**，JUnit **185.279 秒**。
  工具自有 src 布局 fixture 中，contract.v5 / binding.v3 保留根包调用；B 真失败、F 通过，
  2 个契约 case 仅 1 个实际失败，Guard v4 保留它并通过 B/F 自检，Registry entry v4 独立核验及幂等登记通过。
- 最终 Docker 专项实际执行 4 次工具 fixture（捕获 2、自检 2）。宿主导入与本地执行器均由测试哨兵拒绝。
  Shadow 转换另有传输替身回归；本专项不宣称真实外部 Shadow 已完成。
- 静态专项覆盖显式别名、相对/绝对导出、模糊模块、条件/动态/重复绑定、默认值/注解、装饰器、AST 预算、
  B/F 任一侧漂移、重签状态和旧格式拒绝；20 次文件顺序扰动的完整绑定与摘要一致。
- Ruff、差异空白和新增文档链接检查通过；未跑全量，未重跑既有四项 Docker 攻击，不扩大其他攻击面的已测状态。

首轮受限文件系统运行因硬链接权限失败；正常权限专项另有两项新测试读错失败报告字段，修正测试后通过。
首轮 Docker 在准备阶段发现 fixture 仍声明直接模块入口，尚未启动目标；修正接线后换新目录通过。
首轮快层会话中断，无最终 JUnit，计数为未完成；补跑用新目录。失败与未完成现场保留在本地，
公开仅提供有限原因、计数与原始 JUnit 摘要，不发布用户名、宿主路径或原始日志。

## 进入来源捕获前还缺什么

1. 仓库所有者审核这份契约的输入、ValueError 消息语义、模块初始化与源码独立性。
2. 在所有者控制的 fork 中，从精确 F 建立独立分支，只新增此契约，形成直接子提交 H。
   提议路径为 `contracts/termcolor.colored.rgb-range.v2.json`；提交说明必须标注 **NOT upstream**。
   本轮没有创建 fork、分支或 H，也没有把本工具的提交当成上游认可。
3. 从 H 重新 bind 并审核，通过后才执行已审核 Docker 中的双向 capture、独立 Evidence 复核与最小 Guard 自检。
4. 研究还需自然可比、谱系独立的目标和研究执行桥接准入；取得一个来源修复不能代替跨项目可行性。

研究 split/protocol/context 未冻结，标签未分配，研究桥接未启动。无新增运行时依赖，冻结 v1 数据、
examples 原实现/契约、既有 artifacts 和 v0.1.0 / v0.5.0 标签均保持原样。
核对范围与字节摘要见 [audit.json](audit.json)。
