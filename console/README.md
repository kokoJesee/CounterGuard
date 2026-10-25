# CounterGuard 控制台

一个**不需要后端、不需要构建、离线可用**的静态控制台，用来查看 CounterGuard 的守卫、验证记录与适用范围。界面是纯静态实现，数据绑定的是项目真实产物：Registry、replay 报告、Docker verify 报告和冻结的 `scope_v1` 指标。

![总览（真实记录）](shots/01-overview-real.png)

## 打开

直接双击 `index.html`，或：

```powershell
start index.html
```

数据通过 `assets/data.js`（`window.__CG_DATA__`）注入，因此 `file://` 下也能正常加载，不存在跨域问题。

生成的数据含本机路径，**不入库**。新 clone 后先在仓库根目录跑一次导出：

```powershell
python console/tools/export_console_data.py --root .
```

没有数据时页面只显示提示，不会伪造记录。

## 五个页面

| 页面 | 内容 |
|---|---|
| 项目（总览） | KPI、守卫列表、最近一次验证的失败断言与来源缺陷 |
| 守卫库 | Registry 里的全部守卫，按契约 / 状态 / 最近结果筛选；点行看详情抽屉 |
| 验证记录 | 每条 replay / verify 的 `scope_decision`、`execution_outcome`、`final_verdict` |
| 适用范围 | 三态计数、initial / refined 规则、留出集四方法对比 |
| 告警 | 只收录「确认适用 + 执行失败」的违规；Shadow 阶段只记录不阻断 |

![验证记录](shots/04-records.png)

![适用范围](shots/05-scope.png)

交互：搜索、下拉筛选、分页、`Esc` 关闭抽屉、`/` 聚焦搜索。深链可直接定位：

```text
index.html#/guards/grd_discount_member_rate_regression_v2
index.html#/records/vfy_001
index.html?demo=1#/overview          # 直接进入演示数据
```

## 真实记录 vs 演示数据

顶栏右上角的按钮可以在两种数据之间切换（写在 `localStorage`，也可用 `?demo=1` 强制）。

- **真实记录**（默认）：全部来自本机项目，未做任何修饰。
  - `.counterguard/registry.json`、`.counterguard/entries/*.json` → 守卫
  - `artifacts/day13-smoke/report.json` → 6 条 replay
  - `artifacts/ci-demo/verify-1/verify/report.json` → 1 条 Docker verify（含失败断言与阻断标记）
  - `docs/results/scope-v1/evaluation/metrics.json` → 四方法指标
  - `artifacts/experiments/scope-v1/fitted/{initial,refined}/*.json` → 学到的适用条件
  - `benchmarks/splits/scope_v1.json` 与样本文件 → 9 训练 / 6 留出
- **演示数据**：为了展示 128 条守卫、2,431 次验证这类界面密度而**合成**的数据，每行都标在演示模式下，页面顶部有固定横幅、页脚也有标记。**它不能作为项目事实引用。**

真实记录当前只有 2 条守卫、7 条验证、3 条违规——控制台显示的就是这个量级，不会把稀疏数据美化成大样本。

## 重新导出

项目有新产物后，在仓库根目录：

```powershell
python console/tools/export_console_data.py --root .
# 或显式指定项目根
python console/tools/export_console_data.py --root <path-to-repo>
```

会同时写出：

- `assets/data.js` —— 页面实际加载的数据
- `data/console-data.json` —— 同一份 JSON，便于其他脚本消费

脚本只读项目文件，不写项目目录。缺少某个产物时会退化为空集，不会编造记录。

## 目录

```text
index.html                  页面骨架、图标精灵、侧栏插画
assets/console.css          设计令牌与全部组件样式
assets/console.js           路由、筛选、分页、抽屉、迷你图
assets/data.js              生成的数据（勿手改，不入库）
data/console-data.json      同一份数据，供程序读取（不入库）
tools/export_console_data.py  导出脚本（Python 3.10+，仅标准库）
tools/smoke_console.mjs       交互冒烟测试（可选，需 Node 18+ 与 Chrome）
shots/                      真实记录模式的界面截图
```

## 交互冒烟测试（可选）

```powershell
# 1) 用调试端口启动 Chrome
# 1) 用调试端口启动 Chrome（chrome.exe 在 PATH 中）
chrome --headless=new --remote-debugging-port=9333 --user-data-dir="$env:TEMP\cg-cdp" about:blank

# 2) 跑检查（在 console/ 目录下）
node tools/smoke_console.mjs
```

覆盖：列表渲染、行点击抽屉、Esc 关闭、搜索过滤、记录筛选、范围页数据、告警抽屉、真实/演示切换。当前 16/16 通过。

## 在仓库内的位置

控制台以静态文件形式随仓库分发，不进入 Python 包——`pyproject.toml` 的 wheel 只包含 `src/counterguard`，这里只有 HTML/CSS/JS 和两支独立工具。
`assets/data.js` 与 `data/` 由 `console/.gitignore` 排除，避免把本机路径和一次性快照写进历史。

如果要把它变成产品入口，建议单独开一个阶段：新增 `counterguard console --export <dir>` 复用现有字段映射；
用 `python -m http.server` 或 Typer 挂只读静态服务以避免 `file://`；再给导出器补单元测试并纳入验收记录。

## 已知边界

- 这是**只读快照**：页面不会自己刷新，也没有后端；重新导出才会更新。
- 没有登录、权限、远程 Registry；顶栏的团队/铃铛是界面元素，不承诺真实通知能力。
- 演示数据是合成的，页面已明确标注；引用数字时请使用真实记录模式。
- 摘要只用于一致性检查，不作为签名或身份认证——和项目本身的表述保持一致。
