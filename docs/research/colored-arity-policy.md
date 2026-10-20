# colored RGB 长度政策的有界调查

2026-10-20 补查了 `colored:cprint` 的文档分支、引入历史和定点 issue/MR 查询。
结论仍是：**四个二/四元组输入缺少独立的异常类型/消息规范，不能纳入已确认合法反例。**
来源 Guard 的八个 case 和既有观察全部保留，不删除输入或放宽消息 oracle。

## 新增的一手依据

代码快照保持 `f3d799873a7cde62f3c43d74ed6ffc258240d956`。
另将上游 site 文档固定为 `ad5d82d71479b6c92d460b180fcbc298cc3c180a`；
该文档不属于代码快照的提交树，未作为新的执行或标签授权输入。

| 固定来源 | 能支持的结论 | 不能支持的结论 |
|---|---|---|
| [API 参数表](https://gitlab.com/dslackw/colored/-/blob/ad5d82d71479b6c92d460b180fcbc298cc3c180a/docs/api/functions.md#L87) | 前景/背景 RGB 参数按三通道描述 | 二/四元组必须抛某类异常或兼容 termcolor 消息 |
| [异常文档](https://gitlab.com/dslackw/colored/-/blob/ad5d82d71479b6c92d460b180fcbc298cc3c180a/docs/api/exceptions.md#L1) | 明确列举颜色名、HEX、样式、控制符等错误 | 将这些政策移用为 RGB 长度错误规范 |
| [3ed4a56](https://gitlab.com/dslackw/colored/-/commit/3ed4a56ce61d371153dcee140b57df3ba5d5d005) | 三项类型注解的历史依据 | 运行时异常或消息承诺；该补丁未加入相关测试 |
| [1be86a0](https://gitlab.com/dslackw/colored/-/commit/1be86a0bf3c1380e714a8d8619570a7683e1dcc6) 与[变更说明](https://gitlab.com/dslackw/colored/-/blob/ad5d82d71479b6c92d460b180fcbc298cc3c180a/docs/changes.md#L27) | tuple unpacking 变动用于 mypy/pylint 告警修复 | 把提交标题当作非法长度输入策略 |
| [RGB 引入历史](https://gitlab.com/dslackw/colored/-/commit/feb49e533ce02f5114f70c1a1815d567140d93ac) | 最初实现直接三项解包 | 把解释器产生的错误升级为独立规范 oracle |

本轮命中的 #120 / MR !20 关联提交涉及省略颜色参数时的默认色，与长度错误无关。
完整 issue/MR 正文讨论未取得，不能声称已排查其中全部内容。

## 检索边界

共使用八项定点网络请求/检索：四次 Web 访问未取得正文，两次定点搜索没有相关结果，
两次直接 GitLab issues/MRs API 以 `search=rgb` 查询，均 HTTP 200、正文为 `[]`。
后两次不是 API 故障；空列表不证明其他关键词、私有/删除内容或所有讨论均无相关政策。
另只读既有 Git 对象中的相关 cprint/RGB/测试及文档补丁，没有扩搜其他项目。
原始响应和本地命令日志留在仓库外，不发布系统路径或控制脚本。

可重复的固定 Git 读取：

```powershell
git -C <colored-object-store> show ad5d82d71479b6c92d460b180fcbc298cc3c180a:docs/api/functions.md
git -C <colored-object-store> show ad5d82d71479b6c92d460b180fcbc298cc3c180a:docs/api/exceptions.md
git -C <colored-object-store> show 3ed4a56ce61d371153dcee140b57df3ba5d5d005 -- colored/cprint.py
git -C <colored-object-store> show 1be86a0bf3c1380e714a8d8619570a7683e1dcc6 -- colored/utilities.py
```

未决 case 为 `case_942019cec8bae1dea1bc3460`、`case_a49a01cfad8d0af1e6973391`、
`case_c231f71510e8045580409a5e`、`case_f16a157710addc6257cec33e`。
它们超出所描述的参数形状，这可以作为后续人审材料，不能自动改变既定比较域或生成 Gold。
本轮目标执行、Docker、标签和新研究场景均为 0；[先前真实观察](../results/colored-observation-v1/README.md)仍为探索结果。
在当前标准下该 pair 继续不进入正式 refinement，研究工程可用自有 fixture 推进，不能靠反复跑容器补出规范。
