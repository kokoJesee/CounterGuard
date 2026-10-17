# 受限通用 Docker 双向捕获验收

交付 [`bootstrap capture` / `bootstrap verify-evidence`](../../standalone-capture.md)：
当前 H 契约、逐角色 B/F 来源、可信测试生成与专用授权，在既有封闭 Docker policy 下产生 `evidence.v4`。
最小 Guard 编译/自检、精确快照 Scope 和 Shadow/Registry 仍未交付；不能把首次 Evidence 当作完整接入。

## 实测

| 检查 | 结果 |
|---|---|
| 快速层 `uv run pytest -m "not slow" -q` | 767 passed、210 deselected，104.28 秒 |
| 捕获、绑定、计划和准入单元专项 | 109 passed，37.29 秒；与快速层有重叠，不能相加为测试总数 |
| 真实 Docker 捕获专项 | 3 passed：根布局、src、导入故障；根布局另做一次固定提交重复捕获 |
| 未修改的四项 Docker 攻击复验 | 4 passed；与上一行合并运行共 7 passed、无 skip，230.26 秒 |
| Ruff | `uv run ruff check .` 通过；新增 Python 文件格式检查通过 |

按约定未跑全量。上表仅表示本机当前实测；不是跨平台、真实 GitHub CI 或全面安全审计。

两种布局均采用**工具自有**真实 Git B→F→H fixture，H 独立新增契约，不能当成外部开源仓库的缺陷。
每个契约有 2 case：正常 B 运行 1 pass / 1 fail、exit=1；F 为 2 pass、exit=0。
Evidence 只标出 1 个真实失败 case。根布局固定提交复跑的逐 case 结果一致，run ID 各自独立，完整摘要不伪造成相等。

目标含容器身份哨兵；宿主目标 import 和本地执行器一旦调用测试就失败。
上游测试模块、conftest 含拒绝加载哨兵，配置故意要求不可用 pytest/plugin。
容器实际只挂载角色源码闭包、H 契约及生成测试，正常捕获成功表明这组隔离行为确实运行过。
这不表示任意项目不需要 conftest/fixture，也不授权忽略目标自身的未知依赖。

另一个 B 在导入时抛 ImportError：真实 pytest exit=2，F exit=0；Evidence 为 reproduced=false、失败集为空，
独立核验退出 3。该记录作为基础设施失败保留，未算作成功缺陷复现。

攻击测试继续覆盖网络/只读/非 root 控制、日志洪泛、超时后的子孙清理，以及真实 Inspection/授权路径。
新单元测试还覆盖请求/角色/超时/封闭 policy/测试及来源漂移、原始日志与重签结论篡改、
未知输入不启动 Docker，以及执行后的晚到修改不得留下成功 Evidence。

## 复验

```powershell
counterguard runner list --runner-id root-pytest8
$env:COUNTERGUARD_RUNNER_IMAGE_DIGEST='sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16'
uv run pytest -m "not slow" -q
uv run pytest tests/integration/test_standalone_capture.py tests/integration/test_docker_runner.py -q
uv run ruff check .
```

真实 Docker 专项必须显式设置目录中的精确审核 image ID；未设置会 skip，不能当作通过。
所有新真实进程测试标为 slow。独立核验会读取 Git 原始对象，但不执行目标源码或启动容器。
执行时使用当前源码生成全新绑定，旧 binding v1、授权和来源绑定产物不补签。

机器摘要见 [acceptance.json](acceptance.json)，它是筛选字段的验收收据，不是原 Evidence 或其授权替代品。
摘要标注真实源码基点、dirty 状态和逐文件源码汇总摘要；不能将工作区实测冒称为历史 commit 实测。
原始 argv/日志、Git fixture 与完整输出只留本地，避免公开工作站路径。
根布局第二次捕获和导入故障 Evidence 保持原样并再次独立核验；首轮根/src Evidence 在专项末尾被故意重签失败集，
现为拒绝样本。收据明确区分这两种状态，没有恢复/覆盖旧记录或给篡改后的文件贴有效标签。

## 重算与剩余边界

新 binding v2、授权 v4、Evidence v4 与生成器参与全包源码摘要；新记录必须新命名空间。
旧契约/实验/标注/上下文/已有产物、Dockerfile/入口/policy、runner catalog/镜像及版本标签均未改。
本轮正常启动了既有 Docker Desktop，未更改其持久设置或构建/替换镜像。

本机审核理由不是身份认证，Git 完整性不能认证所有者；Docker 不证明恶意目标未干扰 pytest/JUnit。
通用 Guard、Scope/Shadow、原生 pytest 引导、依赖安装和远程 CI 权限仍需独立准入。
此前 boltons 的所有者 H 缺失/动态 lookup 未解决；本轮没有替其制造提交、隐藏 finding 或执行其源码。
