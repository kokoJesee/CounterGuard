# Docker 受限执行

W3-B 提供库级 `DockerExecutor`，用于已审核的精确 replay 请求。W3-C Registry 与 W3-D validators 试点通过专用流程接入它；这不构成面向任意仓库的通用执行命令。运行边界和试点准入见[安全模型](security-model.md)、[预检说明](preflight.md)与[pilot 设计](../integrations/pilot/design-fork-v1.md)。

## 授权不是布尔开关

`InspectionReport.execution_allowed` 与每个 `TargetImpact.execution_allowed` 永远为 false，JSON Schema 也写成 `const: false`。W3-B 不修改这两个模型。

`authorize_docker_execution(...)` 产生独立的 `docker-execution-authorization.v1`，要求：

1. Inspection 自摘要有效，且由当前完整 CounterGuard Python 源码生成；状态 ready、无 reason/unmapped，目标为 affected。
2. 配置原字节摘要、项目和目标映射与 Inspection 一致；W3-B 额外要求显式 `module`，且它必须由 `source_ref` 唯一推导（`src/pricing.py` → `src.pricing`）。
3. head 的 source/contract/dependency 全部有 Git object/content pin，当前物化文件逐字节一致。
4. 请求只能是 replay，并绑定 TargetRef、contract、Guard test、case IDs、timeout、输出目录和所有内容摘要。
5. 固定 `docker-policy.v1` 与本机精确 `sha256:` image ID 一起进入授权。

DockerExecutor 在启动前和退出后都重建这份授权。启动时把授权中的 source/contract/dependency 与 Guard test 逐字节复核后复制到一次性最小目录，容器只读挂载这个目录；项目配置、Git 元数据、仓库 `conftest.py`、pytest 配置和其他未声明文件不会进入容器。输入在执行期间变化时保留实际 RunRecord，并抛出完整性错误；授权或镜像缺失时不创建运行目录，也不调用 LocalTrustedExecutor。自摘要只用于一致性，不是签名；可信主体是宿主 CounterGuard 控制面，仓库代码只在容器内开始运行。

“谁能授权”是进程信任边界，而非用户身份系统：只有调用这组库 API 的可信宿主代码能构造授权，仓库文件和 Inspection 数据没有开关。当前没有 Registry 角色、签名或 OS 权限认证；这些属于 W3-C/W4，不能把本地函数调用描述成发布级权限控制。

## 构建与真实测试

基础 runner 的正式构建与锁定记录见 [runner receipt](results/w3b-formal-v1/runner-receipt.json)。validators 固定试点另使用 pytest 9.0.3 的专用镜像；已接受镜像 ID、依赖锁和四项原始攻击复验见 [试点 runner receipt](results/w3d-fork-v1/runner-receipt.json) 与 [Docker 攻击结果](results/w3d-fork-v1/attacks/acceptance.json)。下面的命令重建基础 runner；重建不会自动继承已接受的镜像 ID，必须生成新锁并复验：

```powershell
docker build --pull -t counterguard-runner:w3b -f containers/python-runner/Dockerfile .
$env:COUNTERGUARD_RUNNER_IMAGE_DIGEST = docker image inspect counterguard-runner:w3b --format '{{.Id}}'
uv run pytest -m docker tests/integration/test_docker_runner.py -q
```

执行时只使用已核验的 image ID，并传 `--pull=never`。tag 不是授权身份。基础 runner 的 Dockerfile、依赖锁、runner ID 与原四项攻击通过记录见 [正式 runner receipt](results/w3b-formal-v1/runner-receipt.json) 和 [Docker 测试输出](results/w3b-formal-v1/docker-tests.txt)。以后重建必须新锁新验收；不承诺未来源码构建逐位相同或上游身份签名。

若 Docker Desktop 4.71 在 Windows 报 Inference manager 的 `unix://C:\...\dockerInference` 路径错误，可先退出弹窗，再从正常桌面会话启动，并按官方命令关闭与本项目无关的 Model Runner：

```powershell
docker desktop disable model-runner
```

不要用恢复出厂设置作为第一步。该命令见 [Docker Desktop disable 文档](https://docs.docker.com/reference/cli/docker/desktop/disable/)；官方功能字段是 `enableInference`，不是控制 Gordon 的 `enableDockerAI`。本机持久化位置未取证确认；不能把官方字段当作本机历史 diff。

## 固定边界

容器没有网络或额外挂载，不传 Docker socket、宿主环境和凭据。根文件系统与最小 `/workspace` 只读，只有 64 MiB `/tmp` 可写。进程为 65532:65532，drop ALL capabilities、no-new-privileges，限制 1 CPU、256 MiB 内存/无额外 swap、64 PID、30 秒测试时间及分层日志大小。

entrypoint 自建 pytest 配置并关闭自动插件、conftest、cache provider 和 capture。W3-B v1 不安装项目，不支持仓库插件或 fixture 引导；需要这些机制的项目不进入首个试点。未来显式模式必须新版本化，并把配置、插件版本、fixture 代码和镜像一起绑定。

Docker 隔离保护宿主，不保证被测代码诚实报告语义。目标代码和 pytest 在同一 Python 进程中，恶意目标可能干扰框架或 JUnit；宿主能拒绝畸形、超限、超时和变化输入，却不能把这变成远程证明。Docker daemon、WSL2/内核、runner 镜像和宿主 CounterGuard 仍在可信计算基中。
