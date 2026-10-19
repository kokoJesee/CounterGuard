# 小型 RGB 目标的有界筛查

本批预算为 **5 个发行包，已用尽，停止同方向扩搜**。新增可接纳比较目标为 0；已有 termcolor 来源闭环仍为 1，完整跨项目研究场景仍为 0。
本轮仅做只读 Git/AST 筛查和方案准备，没有 import、安装或执行候选代码，没有新增 fork/H、可执行契约、研究标签或 profile。

与上一批不同，本批找到了更具体的合法差异线索：**colored 的上游测试明确要求夹紧越界 RGB，并有能接收全部来源元组的普通 cprint 入口**。
当前仍有两项准入阻塞，但明显比 Click 的完整包问题更集中。建议评审[受限支持提案](../../experiments/scope-v2/colored-minimal-support-proposal.md)，不自动实施。

基线提交为 `5f2924dee4874fc4720c49f76e7cb02d74770782`，产品源码仍为 `c1a2d24bc271e8d482644f61c1c338e4a41e9b2a`。
来源/接口/许可依据见[一手调查](../../research/bounded-rgb-targets.md)，每项固定 SHA、文件 pin、首个阻塞及未测项见
[逐项回执](../../../benchmarks/v2/rechecks/bounded-rgb-targets-v1.jsonl)，[保护项核验](audit.json)另列。

## 方法与计数

先固定候选发行包，再确认官方源码 URL、完整提交、许可文件、项目声明、普通用户入口和根包。
元数据已明确超出当前支持时就在此停止，不追历史、不运行安装脚本、不因 README 写“无依赖”代替声明。
仅对通过这一步的 colorist、colored 实际运行严格 preflight 和完整树/直接定义闭包检查。

- 候选数 5；正式 CLI preflight 2 次；元数据提前停止 3 项。
- 两个现代包均完整读取固定 Git 树并做角色诊断。colored 后续另核查同一项目 cprint 入口，不算第六个候选。
- 各自上游测试未执行；没有把未跑的 preflight、闭包或 Docker 写成通过。
- 比较目标不要求自己的 B/F/H 来源链；本批没有以“找不到目标修复”为淘汰理由。
- 所有材料已被开发者阅读，holdout_exposure=known_development_probe，不当作盲测留出。

官方源纠错保留：colorist 首次误用的 `/colorist` 地址返回 Repository not found；官方 PyPI 指向 `/colorist-for-python` 后才固定提交。
colored 的 GitHub 地址只是未核实建议，没有克隆；按官方 PyPI 改为 GitLab。它们都是同一发行包的来源确认，不增加候选数，也不覆盖首轮失败。

## 逐项处置

| 候选 / 固定 SHA | 真实接口与语义线索 | 本轮最早阻塞 / 实测结果 |
|---|---|---|
| colorist `d23bee9dc3607e777f92a33df330243457d1b0ca` | 普通 rgb/bg_rgb(text,r,g,b)，逐通道范围错误拒绝；不能误写成只有类接口 | preflight 4；完整定义闭包 58 文件，colorist.model.abc 命名空间边界 blocked，根导出 export_direct_child_required |
| sty `6f1774ef260be04bac356c101e3fca0ae5b38c70` | fg/bg 为可调用 Register；普通低层 renderer 不是相同用户入口 | 只有旧 Poetry 元数据，没有 [project]；在元数据阶段停止，未跑 preflight/闭包 |
| ansicolors `c965f5b9103c5bd32a1572adb8024ebe83278fb0` | 普通 color(s,fg/bg=tuple)，能表达全部 8 个输入；域外 tuple 直拼是待定缺陷线索，不能当合法反例 | 无 PEP 621、只有 setup.py；元数据提前停止，不执行脚本推断依赖 |
| colored `f3d799873a7cde62f3c43d74ed6ffc258240d956` | 普通 fore_rgb/back_rgb 有夹紧测试；普通 cprint 接受前景/背景原元组 | preflight 4；完整定义闭包 12 文件，仅 3 条类/元类 __getattr__ 被保守规则判成模块钩子；根导出仍 unsupported |
| rgbprint `d001f45bc5a527220f881b47ff85ac1dc191a5d4` | 普通 rgbprint(*values,color=tuple)；只找到前景映射，内部另有类/元类 | 无 PEP 621、setup.py 元数据；提前停止，不为准入换用内部 helper |

严格 preflight 不等于 source-only：colorist/colored 的 conftest 只说明原测试 bootstrap 存在，本轮没有加载它们。
source-only 的实际阻塞另行记录；没有把 colored 的静态省略 dependencies 误判为一定需要安装依赖，也没有因此跳过完整闭包。
相反，sty/ansicolors/rgbprint 的运行闭包**未测**，不能沿用先前同族库的结论。

colorist 的元数据明确 dependencies=[]；其 root 多层重导出和缺少传统 __init__.py 的内部命名空间仍超出当前 profile。
三标量接口可自然表示 4 个三分量越界输入；两组长度错误不能由适配器先解包失败冒充目标处理，未获完整 8-case 映射批准。
不同 ValueError 消息只能保留为规范差异线索，不能改来源 oracle 或自动赋不适用标签。

sty 的异常/范围容忍规范仍不确定。ansicolors 虽有三元素 0–255 的文档描述，但域外行为是否承诺必须拒绝还需规范裁决，
不能把静态透传直接当成已验证缺陷，更不能当成已确认合法反例。rgbprint 未发现背景入口，不复制前景运行充当背景样本。
本批均未使用 validators、pytimeparse 或 termcolor 衍生实现填数，也未复制 GPL 候选源码进产品。

## colored：保留全部输入的目标提案

初筛诊断的 `colored:fore_rgb` 入口和原始回执保留。阅读同一固定版本的公开 cprint 签名后，另提出 `colored:cprint`：

```text
source text                → target text（原样）
source color=<rgb tuple>   → target fore_rgb=<same tuple>
source on_color=<rgb tuple>→ target back_rgb=<same tuple>
source force_color=True    → 显式记录为来源到达校验的控制项，不盲传给无此参数的目标
source ValueError + match  → 原断言保留，不改成“接受夹紧”或其他消息
```

8 个源 case 的文本、RGB 元组、case ID、原断言摘要和完整 match 均保留在
[映射工作表](colored-cprint-proposal.json)中。这里的 **8/8 是字面量调用表示提案**，不是已裁决的语义映射、可执行契约或运行结果。
没有执行适配器、选择性删掉长度 case、执行目标，或按 replay 结果挑入口。

`cprint` 内部的 resolve_foreground/resolve_background 自己解包元组：长度错误的 ValueError 会发生在目标内部，
与适配器在调用前解包报错不同。完整路径还需后续准入与 Docker 核对，不能仅凭静态推导标为已通过。

最强的规范依据是上游 `test_fore_rgb_clamping`：它明确要求 `(300,-1,128)` 转成 `(255,0,128)` 的 ANSI 序列；
Utilities.is_percentage 的固定实现也逐分量 clamp。这是目标有意的语义选择，支持“拒绝要求未必适用”的合法反例假设。
它不是目标漏拒绝已成立的证据。该测试直接见证低层 fore_rgb；cprint 调用它的路径来自固定源码，仍须独立审核并实际验证。
[固定测试](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/tests_pytest/test_colored.py)、
[固定入口](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/cprint.py)、
[固定夹紧实现](https://gitlab.com/dslackw/colored/-/blob/f3d799873a7cde62f3c43d74ed6ffc258240d956/colored/utilities.py)

与 Click 的消息差异相比，这里还有**拒绝与夹紧**的政策差异，研究价值更明确。
但单个来源、单个合法差异候选不足以证明跨项目泛化、最终留出缺陷检出或样本规模目标，仍需如实列出限制。

## 仍不能执行的两条边界

1. 现有根导出 grammar 拒绝 colored 根包：多个直接子模块导出，另有带类型注解的字面量版本赋值。
   不能把直接模块诊断当作根包绑定已通过，不能删掉根包或用包装器篡改异常。
2. cprint 完整闭包有 12 文件、3 条 module_lookup_hook_requires_review。AST 定位表明它们分别是 MetaStyle、MetaBack、MetaFore 的类/元类方法，
   不是该文件的模块级钩子。但“检查器把作用域混在一起”不等于这些动态行为自动安全，更不允许现在清零 finding 放行。

类/元类构造、输入相关异常、模块末尾 Windows 终端初始化、环境读取和 ctypes 分支仍属于待审完整源码。
预定 Linux Docker 的平台条件必须在授权、输入与运行环境中明确；本轮没有靠宿主平台裁剪代码或绕过隔离。

## 收束与待维护者决策

预算用尽，**不再自动搜索第六个候选**。下一步只提交两条范围选择：

- 选择实施 colored 的[受限支持提案](../../experiments/scope-v2/colored-minimal-support-proposal.md)：版本化根导出绑定和精确作用域/有限类钩子审查，
  先跑工具自有专项；目标真实执行仍等独立研究桥接和全部安全准入。初估 3–6 人日，不做 legacy、kwargs 提取或 Click 支持。
- 暂不扩张 profile：保留当前跨项目 insufficient_data，缩窄本轮可交付主张。已完成的真实来源复现与机制验证可独立交付；
  不能把它们改称跨项目收益，也不能未经确认改成同项目探索轨。

两者都没有在本轮自动执行。停止扩搜是按本批预先约定收束，不表示跨项目研究已经完成。

## 重复命令

固定 URL、SHA、选定源码与许可 pin 在机器回执中。在完整 clone 之外运行：

```powershell
counterguard preflight --repo <candidate-clone> --revision <fixed-full-sha>
git -C <candidate-clone> show <fixed-full-sha>:pyproject.toml
git -C <candidate-clone> show <fixed-full-sha>:<selected-source-ref>
```

本轮 colorist 和 colored 的正式 preflight 都退出 4；其他三项未跑。直接定义闭包和根导出判断使用现有工具函数，
通过完整树读取后分别调用并分别记录拒绝，不因一个步骤出错就将后续未运行项写为通过。
复核 cprint 使用 `colored.cprint` / `cprint` / `colored/cprint.py` / import_root `.`，根绑定仍为 `colored:cprint`。

本轮无产品代码变更：Ruff、链接、固定 Git 对象/摘要、保护项和隐私按 audit 实测；未重跑快层、全量或 Docker。
网络获取计时、命令计时分别保存；人工审阅与总接入耗时不完整，保持 null，不据此声称达到 30 分钟门槛。
