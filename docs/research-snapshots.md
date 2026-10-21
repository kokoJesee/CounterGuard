# 独立研究快照：工具自有 fixture

`source-only-python-snapshot.v1` 使用完整 Git 快照清单和独立执行审核，接受获审包源码中的正常 Python 动态操作。它与原有词法闭包 profile 分开：旧 profile 的 `unknown` 不会被一个理由字段清除，旧契约、Scope、Registry 和 `verify` 不接受这里的新类型。

来源链当前执行用途仅为 **tool_owned_fixture**；[独立比较子命名空间](snapshot-comparisons.md)仅允许 **tool_owned_snapshot_comparison_only**。二者均限工具自有 fixture，没有批准 TTE、webcolors 或其他外部仓库执行，没有生成真实研究标签，也没有提供生产 Shadow/Active 的入口。工具自有 fixture 跑通不能计入跨项目场景数。

## 两种快照边界

| 边界 | 内容 | 作用 |
|---|---|---|
| 完整提交清单 | B/F/H 全部文件的路径、Git object ID、内容摘要和大小，包括测试、媒体和配置 | 重建来源和容量；不遗漏媒体冒充全树 |
| 容器输入 | 声明的顶层普通 Python 包内全部文件、H 中的契约、工具生成的测试 | 执行完整包快照，不再声称它是词法可达闭包 |

包根支持 `.` / `src`，要求顶层包存在 `__init__.py`。原测试、根配置、根 conftest、安装脚本和包外媒体不进入容器挂载；它们仍在完整提交清单中。包内 conftest、启动定制文件、原生二进制和 Python 字节码拒绝，不通过删除这些文件换取准入。

PEP 621 必须给出静态零运行时依赖、可检查的 Python 版本要求；不执行 `setup.py`，不安装依赖。包内显式第三方导入拒绝。静态扫描不证明所有动态导入可用、无副作用或语义安全；这些是快照审核和 Docker 隔离的责任。运行时导入失败仍是执行问题，不是缺陷证据。

`__future__` 是 Python 标准库的编译指令模块，不是需安装的项目依赖；本 profile 接受它，也禁止目标包遮蔽它。该修正不扩大旧预检、插件或依赖安装范围。

## 容量和 Git 约束

| 项目 | 新 profile 上限 |
|---|---:|
| 单 blob | 8 MiB |
| 完整提交物化大小 | 128 MiB；同一 blob 的多个路径重复计数 |
| 文件数 | 2048 |
| 单个 Python AST 输入 | 1 MiB / 50,000 节点 |
| 全树读取预算 | 30 秒，包含首次 Git 预检 |
| 每次 Git 子进程 | 沿用 5 秒上限 |

先读全部 blob 大小，再按至多 8 MiB / 64 个对象分批读取。逐对象核对 Git SHA-1 framing、累计物化大小和最后期限；保留的完整树最多 128 MiB。这是有界分批读取，不是恒定内存的流式 AST 分析。

沿用隔离 Git 元数据、禁止网络/替换对象/外部对象库、对象完整性、链接/submodule 和仓库变化检查。原对象库 128 MiB 预检等限制仍存在，不能由新树容量绕过；大历史仓库仍可能拒绝或超时。没有用外部大仓库实测证明兼容性。

`SnapshotBudget` 只允许收紧这些容量，不允许扩大。旧读取器的单 blob 1 MiB / 全树 8 MiB 不变。

## 原测试的有限投影

新 `snapshot-test-projection.v1` 复用原断言语法，并支持：

```python
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(-1, id="negative"),
        pytest.param(256, id="too large"),
    ],
)
def test_invalid(value):
    with pytest.raises(ValueError, match="outside range"):
        check(value)
```

位置参数必须是既有字面量语法可表示的数据；`id` 必须是字面量字符串。marks、展开、动态 ID、fixture、动态值和控制流仍拒绝。异常类型沿用白名单，`match` 沿用字面量匹配子集，不加入复杂正则。

必须完整表示选定原函数中的所有断言和参数；不接受 partial 后删 case。契约保持断言/参数的源码顺序，原 ID、整个测试摘要和投影摘要保留来源身份。相同输入的不同参数行有不同 case ID。

运行结果沿用 `RunRecord` 的 ID 排序；核对时比较完整规范 case 集，再按原测试顺序保留实际失败 case。不会因为两个模块排序不同而改变原参数或把缺失 case 当成通过。

## B/F/H 与两类审核

F 必须以 B 为唯一直接父提交；H 必须以 F 为唯一直接父提交，并只新增契约，以及可选的显式工具配置 `counterguard.yaml`。配置按完整字节绑定，但不作为可执行配置加载。绑定重建 H 原始 blob、F 原测试投影、全部 case、完整清单和每个角色的完整包输入。不能由工作区文件代替提交内容。

`tool_additions` 与 `upstream_refs` 区分工具文件和上游文件。H 必须由相应所有者流程创建；这里的 prepare/bind 不会代造 owner 提交、补签或放宽契约来自 H。

两种审核分别记录：

- `execution` 绑定完整 B/F/H、入口、契约、容量、超时、精确 runner 收据、Docker policy、实现摘要和用途。
- `semantics` 使用另一条记录表达语义审核。执行审核不自动批准 oracle 独立性、适用性、合规性或标签；当前模块没有训练/标签接口。

调用方必须在可变记录之外独立保存审核摘要，并在 capture/compile/replay/audit 时传入。替换记录并重算自身摘要不能替换这个信任锚。记录有真实 UTC 时间，不伪造跨运行相同的摘要。

fixture 标记只是一项可信本机操作者声明，不是签名或仓库所有权证明。它不能把外部项目转换为已获批 fixture。能控制主机、验证器和可信锚的攻击者不在这里的保证内；外部用途需要独立版本及授权。

## 执行和复核

```powershell
counterguard research-snapshot --help
counterguard research-snapshot prepare --help
counterguard research-snapshot bind --help
counterguard research-snapshot review --help
counterguard research-snapshot capture --help
counterguard research-snapshot compile --help
counterguard research-snapshot replay --help
counterguard research-snapshot audit --help
```

prepare 写只读提案；bind 写 `execution_allowed=false` 的来源绑定。review 不启动 Docker。执行命令还要求明确审核记录及 `--review-digest`，输出目录必须全新、位于工作区内且在目标仓库之外。

capture 仅在 B 真测试失败、F 通过、两侧完整执行全部原 case 时标记 reproduced。compile 恰好保留实际失败 case，并在 B/F 再做双向自检。replay 只支持已审核 B/F 的精确快照，不声称学习了其他目标的适用性。audit 从 Git、独立锚、规范测试、授权、原始日志/JUnit 重建结果，不启动容器。

沿用已审核镜像的精确 image ID、封闭 Docker 参数、无网络、非 root、只读挂载/rootfs、能力清空、进程/内存/输出/时间限制。没有本地回退；原测试、pytest 插件和 conftest 不自动加载。执行前后重新核对来源和输入；晚到变化保留实际 Run，失败时保留失败回执，不发布成功 Guard。

恶意候选干扰容器内测试或 JUnit 的问题仍未解决。这里的原始日志重建是可追溯性保证，不是对任意恶意 Python 的语义证明。

## 可重复的自有 fixture 验收

```powershell
uv run pytest tests/unit/test_snapshot_projection.py tests/unit/test_snapshot_repository.py tests/unit/test_snapshot_admission.py -q
uv run pytest tests/integration/test_snapshot_admission.py -q
counterguard runner list
# 由操作者把上一条已核验的 root-pytest8 精确 ID 设入环境变量：
$env:COUNTERGUARD_RUNNER_IMAGE_DIGEST = '<root-pytest8 的精确 sha256 ID>'
uv run pytest tests/integration/test_snapshot_docker.py -q
uv run python scripts/export_snapshot_schemas.py --check
```

两个 integration 文件均标 `slow`，真实 Docker 文件另标 `docker`。未设置镜像变量时 Docker 专项 skip，不能将它记为已测。专项只创建工具自己的 Git 历史，不下载或运行外部项目。

新增源码改变全包 implementation digest。需要当前有效结论的链必须使用新 ID/目录重新物化；历史结果不改字节、不重签为当前有效。Schema 位于 `schemas/research-snapshot-v1/`，不重写旧 Schema。
