# Evidence 版本、有效性与历史记录

新捕获使用 `evidence.v2`。推荐 ID 为 `<语义名称>_v1`、`<语义名称>_v2`；末尾的版本表示捕获修订，不是业务契约版本或开发日期。新捕获拒绝 `_d4`、`_d5` 等日程后缀。历史 v1 记录保持原始字节、ID 和 digest，不重命名、不覆盖。

| 字段 | 规则 |
|---|---|
| `capture_revision` | 首次捕获为 1；重新捕获必须为前驱修订加 1 |
| `supersedes` | 前驱的 `evidence_id`、工作区相对 `evidence_ref` 和 `artifact_digest` |
| `recapture_reason` | 非空的重新捕获原因，与 `supersedes` 同时提供 |

如果 ID 使用 `_vN` 后缀，N 必须与实际修订一致。旧 `evidence.v1` 在替代链内按修订 1 处理，但不向旧 JSON 注入新字段。同 ID 请求只能验证后复用；改变输入、替代关系或原因必须创建新修订。允许从测试源码已变更的前驱重新捕获，但前驱 JSON 和整条替代链必须完整，且 contract ID 保持一致。

## 唯一有效性标准

**Evidence 能用于新的编译工作的唯一标准是 `evidence verify` 返回 0。** 这要求 Schema、自身摘要、契约、测试、两个目标、运行日志及替代链校验通过，并且双向运行确实满足 `reproduced=true`。文件存在、名称更新、Git SHA 或 JSON 中单独的 `reproduced=true` 都不能代替验证。

- `verified` / `usable=true`：验证返回 0。
- `diagnostic` / `usable=false`：内容完整，但没有复现，或存在运行基础设施错误。
- `invalid` / `usable=false`：引用缺失、摘要不符、Schema 不支持或替代链损坏。
- `eligible=true`：可用且没有被另一份验证通过的 Evidence 显式替代，可作为默认新工作候选。

“过期”和“已替代”是两件事。源码变更导致验证失败的旧记录过期；仍验证通过但有可用后继的记录只是不再默认选用。诊断性后继不能淘汰有效前驱。显式审核旧资产仍然允许，但必须再次通过 verify。

目录扫描必须调用 `inventory_evidence`，逐份执行与 CLI 相同的完整验证，不能靠文件名选最新版。遇到分支后继保留全部可用末端，不任意裁决。扫描不会删除或修改历史记录：

```powershell
uv run evidenceguard evidence inventory
uv run evidenceguard evidence verify artifacts/evidence/evd_discount_v1_member_rate_fix_v2/evidence.json
```

inventory 返回 0 只表示检查完成；消费者必须读取每行 `usable` / `eligible`，不能把命令成功当成目录内全有效。

## 重新捕获与 Guard 迁移

```powershell
uv run evidenceguard capture --evidence-id evd_discount_v1_member_rate_fix_v2 --contract examples/discount/contracts/membership_discount_final_price_v1.json --test tests/contract_tests/test_membership_discount_v1.py --buggy-target examples.discount.implementations.final_price_v1_buggy:calculate_price --fixed-target examples.discount.implementations.final_price_v1_fixed:calculate_price --supersedes artifacts/evidence/evd_discount_v1_member_rate_fix_d4/evidence.json --reason "Adopt semantic capture revisions and explicit replacement provenance; retain the verified exception whitelist and isolated execution harness."
```

以上命令用于已有 D4 前驱的工作区。干净检出执行 `uv run python scripts/prepare_scope_v1.py`：它创建语义 v1 前驱，再捕获 v2；已有 v2 时验证并复用，不改实验协议。

生成器升级为 `guard-test.v2`，缺少目标环境变量时给出 `pytest.UsageError` 和 CLI 使用方式；不跳过断言。新的两份 Guard 使用 `_v2` ID、`guard_version=2`。旧 v1 模板仍可加载与审计，旧资产保持不变。
