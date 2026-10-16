# 通用契约与来源绑定验收

本次交付 contract.v3 / standalone-literals.v1 与只读 prepare、bind、verify-binding。
详细[使用与限制](../../standalone-contracts.md)。它不是新的可执行 profile，不代表通用接入或真实 CI 已完成。

## 实测范围

- 工具自有的真实 Git fixture，分别使用根布局与 src 布局；B→F→H 均为实际提交，H 单独新增契约。
  目标包、上游测试与 conftest 含拒绝执行哨兵，所有操作只读 Git/AST，未执行这些文件。
- 两种布局均完成准备、H 内契约绑定、独立重建与重复字节一致检查。
  删除工作树 conftest、改写本地源码/契约，不会改变提交来源结论；以 F 冒充 H 时保留契约缺失拒绝。
- boltons 的真实 B=55dfe5077bcb5fa76611b5f2a557ea6c442ad87c、
  F=1e61524a798ea73632029a013a7686036d5c126f 完成契约准备，覆盖 12 个直接断言，1 个嵌套断言明确 unsupported。
  模块中的动态 lookup 保持 unknown；没有声称整个模块已审核。
- boltons 尚无本次契约的真实所有者 H。以 F 为 assertion head 的实际 CLI 返回 **5 / contract_missing_from_head**；
  工具没有注入文件、创建 owner 提交、checkout 或执行 boltons。准备命令返回 **4 / 需人审**。

复验命令（所有输出路径均须新建）：

```powershell
counterguard contract prepare --repo <boltons-clone> --buggy 55dfe5077bcb5fa76611b5f2a557ea6c442ad87c --fixed 1e61524a798ea73632029a013a7686036d5c126f --contract-id boltons-singularize.v1 --target boltons.strutils:singularize --import-root . --test-ref tests/test_strutils.py --test-function test_singularize_double_s --output <fresh-preparation-directory>
counterguard bootstrap bind --repo <boltons-clone> --head 1e61524a798ea73632029a013a7686036d5c126f --contract-ref contracts/boltons-singularize.v1.json --output <fresh-refusal-directory>
uv run pytest -m "not slow" -q
uv run pytest tests/integration/test_bootstrap_binding.py -q
uv run ruff check .
```

前两项是正常返回 4 和 5 的准入记录；不能把它们改成绿色结果。
fixture 的来源绑定核实不等于缺陷复现；各报告 execution_allowed=false、capture_available=false、reproduced=null。
机器验收摘要见同目录 acceptance.json；原始绑定、日志、源码快照和未发布准备文件只留本地。

## 重算与剩余门槛

新工具源码改变当前来源摘要；所有新实测使用新命名空间，旧记录不补签，不改冻结 benchmark/experiment/split/context。
发布前补充了写入端与读取端一致的字节预算，早期本地检查/准备目录保留，不当作最终版本的验收结果。

下一环仍需 contract.v3 的可信测试生成器和逐次重建的 Docker 授权器、真实 B/F RunRecord 与 JUnit/日志、
最小失败集编译/自检及独立验证。之后才可产生 reproduced Evidence、精确快照 Scope 和 Shadow。
owner H、语义审核、运行输入 unknown/blocked 任何一项未关闭，都不能用本地执行或重签记录替代。
