# MVP 0.1.0 安装与发布验收

> 本页保留 MVP 冻结时的历史说明；当前版本的安装与发布范围见 [0.5.0 Beta](beta-release.md)。不要把以下历史构建目录当作新版本输出目录。

本页说明 MVP 阶段如何从源码运行和构建 wheel。仓库采用 Apache-2.0，见 [LICENSE](../LICENSE)。MVP 阶段没有 GitHub 发行版下载；当前 Beta 交付见上方链接。`docs/results/` 只保留经过筛选的验收记录，不包含所有本机原始运行日志。

公开仓库没有发布 `v0.1.0` Git tag。本地保留的旧标签属于更名前的 EvidenceGuard 冻结记录，不是 CounterGuard 的发行标签。MVP 验收摘要见 [冻结版检查结果](results/mvp-freeze-v1/final-checks.json)；其中的历史提交号是在隐私清理前记录的，当前 GitHub `main` 已重写历史。

## 从源码运行

在源码分发或仓库根目录运行；Python 要求 >=3.12。当前已验证的平台和 Python 版本见 [冻结版检查结果](results/mvp-freeze-v1/final-checks.json)，未测平台不宣称兼容性已验证。

```powershell
uv sync --frozen
uv run counterguard version
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/freeze-demo
uv run counterguard demo --workspace artifacts/freeze-demo --verify-only
```

选择未使用过的 workspace。反复调用已完成目录只读验证；源码或依赖版本变化后用新目录。mvp.yaml 只支持 JSON 子集，见 [快速开始](quickstart.md)。

## 构建和干净安装

```powershell
uv build --out-dir dist/v0.1.0-freeze
uv venv .release-env
uv export --frozen --all-extras --no-dev --no-emit-project --output-file release-constraints.txt
uv pip install --python .release-env/Scripts/python.exe --constraint release-constraints.txt './dist/v0.1.0-freeze/counterguard-0.1.0-py3-none-any.whl[runner]'
.release-env/Scripts/counterguard.exe --help
.release-env/Scripts/python.exe -I -m counterguard version
```

`runner` 声明既有 pytest 执行器依赖，不引入新的第三方库。基础 wheel 的 pydantic/typer 足够加载 CLI/数据模型，却不足以运行 pytest；需要执行的安装选择 runner。dev 组继续供源码测试使用。约束文件保留本次锁定版本；不使用它重新解析依赖时，未来版本可能与已发布证据的环境 pin 不同。

基础/执行两种安装命令见 [快速开始](quickstart.md)。缺少 pytest 的执行请求会在创建运行目录前给出安装提示，退出 3；版本元数据和模块查找均检查，但这不证明任意损坏或被篡改的 pytest 安装可运行。

wheel 只装 Python 库与 console entry point；Demo 输入位于源码分发的 examples、benchmarks、experiments、tests/contract_tests。为了排除从当前 checkout 偷偷导入源码，安装验收要在 checkout 外运行，使用解释器的 `-I` 并检查 counterguard.__file__ 位于新环境 site-packages。指定 `--cwd` 到解压后的源码输入根目录，再用新输出目录运行：

```powershell
# 将以下两个绝对路径替换成实际安装环境与解压后的源码分发目录。
& 'D:/release-env/Scripts/python.exe' -I -m counterguard demo --cwd 'D:/release-source' --scenario examples/demo/mvp.yaml --workspace artifacts/wheel-demo --format json
& 'D:/release-env/Scripts/python.exe' -I -m counterguard demo --cwd 'D:/release-source' --workspace artifacts/wheel-demo --verify-only
```

安装 Demo 必须真的完成双向 Capture、最小 Guard 自检、两阶段学习与 Replay；单独 `--help` 成功不能替代这条验收。生成输入和原始日志的源码引用是相对路径；代码 pin 对应实际导入的 wheel 文件。

## 冻结前检查

```powershell
uv run pytest -q --tb=short --durations=20
uv run ruff check .
git diff --check
```

完整回归只在交付前运行；日常 `uv run pytest -m 'not slow' -q`。不修改既有 artifacts、样本、冻结协议/split/context。evaluation 留出结果按原代码只读复验并保留历史限制，不用当前源码重签。

公开结果按评测、冻结验收和仓库试点用途归档在 `docs/results/`。带本机绝对路径或个人操作标签的原始日志已从公开历史移除；没有把改写过的 JSON 继续当作原始收据。记录中的摘要是完整性校验值，不是数字签名。项目尚未完成多平台矩阵或外部供应链审计；validators 试点范围见 [W3-D 最终验收](results/w3d-fork-v1/final-acceptance.json)。
