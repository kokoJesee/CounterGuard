# 受限的异常消息断言

契约提取器支持以下形式，异常类型仍限 ValueError、TypeError、OverflowError：

```python
with pytest.raises(ValueError, match="Expected a tuple of 3 ints in range 0-255"):
    target((0, 0, 256))

with pytest.raises(ValueError, match=r"invalid\[value\]"):
    target(-1)
```

`match` 必须是源测试中的字符串字面量，最长 4096 字符。保留原始模式，不自动加锚点、不自动 escape、不把它丢掉后只检查异常类型。无消息断言的 raises 行为保持原样。

## 接受的范围

只接受普通文本，以及转义后的正则标点和 `re.escape` 可能产生的有限标点转义。支持空字符串、Unicode 和字面量换行。空模式与 pytest 一样不增加文本约束；审核者应注意它的约束强度。

未转义的 `. ^ $ * + ? { } [ ] | ( )`、字符类、分组、重复、交替、锚点、flags、反向引用、`\d` 等转义和悬空反斜杠均返回 `exception_match_regex_unsupported`。本版宁可拒绝简单的锚点，也不把任意 regex 当纯文本解释。

变量（包括参数名）、f-string、函数调用、`re.compile`/`re.escape` 调用和非字符串返回 `exception_match_literal_required`。即使调用结果可能是字面量，扫描阶段也不执行它。`as exc`、多异常元组、check 回调、关键字展开和用户异常类继续 unsupported。部分断言不支持时保持逐条覆盖计数，不丢弃该条记录。

pytest 的 match 使用 `re.search`，会搜索异常字符串及 PEP 678 notes，允许匹配其中的一段。[pytest 官方语义](https://docs.pytest.org/en/stable/reference/reference.html#pytest.raises)是这里的依据。生成测试把已验证的模式原样交给已审核 runner 内的 `pytest.raises(..., match=...)`，由 pytest 执行类型和文本检查；宿主扫描器只做有界字符检查，不编译模式、不 import 目标。

## 格式与兼容

| 内容 | 原有无 match 格式 | 含受支持 match 的新格式 |
|---|---|---|
| 草案 | contract-proposal.v1 / literal-test-projection.v1 | [contract-proposal.v2](../schemas/contract-proposal-v2.schema.json) / literal-test-projection.v2 |
| H 内契约 | contract.v3 / standalone-literals.v1 | [contract.v4](../schemas/standalone-contract-v4.schema.json) / standalone-literals-match.v1 |
| 捕获计划与生成器 | standalone-capture.v1 / standalone-test.v1 | [standalone-capture.v2](../schemas/standalone-capture-v2.schema.json) / standalone-test.v2 |
| 最小 Guard 与生成器 | guard.v3 / standalone-guard-test.v1 | [guard.v4](../schemas/standalone-guard-v4.schema.json) / standalone-guard-test.v2 |
| Registry 条目 | registry-entry.v3 | [registry-entry.v4](../schemas/standalone-registry-entry-v4.schema.json) |

新 case 在原 raises 字段之外增加必需的 `exception_match`。新契约可以混合原 case 与消息 case。旧 Schema/模型保持原样，读取新字段或新版本会拒绝；新读取器按显式版本分派，不能降级为“只检查异常类型”。捕获/Guard 生成器版本与契约版本必须一致。

case ID 继续绑定原断言 AST 和完整片段，match 改动会改变 ID 与投影摘要；相同输入重复结果稳定，注释/行号变化不改变 case ID。原来已支持且不带 match 的 case 字段、ID、契约和规范测试字节保持兼容。

这只扩展字面量 oracle，不增加 legacy 元数据、重导出身份解析、callable-object、fixture、插件、安装依赖或研究 Scope 支持。必须仍从真实 B/F 与 H 内原始测试重建，所有者审核之后才能进入 Docker；提取成功不代表已有失败见证、H 或适用边界。

## 重算规则

已有 artifact 不改写、不补签。需要使用消息 oracle 时，在新目录重新 draft/prepare，由所有者向 F 的单独子提交 H 添加新格式契约，再 bind/capture/compile/register。Evidence 和 Scope 继续绑定完整契约摘要、当前源码、精确快照及审核镜像；不重新解释旧报告。

工具的全包源码摘要发生变化，旧通用绑定、捕获、编译及登记链可能因实现过期被拒绝。即使原契约不带 match，要取得当前实现下的执行结论也须在新 ID/目录重建相关链。冻结 scope_v1、benchmark、examples、旧 artifact、发布 tag 和 Docker policy/runner 收据均不因本功能重写。

只导出本次新增 Schema，避免顺带重写其他历史导出：

```powershell
uv run python scripts/export_schemas.py --only contract-proposal-v2 standalone-contract-v4 standalone-capture-v2 standalone-guard-v4 standalone-registry-entry-v4
uv run pytest tests/unit/test_exception_match.py tests/unit/test_exception_match_pipeline.py -m "not slow" -q
```

真实 Docker 专项是 `tests/integration/test_standalone_capture.py::test_real_docker_message_only_regression_preserves_minimal_oracle_and_registry`，明确标 slow/docker，使用工具自有 fixture。外部候选的重新筛选与准入数量另见研究回执，不能拿 fixture 的执行成功充当真实项目收录。
