# MVP 0.1.0 安装与发布验收

D14 交付本地源码分发、wheel、冻结评测汇总和新 Demo。正式执行记录见 [day14.md](progress/day14.md)。这不是 PyPI/GitHub 上传记录；许可证选择和公开发布另行处理。

本地 `v0.1.0` tag 冻结的是补齐 runner 缺失提示后的提交，验收见 [MVP 冻结补充记录](progress/mvp-freeze-v1.md)。最终包在 `dist/v0.1.0-freeze/`，D14 初版的 `dist/` 文件及报告保留原样；两个目录中的包版本均为尚未公开发布的 0.1.0，以目录和 SHA-256 区分。

## 从源码运行

在源码分发或仓库根目录运行；Python 要求 >=3.12。当前实测平台和 Python 版本以 D14 记录为准，未测平台不宣称兼容性已验证。

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

完整回归只在交付前运行；日常 `uv run pytest -m 'not slow' -q`。不修改既有 artifacts、样本、冻结协议/split/context。D9 留出结果按原代码只读复验并保留历史限制，不用当前源码重签。

初版记录保存在 docs/results/day14；tag 对应冻结版的 SHA-256、安装来源、Demo 和完整测试输出保存在 docs/results/mvp-freeze-v1。最终校验文件是本次本地交付记录，不是数字签名；没有做多平台矩阵、外部供应链审计或未知仓库执行验收。
