# Docker Desktop 全局设置改动记录

记录日期：2026-10-16。范围是用户机器的 Docker Desktop，不属于 EvidenceGuard 项目配置。本轮仅只读核查，没有再次更改这些设置。

| 操作 | 持久设置 / 实际观察 | 还原方式 |
|---|---|---|
| 10-15 为绕过 Inference manager 启动错误执行 `docker desktop disable model-runner` | 官方功能对应 `enableInference=false`。但当时没有保存命令前后完整设置 diff；10-16 的 `%APPDATA%\Docker\settings-store.json` **没有显式 Inference 相关键**。因此该版本 CLI 究竟把状态持久化到哪个内部文件/键，**不确定**；不能把官方逻辑字段冒充本机取证结果。没有证据显示修改了 TCP/GPU/CORS 子选项 | 需要恢复 Model Runner 时，在正常桌面会话执行 `docker desktop enable model-runner`，或在 Docker Desktop 设置中打开 Model Runner。使用前按本机 `--help` 核对；可能再次触发原启动错误，项目不自动恢复它 |
| 10-15 曾误把 Gordon 关闭，随后恢复 | 实际编辑 `%APPDATA%\Docker\settings-store.json` 的 **`EnableDockerAI`**：true → false → true。10-16 只读确认它为 true。官方管理字段拼写为 `enableDockerAI`，对应 Gordon，与 Model Runner 是不同设置。最终值已恢复到原值 | 当前无需还原。若用户希望关闭，在 Docker Desktop 设置关闭 Gordon。退出 Desktop 后编辑设置时须先备份、只修改实际存在的大小写键；不要复制整份旧配置覆盖其他设置 |
| 用户于 10-16 配置 registry-mirrors | `docker info` 实测为 `https://docker.1ms.run/` 与 `https://docker.m.daocloud.io/`。该改动由用户完成；本轮未修改 daemon.json | 在 Docker Desktop → Settings → Docker Engine 中移除这两条 `registry-mirrors` 后 Apply & restart。镜像源是全局网络/供应链选择，项目不自动改回 |

核查命令（只显示相关键，不公开整份可能含隐私的配置）：

```powershell
$settings = Get-Content -Raw "$env:APPDATA\Docker\settings-store.json" | ConvertFrom-Json
$settings.PSObject.Properties | Where-Object { $_.Name -match 'Inference|DockerAI' } | Select-Object Name,Value
docker info --format '{{json .RegistryConfig.Mirrors}}'
docker desktop status
docker desktop enable model-runner --help
```

官方依据：[disable model-runner](https://docs.docker.com/reference/cli/docker/desktop/disable/)、[Desktop 管理设置字段](https://docs.docker.com/desktop/enterprise/hardened-desktop/settings-management/settings-reference/)。这些文档说明功能语义；它们不证明本机历史文件差异。若要精确关闭 Q3 中的内部持久化位置疑问，需要在用户选择再次切换功能时，比较该版本 Desktop 的设置/API 状态并保存脱敏 diff；本次没有为取证主动切换全局功能。
