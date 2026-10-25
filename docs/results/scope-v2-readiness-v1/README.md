# scope_v2 正式准入门（v1）

这份回执把研究主线的当前状态做成机器可核验的闭合世界记录。它固定输入文档、候选登记、
两份真实外部观察和工程资格回执的内容摘要，并检查所引用实现提交仍存在。

```powershell
uv run python scripts/check_scope_v2_readiness.py `
  --readiness docs/results/scope-v2-readiness-v1/readiness.json
```

当前预期退出码是 **4**，输出 `status=verified`、`outcome=insufficient_data`、
`next_phase_allowed=false`。退出 4 表示记录有效但下一阶段仍被数据门槛关闭；退出 5 才表示记录、
摘要或源码绑定损坏。

当前固定计数：

- 候选记录 20：结构化登记 13 条，最新只读续查 7 条；
- 已验证真实来源修复 2；
- 已执行外部观察 pair 2；
- 正式准入场景、冻结 train/holdout、正式 fitted Guard 槽位均为 0。

工具自有 fixture 的 Docker、fit 和四方法回放只证明实现链路，因此只作为
`engineering_qualification` 输入，不能增加真实研究计数。该门禁也不授权外部执行或语义标注。

## 阶段结论

本轮可行性研究在 2026-10-25 以 `insufficient_data` 关闭。研究规格要求先证明正式跨项目场景，
再物化正式协议、真实标签、split 和 fit；当前没有满足这一条件，因此后续正式数据阶段没有被假装执行。
已有代码、fixture 与两组外部观察均保留为下一轮输入，但不能据此宣称四方法真实实验已经完成。

重新开启时必须新增至少一条通过语义裁决的正式跨项目场景，并另开 readiness 版本；不得覆盖本回执。
