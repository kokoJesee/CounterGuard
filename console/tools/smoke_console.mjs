/**
 * 控制台交互冒烟测试（可选开发工具）
 *
 * 前置：先用调试端口启动 Chrome（chrome.exe 在 PATH 中），例如
 *   chrome --headless=new --remote-debugging-port=9333 --user-data-dir=%TEMP%\cg-cdp about:blank
 * 运行：
 *   node tools/smoke_console.mjs [http://127.0.0.1:9333] [fileUrl]
 */
const base = process.argv[2] || 'http://127.0.0.1:9333';
const pageUrl = process.argv[3] || new URL('../index.html', import.meta.url).href;

const target = await (await fetch(`${base}/json/new?${encodeURIComponent(pageUrl)}`, { method: 'PUT' })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
const errors = [];
let seq = 0;

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });

ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message));
    else resolve(msg.result);
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
  }
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    errors.push(msg.params.args.map((arg) => arg.value ?? arg.description).join(' '));
  }
});

await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true });
  ws.addEventListener('error', reject, { once: true });
});

await send('Runtime.enable');
await send('Page.enable');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function waitFor(expression, timeout = 4000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(expression)) return true;
    await sleep(60);
  }
  return false;
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok: Boolean(ok), detail });
}

await sleep(1200);
check('页面渲染出守卫表', await waitFor("document.querySelectorAll('#list-region tbody tr[data-guard]').length === 2"));
check('KPI 显示真实守卫数 2', (await evaluate("document.querySelector('.kpi .kpi-value').textContent.trim()")).startsWith('2'));

await evaluate("document.querySelector('tr[data-guard]').click()");
check('点击行打开抽屉', await waitFor("document.getElementById('drawer-root').classList.contains('open')"));
check('抽屉标题是守卫名', (await evaluate("document.querySelector('.drawer-title')?.textContent || ''")).includes('limit=0'));
await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
await sleep(400);
check('Esc 关闭抽屉', !(await evaluate("document.getElementById('drawer-root').classList.contains('open')")));

await evaluate(`(() => {
  const input = document.querySelector('[data-search-input]');
  input.value = 'limit';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()`);
await sleep(200);
check('搜索过滤剩 1 条', (await evaluate("document.querySelectorAll('#list-region tbody tr[data-guard]').length")) === 1);
await evaluate(`(() => {
  const input = document.querySelector('[data-search-input]');
  input.value = '';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()`);
await sleep(150);

await evaluate("location.hash = '#/records'");
await waitFor("document.querySelectorAll('#list-region tbody tr[data-record]').length > 0");
check('验证记录页 7 条', (await evaluate("document.querySelectorAll('#list-region tbody tr[data-record]').length")) === 7);
await evaluate("document.querySelector('[data-chip=kind][data-value=verify]').click()");
await sleep(200);
check('按 verify 过滤剩 1 条', (await evaluate("document.querySelectorAll('#list-region tbody tr[data-record]').length")) === 1);
check('汇总卡显示确认违规 3', (await evaluate("document.querySelectorAll('.summary-value')[3].textContent")).trim().startsWith('3'));

await evaluate("location.hash = '#/scope'");
await waitFor("document.body.innerText.includes('搜索空间')");
const scopeText = await evaluate('document.body.innerText');
check('适用范围页含 92 / 175 候选数', scopeText.includes('92 / 175'));
check('适用范围页含四方法', scopeText.includes('学习 · refined'));

await evaluate("location.hash = '#/alerts'");
await waitFor("document.querySelectorAll('.alert-card').length === 3");
check('告警页 3 张卡', (await evaluate("document.querySelectorAll('.alert-card').length")) === 3);
await evaluate("document.querySelector('[data-record-open]').click()");
check('告警可打开证据抽屉', await waitFor("document.getElementById('drawer-root').classList.contains('open')"));

await evaluate("location.hash = '#/overview'");
await evaluate("document.getElementById('source-toggle').click()");
await waitFor("document.querySelector('.kpi .kpi-value').textContent.includes('128')");
check('切换到演示数据 128 守卫', (await evaluate("document.querySelector('.kpi .kpi-value').textContent")).includes('128'));
check('演示模式有横幅', await evaluate("Boolean(document.querySelector('.demo-banner'))"));
await evaluate("document.getElementById('source-toggle').click()");
await sleep(300);
check('切回真实记录', (await evaluate("document.querySelector('.kpi .kpi-value').textContent")).trim().startsWith('2'));

const failed = checks.filter((item) => !item.ok);
for (const item of checks) console.log(`${item.ok ? 'PASS' : 'FAIL'}  ${item.name}`);
console.log(`\n${checks.length - failed.length}/${checks.length} 通过`);
if (errors.length) {
  console.log('\nJS 错误：');
  for (const error of errors) console.log(' -', error.split('\n')[0]);
}
await send('Page.close').catch(() => {});
ws.close();
process.exit(failed.length || errors.length ? 1 : 0);
