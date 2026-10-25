# 查找已审核 runner

用户无需从开发记录手抄镜像摘要：

```powershell
uv run counterguard runner list
uv run counterguard runner list --format json
uv run counterguard runner show validators-pytest9
# 只看发布的审核来源，不连接 Docker
uv run counterguard runner list --offline
```

`runner list` 只运行有时间/输出预算的 `docker image inspect`，不运行镜像、不拉取、不构建、不加载镜像，也不执行项目。每项显示稳定 runner ID、profile、完整 image ID、本机可用状态、构建与攻击复验收据及其摘要。JSON 还包含基础 registry digest、pytest 版本、runner 源码摘要、锁摘要和审核时间。

`available` 表示本机确有与审核记录一致的 image ID；只有此时 `usable=true`。镜像缺失或 Docker 不可访问显示 unavailable；没有任一可用项时命令返回 3，但仍输出来源记录。`--offline` 显示 not_checked、usable=false，返回 0 只表示目录读取成功。审核过不等于本机已安装。

## 用稳定 ID 执行

```powershell
uv run counterguard verify --repo <repo> --base <base-sha> --head <head-sha> --config <config.json> --registry <registry> --runner-id root-pytest8 --output artifacts/verify/check-v2
```

validators 固定仓库使用 `--runner-id validators-pytest9`。两者属于不同 profile，不能因一个镜像较新就交换使用。

原 `--image sha256:...` 选项保留，但只接受目录中已有审核的精确 ID；未知 ID 被拒绝并写出完整性失败报告。`--runner-id` 和 `--image` 必须二选一，不接受浮动 tag。实际执行前后仍重建原有授权，runner 目录不能替代 Guard/Evidence、状态、契约来源、Scope 或 Docker 隔离检查。

## 审核来源与交付边界

目录是安装包中的 `data/runner-catalog.v1.json`，其完整内容摘要固定在可信宿主代码中；各 review 另有自摘要。只改目录并重算自摘要不能批准新镜像。`verify-report.v2` 记录选中的 runner ID、image ID 和 review digest，各行也绑定同一审核记录。目录只信任当前安装的 CounterGuard；它不是签名服务或用户身份系统。

`runner-discovery.v2` 在探测任何本地镜像之前，会逐项读取安装包内 `data/runner-receipts.v1/` 的四份 build/attacks 收据：

1. 比较各收据的规范化摘要与已固定的 review；
2. 交叉核对 image ID、lock digest、基础 registry digest、runner 源码和 pytest 版本；
3. 核对四项攻击的 accepted / exit / passed / log digest。

收据缺失、被篡改、重算自摘要或超出预算，都会让整体退出 5，不输出部分 available。`resolve_runner` 走同一核验，`--image` 也不能绕过。安装包内自带收据，不依赖源码仓库的 docs 路径或网络获取。
输出的 docs 引用是公开来源地址，实际核验的是包内对应副本；两者发布时应逐字节一致。

因此，available 的准确含义是：**安装包固定审核链/收据完整，而且本机 image inspect 的精确 ID 相同**。
发现命令没有重跑攻击或读取已归档原日志，只核对审核记录绑定的日志摘要；它也不认证审核人的身份。
若攻击者连可信 CounterGuard Python 代码及其 pin 一起替换，本机制不能检测安装包整体失陷。
镜像身份只是必要边界之一，实际执行仍需来源、Scope、状态和固定 Docker policy 的独立授权。

两项 profile 的来源见 [构建/复验记录](results/runner-catalog-v1/README.md)。该历史构建轮次没有公开交付镜像；
之后的 [0.5.0 Beta](beta-release.md#发布内容) 已在 GitHub Release 附带 root runner 的精确归档和摘要，未发布 OCI 镜像仓库。
validators-pytest9 归档不在这 6 个附件中。其他机器若没有相应 image ID，会明确显示 unavailable，不把同名 tag 当成已安装或已审核。

需要自行重建时，使用现有 Dockerfile（pytest9 通过 `--build-arg PYTEST_VERSION=9.0.3`），在新目录运行 `scripts/record_runner_build.py` 和 `scripts/accept_pilot_runner.py`。新 image ID 只有在锁定、四项攻击实测并经维护者审核后才进入新目录版本；当前没有“信任任意本机镜像”的快捷开关。构建归档与原始日志默认只留本地，不提交到源码 Git 仓库。
