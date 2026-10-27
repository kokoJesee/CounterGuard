/* ===========================================================
   CounterGuard 控制台 · 应用逻辑
   数据来自 assets/data.js（由 tools/export_console_data.py 生成）
   =========================================================== */
(() => {
  'use strict';

  const DATA = window.__CG_DATA__;
  const view = document.getElementById('view');
  const drawerRoot = document.getElementById('drawer-root');
  if (!DATA) {
    view.innerHTML = '<div class="empty"><h3>缺少数据文件</h3><p>请先运行 python tools/export_console_data.py 生成 assets/data.js。</p></div>';
    return;
  }

  const PAGE_SIZE = { overview: 5, guards: 8, records: 8, alerts: 6 };

  const state = {
    source: localStorage.getItem('cg.source') === 'demo' ? 'demo' : 'real',
    route: 'overview',
    search: '',
    family: 'all',
    gstate: 'all',
    gresult: 'all',
    kind: 'all',
    verdict: 'all',
    overviewPage: 1,
    guardsPage: 1,
    recordsPage: 1,
    alertsPage: 1,
  };

  /* ------------------------------------------------------------ 基础工具 */
  const ds = () => DATA[state.source] || DATA.real;

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  const num = (value) => Number(value ?? 0).toLocaleString('zh-CN');
  const pct = (value) => (value == null ? '—' : `${Math.round(value * 1000) / 10}%`);
  const icon = (name, cls = '') => `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  function relTime(value) {
    if (!value) return '—';
    const diff = Date.now() - new Date(value).getTime();
    const minutes = Math.round(diff / 60000);
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes} 分钟前`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} 小时前`;
    const days = Math.round(hours / 24);
    if (days < 8) return `${days} 天前`;
    return new Date(value).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
  }

  function fmtDateTime(value) {
    if (!value) return '—';
    return new Date(value).toLocaleString('zh-CN', { hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  }

  function fmtDuration(ms) {
    if (ms == null) return '—';
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
  }

  const short = (digest) => (digest ? String(digest).replace('sha256:', '').slice(0, 12) : '—');

  const VERDICT = {
    pass: { label: '通过', cls: 'ok', icon: 'check-circle' },
    violation: { label: '违规', cls: 'bad', icon: 'alert' },
    skipped: { label: '跳过', cls: 'skip', icon: 'slash' },
    inconclusive: { label: '无法判断', cls: 'warn', icon: 'help' },
    not_run: { label: '未执行', cls: 'skip', icon: 'slash' },
    stale: { label: '已过期', cls: 'warn', icon: 'clock' },
  };
  const DECISION = {
    applicable: { label: '适用', cls: 'ok', icon: 'check-circle' },
    inapplicable: { label: '不适用', cls: 'skip', icon: 'slash' },
    unknown: { label: '信息不足', cls: 'warn', icon: 'help' },
  };
  const EXECUTION = {
    pass: { label: '通过', cls: 'ok' },
    fail: { label: '失败', cls: 'bad' },
    not_run: { label: '未执行', cls: 'skip' },
    error: { label: '执行异常', cls: 'warn' },
    timeout: { label: '超时', cls: 'warn' },
  };
  const GUARD_STATE = {
    candidate: { label: 'Candidate', cls: 'warn' },
    shadow: { label: 'Shadow', cls: 'plain' },
    active: { label: 'Active', cls: 'ok' },
    retired: { label: 'Retired', cls: 'plain' },
  };
  const FAMILY_LABEL = {
    membership_discount: '会员折扣',
    input_limit: '输入上限',
    price_rounding: '金额舍入',
    date_window: '日期区间',
    pagination_bounds: '分页边界',
    retry_budget: '重试预算',
  };
  const INTERFACE_LABEL = {
    final_price: '最终价格接口',
    query_parameter: '查询参数接口',
    round_amount: '金额舍入接口',
    date_range: '日期区间接口',
    page_parameter: '分页参数接口',
    retry_count: '重试计数接口',
  };
  const familyName = (value) => FAMILY_LABEL[value] || value || '—';
  const interfaceName = (value) => INTERFACE_LABEL[value] || value || '—';

  /* ------------------------------------------------------------ 迷你图 */
  let gradientId = 0;
  function sparkline(values, tone) {
    const points = (values && values.length ? values : [0, 0]).slice();
    const w = 100;
    const h = 40;
    const pad = 2;
    const max = Math.max(...points);
    const min = Math.min(...points);
    const span = Math.max(1, max - min);
    const coords = points.map((value, index) => {
      const x = pad + (index * (w - pad * 2)) / Math.max(1, points.length - 1);
      const y = h - pad - ((value - min) / span) * (h - pad * 2);
      return [Number(x.toFixed(2)), Number(y.toFixed(2))];
    });
    let line = `M ${coords[0][0]} ${coords[0][1]}`;
    for (let i = 1; i < coords.length; i += 1) line += ` L ${coords[i][0]} ${coords[i][1]}`;
    const area = `${line} L ${coords[coords.length - 1][0]} ${h} L ${coords[0][0]} ${h} Z`;
    const color = tone === 'down' ? '#e0484d' : tone === 'neutral' ? '#8aa79b' : '#12a476';
    const id = `sp${(gradientId += 1)}`;
    return `<svg viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${color}" stop-opacity=".26"/>
        <stop offset="1" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#${id})"/>
      <path d="${line}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    </svg>`;
  }

  /* ------------------------------------------------------------ 共享组件 */
  function statusOf(verdict, when) {
    const meta = VERDICT[verdict] || VERDICT.not_run;
    return `<span class="status ${meta.cls}">${icon(meta.icon)}${meta.label}${when ? `<span class="when">${relTime(when)}</span>` : ''}</span>`;
  }

  function guardStateTag(value) {
    const meta = GUARD_STATE[value] || { label: value || '—', cls: 'plain' };
    return `<span class="tag ${meta.cls}">${esc(meta.label)}</span>`;
  }

  function pager(total, page, size, key) {
    const pages = Math.max(1, Math.ceil(total / size));
    const current = Math.min(Math.max(1, page), pages);
    const items = [];
    for (let p = 1; p <= pages; p += 1) {
      if (p === 1 || p === pages || Math.abs(p - current) <= 1) items.push(p);
      else if (items[items.length - 1] !== '…') items.push('…');
    }
    return `<div class="pager" data-key="${key}">
      <span class="total">共 ${num(total)} 条</span>
      <div class="pages">
        <button type="button" data-page="${current - 1}" ${current <= 1 ? 'disabled' : ''} aria-label="上一页">‹</button>
        ${items
          .map((item) =>
            item === '…'
              ? '<span class="ellipsis">…</span>'
              : `<button type="button" data-page="${item}" class="${item === current ? 'active' : ''}">${item}</button>`
          )
          .join('')}
        <button type="button" data-page="${current + 1}" ${current >= pages ? 'disabled' : ''} aria-label="下一页">›</button>
      </div>
    </div>`;
  }

  function emptyRow(colspan, title, text) {
    return `<tr><td colspan="${colspan}"><div class="empty">${icon('search')}<h3>${esc(title)}</h3><p>${esc(text)}</p></div></td></tr>`;
  }

  /* ------------------------------------------------------------ KPI */
  const KPI_META = {
    guards: { label: '守卫总数', icon: 'shield' },
    verifications: { label: '验证记录', icon: 'play' },
    violations: { label: '发现回归', icon: 'alert' },
    applicability: { label: '适用性判定', icon: 'chart' },
  };

  function renderKpis(kpis) {
    return `<section class="kpi-grid">${Object.entries(KPI_META)
      .map(([key, meta]) => {
        const item = kpis[key] || { value: 0 };
        const tone = item.tone || 'up';
        const arrow = tone === 'neutral' ? '·' : '↑';
        return `<article class="kpi ${tone}">
          <div class="kpi-icon">${icon(meta.icon)}</div>
          <div class="kpi-body">
            <div class="kpi-label">${meta.label}</div>
            <div class="kpi-value">${num(item.value)}${item.unit ? `<span class="unit">${item.unit}</span>` : ''}</div>
            <div class="kpi-delta"><span class="arrow">${arrow}</span><span>${esc(item.delta || '')}</span></div>
          </div>
          <div class="kpi-spark">${sparkline(item.spark, tone)}</div>
        </article>`;
      })
      .join('')}</section>`;
  }

  /* ------------------------------------------------------------ 过滤 */
  function guardList() {
    const query = state.search.trim().toLowerCase();
    return ds()
      .guards.slice()
      .filter((guard) => {
        if (state.family !== 'all' && guard.family !== state.family) return false;
        if (state.gstate !== 'all' && guard.state !== state.gstate) return false;
        if (state.gresult !== 'all' && (guard.last?.verdict || 'not_run') !== state.gresult) return false;
        if (!query) return true;
        const haystack = [guard.name, guard.subtitle, guard.source_defect, guard.source_defect_id, guard.contract, guard.id, guard.family]
          .join(' ')
          .toLowerCase();
        return haystack.includes(query);
      })
      .sort((a, b) => String(b.last?.at || '').localeCompare(String(a.last?.at || '')));
  }

  function recordList() {
    const query = state.search.trim().toLowerCase();
    return ds()
      .verifications.slice()
      .filter((record) => {
        if (state.kind !== 'all' && record.kind !== state.kind) return false;
        if (state.verdict !== 'all' && record.final_verdict !== state.verdict) return false;
        if (!query) return true;
        const haystack = [record.guard_name, record.guard_id, record.target, record.id, record.run_id, record.final_verdict]
          .join(' ')
          .toLowerCase();
        return haystack.includes(query);
      })
      .sort((a, b) => String(b.at).localeCompare(String(a.at)));
  }

  function alertList() {
    const query = state.search.trim().toLowerCase();
    return ds()
      .alerts.slice()
      .filter((alert) => {
        if (!query) return true;
        return [alert.guard_name, alert.guard_id, alert.target, alert.detail, alert.commit].join(' ').toLowerCase().includes(query);
      })
      .sort((a, b) => String(b.at).localeCompare(String(a.at)));
  }

  /* ------------------------------------------------------------ 守卫表 */
  function guardRow(guard) {
    const targetCount = guard.target_count || guard.case_count || 0;
    const unit = state.source === 'demo' ? '个项目' : '个适用样本';
    return `<tr data-guard="${esc(guard.id)}" tabindex="0">
      <td>
        <div class="cell-name">
          <span class="tile">${icon('file')}</span>
          <div>
            <div class="name-text">${esc(guard.name)}</div>
            <div class="name-sub">${esc(guard.subtitle || guard.contract)}</div>
          </div>
        </div>
      </td>
      <td>
        <div class="cell-sub">${esc(guard.source_defect)}</div>
        <div class="cell-ref">${esc(guard.source_defect_id)}</div>
      </td>
      <td>
        <div class="cell-sub">${esc(interfaceName(guard.interface_kind))}</div>
        <div class="cell-meta">${targetCount ? `${num(targetCount)} ${unit}` : '—'}</div>
      </td>
      <td>${statusOf(guard.last?.verdict || 'not_run', guard.last?.at)}</td>
      <td><span class="kebab" role="button" tabindex="-1" aria-label="查看详情">${icon('more')}</span></td>
    </tr>`;
  }

  function guardTable(rows) {
    if (!rows.length) {
      return `<div class="table-wrap"><table class="data"><tbody>${emptyRow(5, '没有匹配的守卫', '试试清空筛选条件，或换一个关键词。')}</tbody></table></div>`;
    }
    return `<div class="table-wrap">
      <table class="data">
        <thead><tr>
          <th style="width:34%">守卫名称</th>
          <th style="width:27%">来源缺陷</th>
          <th style="width:17%">适用对象</th>
          <th style="width:15%">最近结果</th>
          <th style="width:7%"></th>
        </tr></thead>
        <tbody>${rows.map(guardRow).join('')}</tbody>
      </table>
    </div>`;
  }

  function overviewListMarkup() {
    const rows = guardList();
    const page = Math.min(state.overviewPage, Math.max(1, Math.ceil(rows.length / PAGE_SIZE.overview)));
    const slice = rows.slice((page - 1) * PAGE_SIZE.overview, page * PAGE_SIZE.overview);
    return guardTable(slice) + pager(rows.length, page, PAGE_SIZE.overview, 'overview');
  }

  function guardsListMarkup() {
    const rows = guardList();
    const page = Math.min(state.guardsPage, Math.max(1, Math.ceil(rows.length / PAGE_SIZE.guards)));
    const slice = rows.slice((page - 1) * PAGE_SIZE.guards, page * PAGE_SIZE.guards);
    if (!slice.length) {
      return `<div class="table-wrap"><table class="data"><tbody>${emptyRow(7, '没有匹配的守卫', '试试清空筛选条件，或换一个关键词。')}</tbody></table></div>`;
    }
    const body = slice
      .map(
        (guard) => `<tr data-guard="${esc(guard.id)}" tabindex="0">
          <td>
            <div class="cell-name">
              <span class="tile">${icon('file')}</span>
              <div>
                <div class="name-text">${esc(guard.name)}</div>
                <div class="name-sub">${esc(guard.id)}</div>
              </div>
            </div>
          </td>
          <td>
            <div class="cell-sub">${esc(familyName(guard.family))} · ${esc(interfaceName(guard.interface_kind))}</div>
            <div class="cell-meta">${esc(guard.contract_version || '—')} · ${guard.case_count} 条 case</div>
          </td>
          <td><div class="cell-ref" style="max-width:280px;white-space:normal">${esc(guard.scope_refined || guard.scope_initial || '—')}</div></td>
          <td><span class="tag plain mono">${guard.case_count}</span></td>
          <td>${statusOf(guard.last?.verdict || 'not_run', guard.last?.at)}</td>
          <td>${guardStateTag(guard.state)}</td>
          <td><span class="kebab" role="button" tabindex="-1" aria-label="查看详情">${icon('more')}</span></td>
        </tr>`
      )
      .join('');
    return `<div class="table-wrap">
      <table class="data">
        <thead><tr>
          <th style="width:25%">守卫</th>
          <th style="width:20%">契约与接口</th>
          <th style="width:29%">适用条件（refined）</th>
          <th style="width:8%">Case</th>
          <th style="width:11%">最近结果</th>
          <th style="width:7%">状态</th>
          <th style="width:4%"></th>
        </tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>` + pager(rows.length, page, PAGE_SIZE.guards, 'guards');
  }

  /* ------------------------------------------------------------ 验证记录表 */
  function recordRow(record) {
    const decision = DECISION[record.scope_decision] || DECISION.unknown;
    const execution = EXECUTION[record.execution_outcome] || EXECUTION.not_run;
    const verdict = VERDICT[record.final_verdict] || VERDICT.inconclusive;
    return `<tr data-record="${esc(record.id)}" tabindex="0">
      <td><div class="cell-sub">${relTime(record.at)}</div><div class="cell-meta">${esc(record.kind === 'verify' ? 'verify' : 'replay')}</div></td>
      <td>
        <div class="cell-sub">${esc(record.guard_name)}</div>
        <div class="cell-ref">${esc(record.guard_id)}</div>
      </td>
      <td>
        <div class="cell-sub">${esc(record.target)}</div>
        <div class="cell-meta">${esc(record.run_id || '')}</div>
      </td>
      <td><span class="tag ${decision.cls}">${icon(decision.icon)}${decision.label}</span></td>
      <td><span class="status ${execution.cls}">${execution.label}</span></td>
      <td><span class="record-verdict ${verdict.cls}">${icon(verdict.icon)}${verdict.label}</span></td>
      <td><div class="cell-ref">${fmtDuration(record.duration_ms)}</div></td>
      <td><span class="kebab" role="button" tabindex="-1" aria-label="查看记录">${icon('more')}</span></td>
    </tr>`;
  }

  function recordsListMarkup() {
    const rows = recordList();
    const page = Math.min(state.recordsPage, Math.max(1, Math.ceil(rows.length / PAGE_SIZE.records)));
    const slice = rows.slice((page - 1) * PAGE_SIZE.records, page * PAGE_SIZE.records);
    if (!slice.length) {
      return `<div class="table-wrap"><table class="data"><tbody>${emptyRow(8, '没有匹配的验证记录', '换一个范围或清空搜索词。')}</tbody></table></div>`;
    }
    return `<div class="table-wrap">
      <table class="data">
        <thead><tr>
          <th style="width:11%">时间</th>
          <th style="width:22%">守卫</th>
          <th style="width:23%">样本 / 目标</th>
          <th style="width:12%">适用范围</th>
          <th style="width:10%">执行</th>
          <th style="width:11%">结论</th>
          <th style="width:8%">耗时</th>
          <th style="width:3%"></th>
        </tr></thead>
        <tbody>${slice.map(recordRow).join('')}</tbody>
      </table>
    </div>` + pager(rows.length, page, PAGE_SIZE.records, 'records');
  }

  /* ------------------------------------------------------------ 警告列表 */
  function alertListMarkup() {
    const rows = alertList();
    const page = Math.min(state.alertsPage, Math.max(1, Math.ceil(rows.length / PAGE_SIZE.alerts)));
    const slice = rows.slice((page - 1) * PAGE_SIZE.alerts, page * PAGE_SIZE.alerts);
    if (!slice.length) {
      return `<div class="empty">${icon('check-circle')}<h3>没有匹配的警告</h3><p>只有「确认适用 + 执行失败」的守卫才会出现在这里；跳过与信息不足不算警告。</p></div>`;
    }
    const cards = slice
      .map((alert) => {
        const isBlocking = alert.blocking;
        return `<article class="alert-card">
          <span class="tile red">${icon('alert')}</span>
          <div class="alert-main">
            <div class="alert-top">
              <h3 class="alert-title">${esc(alert.guard_name)}</h3>
              <span class="tag ${isBlocking ? 'bad' : 'plain'}">${isBlocking ? '阻断' : '记录'}</span>
              ${alert.expect && alert.actual ? `<span class="tag warn">期望 ${esc(alert.expect)} · 实际 ${esc(alert.actual)}</span>` : ''}
            </div>
            <div class="alert-meta">
              <span>${esc(alert.guard_id)}</span><span class="sep">·</span>
              <span>${esc(alert.target)}</span>
              ${alert.commit ? `<span class="sep">·</span><span>${esc(alert.commit)}</span>` : ''}
              <span class="sep">·</span><span>${relTime(alert.at)}</span>
              ${alert.runner ? `<span class="sep">·</span><span>${esc(alert.runner)}</span>` : ''}
            </div>
            <p class="alert-desc"><span class="k">问题：</span>${esc(alert.detail)}</p>
            ${alert.cases?.length ? `<div class="tag-row" style="margin-top:8px">${alert.cases.map((id) => `<span class="tag mono">case ${esc(id)}</span>`).join('')}</div>` : ''}
          </div>
          <div class="alert-actions">
            <button class="btn-ghost" type="button" data-record-open="${esc(alert.id)}">查看证据 ${icon('arrow-right')}</button>
          </div>
        </article>`;
      })
      .join('');
    return `<div class="alert-list">${cards}</div>${pager(rows.length, page, PAGE_SIZE.alerts, 'alerts')}`;
  }

  /* ------------------------------------------------------------ 最近验证面板 */
  function codePanel(record) {
    const trace = record.trace || [];
    const lines = trace.length
      ? trace.map((line, index) => `<div class="code-line err"><span class="ln">${index + 1}</span><span>${esc(line)}</span></div>`).join('')
      : '';
    const caseBlock =
      record.expect && record.actual
        ? `<dl class="code-case">
            <dt>case</dt><dd>${esc((record.violated_cases || [])[0] || 'guard-case')}</dd>
            <dt>expect</dt><dd class="good">${esc(record.expect)}</dd>
            <dt>actual</dt><dd class="bad">${esc(record.actual)}</dd>
          </dl>`
        : '';
    const file = (record.target || 'target.py').split(' · ')[0];
    return `<div class="code-card">
      <div class="code-head">${icon('code')}<span class="code-file">${esc(file)}</span>
        <button class="code-copy" type="button" data-copy="${esc(trace.join('\n') || record.target || '')}" title="复制">${icon('copy')}</button>
      </div>
      <div class="code-body">${caseBlock}${lines}</div>
    </div>`;
  }

  function flowPanel(record) {
    const rows = [
      ['scope_decision', record.scope_decision],
      ['execution_outcome', record.execution_outcome],
      ['final_verdict', record.final_verdict],
    ];
    return `<div class="code-card">
      <div class="code-head">${icon('code')}<span class="code-file">判定链路</span></div>
      <div class="code-body">
        ${rows
          .map(
            ([key, value], index) =>
              `<div class="code-line"><span class="ln">${index + 1}</span><span>${key} = ${esc(value)}</span></div>`
          )
          .join('')}
      </div>
    </div>`;
  }

  function alertBoxFor(record) {
    const guard = ds().guards.find((item) => item.id === record.guard_id);
    const detail =
      record.expect && record.actual
        ? `守卫在 ${record.target} 上返回 ${record.actual}，契约要求 ${record.expect}。`
        : record.reason || '守卫触发了历史失败 case。';
    const source = guard?.source_defect
      ? `${guard.source_defect} ${guard.source_defect_id || ''}`
      : `固定 CI fixture · ${record.contract || '—'}`;
    return `<div class="alert-box">
      <div class="alert-title">${icon('alert')}检测到历史边界缺陷可能回归<span class="tag warn">警告</span></div>
      <dl class="kv">
        <dt>匹配的守卫</dt><dd><strong>${esc(record.guard_name)}</strong></dd>
        <dt>来源缺陷</dt><dd>${esc(source)}</dd>
        <dt>问题描述</dt><dd>${esc(detail)}</dd>
      </dl>
    </div>`;
  }

  function passBox(record) {
    return `<div class="alert-box good">
      <div class="alert-title">${icon('check-circle')}适用且未触发历史缺陷<span class="tag ok">通过</span></div>
      <dl class="kv">
        <dt>判定依据</dt><dd>${esc(record.scope_decision === 'applicable' ? '适用条件命中，pytest 退出 0' : '该目标不适用，未启动 pytest')}</dd>
        <dt>执行</dt><dd>${esc(EXECUTION[record.execution_outcome]?.label || record.execution_outcome)}</dd>
        <dt>记录</dt><dd class="mono">${esc(record.run_id || record.id)}</dd>
      </dl>
    </div>`;
  }

  function verifyCard(record) {
    if (!record) {
      return `<section class="card"><div class="card-head">${icon('file')}<h2 class="card-title">最近一次验证</h2></div>
        <div class="empty">${icon('file')}<h3>还没有验证记录</h3><p>先运行一次 replay 或 verify。</p></div></section>`;
    }
    const bad = record.final_verdict === 'violation';
    const target = (record.target || '').split(' · ')[0];
    const meta = [
      target,
      record.base_commit ? `${record.base_commit} → ${record.head_commit || 'HEAD'}` : record.run_id || '',
      record.backend || '',
    ]
      .filter(Boolean)
      .join(' · ');
    return `<section class="card">
      <div class="card-head">${icon('file')}<h2 class="card-title">最近一次验证</h2>
        <a class="card-link" href="#/records">查看全部记录 ${icon('arrow-right')}</a>
      </div>
      <div class="verify-panel">
        <div class="verify-head">
          <span class="tile ${bad ? 'red' : ''}">${icon(bad ? 'alert' : 'check-circle')}</span>
          <div class="verify-head-main">
            <div class="verify-title">检查候选代码变更</div>
            <div class="verify-meta">${icon('branch')}<span>${esc(meta)}</span></div>
          </div>
          <span class="tag ${bad ? 'bad' : 'ok'}">${bad ? '警告' : '通过'}</span>
        </div>
        ${record.trace?.length || (record.expect && record.actual) ? codePanel(record) : flowPanel(record)}
        ${bad ? alertBoxFor(record) : passBox(record)}
      </div>
    </section>`;
  }

  /* ------------------------------------------------------------ 页面：总览 */
  function demoBanner() {
    if (state.source !== 'demo') return '';
    return `<div class="demo-banner">${icon('alert')}<span><strong>演示数据</strong> · 用于界面展示与录屏，不代表本机真实记录。</span>
      <button type="button" data-source-switch="real">切回真实记录</button></div>`;
  }

  function projectMeta() {
    const meta = DATA.meta;
    return `${meta.branch} · ${meta.head}`;
  }

  function pageFooter() {
    const meta = DATA.meta;
    return `<footer class="page-foot">
      <span>只读快照 · ${fmtDateTime(meta.generated_at)}</span>
      <span class="sep">·</span>
      <span>Registry ${short(meta.registry?.id)}</span>
      <span class="sep">·</span>
      <span>来源 .counterguard/registry.json + artifacts/</span>
      ${state.source === 'demo' ? '<span class="sep">·</span><span class="foot-warn">当前为演示数据</span>' : ''}
    </footer>`;
  }

  function renderOverview() {
    const data = ds();
    const latest = data.verifications[0];
    return `<div class="page-head">
        <div>
          <h1>CounterGuard <span class="accent">控制台</span></h1>
          <p class="page-sub">把一次修复变成可以反复使用的检查，并智能判断它应该用在哪里。</p>
        </div>
        <div class="page-actions">
          <span class="tag outline mono">${esc(projectMeta())}</span>
          <span class="tag outline">Apache-2.0</span>
        </div>
      </div>
      ${demoBanner()}
      ${renderKpis(data.kpis)}
      <div class="dash-grid">
        <section class="card">
          <div class="card-head">${icon('shield')}<h2 class="card-title">守卫列表</h2>
            <span class="count-pill">${num(data.guards.length)}</span>
          </div>
          <div class="toolbar">
            <label class="field search">${icon('search')}<input type="search" data-search-input placeholder="搜索守卫名称或关键…" value="${esc(state.search)}" aria-label="搜索守卫"></label>
            <span class="select"><select data-filter="family" aria-label="契约族">${familyOptions()}</select>${icon('chevron-down')}</span>
            <span class="select"><select data-filter="gstate" aria-label="状态">${stateOptions()}</select>${icon('chevron-down')}</span>
            <span class="select"><select data-filter="gresult" aria-label="最近结果">${resultOptions()}</select>${icon('chevron-down')}</span>
          </div>
          <div id="list-region">${overviewListMarkup()}</div>
        </section>
        ${verifyCard(latest)}
      </div>`;
  }

  function familyOptions() {
    const families = [...new Set(ds().guards.map((guard) => guard.family).filter(Boolean))];
    return `<option value="all">全部契约</option>${families
      .map((family) => `<option value="${esc(family)}" ${state.family === family ? 'selected' : ''}>${esc(familyName(family))}</option>`)
      .join('')}`;
  }
  function stateOptions() {
    return `<option value="all">全部状态</option>${Object.entries(GUARD_STATE)
      .map(([key, meta]) => `<option value="${key}" ${state.gstate === key ? 'selected' : ''}>${meta.label}</option>`)
      .join('')}`;
  }
  function resultOptions() {
    return `<option value="all">最近结果</option>${['pass', 'violation', 'skipped', 'inconclusive']
      .map((key) => `<option value="${key}" ${state.gresult === key ? 'selected' : ''}>${VERDICT[key].label}</option>`)
      .join('')}`;
  }

  /* ------------------------------------------------------------ 页面：守卫库 */
  function renderGuards() {
    const data = ds();
    return `<div class="page-head">
        <div>
          <h1>守卫库</h1>
          <p class="page-sub">每条守卫只保留这次真实失败、且已在 fixed 目标上自检通过的 case。</p>
        </div>
        <div class="page-actions"><span class="tag outline mono">${num(data.guards.length)} guards</span></div>
      </div>
      ${demoBanner()}
      <section class="card">
        <div class="card-head">${icon('shield')}<h2 class="card-title">已登记守卫</h2>
          <span class="count-pill">${num(data.guards.length)}</span>
          <a class="card-link" href="#/scope">适用范围 ${icon('arrow-right')}</a>
        </div>
        <div class="toolbar">
          <label class="field search">${icon('search')}<input type="search" data-search-input placeholder="搜索守卫、契约或缺陷…" value="${esc(state.search)}" aria-label="搜索守卫"></label>
          <span class="select"><select data-filter="family" aria-label="契约族">${familyOptions()}</select>${icon('chevron-down')}</span>
          <span class="select"><select data-filter="gstate" aria-label="状态">${stateOptions()}</select>${icon('chevron-down')}</span>
          <span class="select"><select data-filter="gresult" aria-label="最近结果">${resultOptions()}</select>${icon('chevron-down')}</span>
          <span class="toolbar-spacer"></span>
          <span class="tag plain">点击行查看详情</span>
        </div>
        <div id="list-region">${guardsListMarkup()}</div>
      </section>`;
  }

  /* ------------------------------------------------------------ 页面：验证记录 */
  function renderRecords() {
    const data = ds();
    const records = data.verifications;
    const counts = { applicable: 0, inapplicable: 0, unknown: 0, violation: 0 };
    records.forEach((record) => {
      counts[record.scope_decision] = (counts[record.scope_decision] || 0) + 1;
      if (record.final_verdict === 'violation') counts.violation += 1;
    });
    const summary = [
      { label: '适用', value: counts.applicable, unit: '条', icon: 'check-circle', tone: '' },
      { label: '不适用（未启动 pytest）', value: counts.inapplicable, unit: '条', icon: 'slash', tone: 'neutral' },
      { label: '信息不足', value: counts.unknown, unit: '条', icon: 'help', tone: 'neutral' },
      { label: '确认违规', value: counts.violation, unit: '条', icon: 'alert', tone: 'down' },
    ];
    return `<div class="page-head">
        <div>
          <h1>验证记录</h1>
          <p class="page-sub">先判适用性，再决定是否执行；跳过与信息不足永远不会被当成“通过”。</p>
        </div>
        <div class="page-actions"><span class="tag outline mono">${num(records.length)} records</span></div>
      </div>
      ${demoBanner()}
      <div class="summary-row">
        ${summary
          .map(
            (item) => `<div class="summary">
              <span class="tile ${item.tone === 'down' ? 'red' : item.tone === 'neutral' ? '' : ''}">${icon(item.icon)}</span>
              <div><div class="summary-label">${item.label}</div><div class="summary-value">${num(item.value)}<small>${item.unit}</small></div></div>
            </div>`
          )
          .join('')}
      </div>
      <section class="card">
        <div class="card-head">${icon('file')}<h2 class="card-title">全部记录</h2>
          <span class="count-pill">${num(records.length)}</span>
        </div>
        <div class="filters-bar">
          <div class="chip-group" role="group" aria-label="记录类型">
            ${[
              ['all', '全部'],
              ['replay', '重放 replay'],
              ['verify', '验证 verify'],
            ]
              .map(([key, label]) => `<button type="button" data-chip="kind" data-value="${key}" class="${state.kind === key ? 'active' : ''}">${label}</button>`)
              .join('')}
          </div>
          <span class="select"><select data-filter="verdict" aria-label="结论">${['all', 'pass', 'violation', 'skipped', 'inconclusive']
            .map((key) => `<option value="${key}" ${state.verdict === key ? 'selected' : ''}>${key === 'all' ? '全部结论' : VERDICT[key].label}</option>`)
            .join('')}</select>${icon('chevron-down')}</span>
          <label class="field search" style="margin-left:auto">${icon('search')}<input type="search" data-search-input placeholder="搜索守卫或目标…" value="${esc(state.search)}" aria-label="搜索记录"></label>
        </div>
        <div id="list-region">${recordsListMarkup()}</div>
      </section>`;
  }

  /* ------------------------------------------------------------ 页面：适用范围 */
  function renderScope() {
    const data = ds();
    const scope = data.scope || DATA.real.scope;
    const records = data.verifications;
    const decisions = { applicable: 0, inapplicable: 0, unknown: 0 };
    records.forEach((record) => {
      decisions[record.scope_decision] = (decisions[record.scope_decision] || 0) + 1;
    });
    const states = [
      { key: 'applicable', name: 'applicable · 适用', desc: '目标在适用条件内，执行 pytest', cls: '', icon: 'check-circle' },
      { key: 'inapplicable', name: 'inapplicable · 不适用', desc: '已确认不属于该守卫，直接跳过', cls: 'off', icon: 'slash' },
      { key: 'unknown', name: 'unknown · 信息不足', desc: '证据不足，不执行也不下结论', cls: 'unk', icon: 'help' },
    ];
    const bestFp = Math.min(...scope.methods.map((method) => method.fp));
    const best = scope.methods.find((method) => method.fp === bestFp);

    return `<div class="page-head">
        <div>
          <h1>适用范围</h1>
          <p class="page-sub">守卫该在哪里生效，靠已确认的反例学出来——不是靠路径、名字或契约 ID 猜出来。</p>
        </div>
        <div class="page-actions"><span class="tag outline mono">${esc(scope.protocol)}</span></div>
      </div>
      ${demoBanner()}
      <div class="scope-grid">
        <section class="card">
          <div class="card-head">${icon('target')}<h2 class="card-title">判定三态</h2><span class="count-pill">${num(records.length)}</span></div>
          <div class="state-cards">
            ${states
              .map(
                (item) => `<div class="state-card ${item.cls}">
                  <span class="dotmark"></span>
                  <div><div class="state-name">${item.name}</div><div class="state-desc">${item.desc}</div></div>
                  <span class="state-count">${num(decisions[item.key] || 0)}</span>
                </div>`
              )
              .join('')}
          </div>
          <div class="footnote">
            不适用与信息不足都不启动 pytest，记录里 <b>run=null</b>。
            跳过的行不会被任何报表折算成 pass；unknown 单独统计，并同时报告判定覆盖率。
          </div>
        </section>

        <section class="card">
          <div class="card-head">${icon('layers')}<h2 class="card-title">冻结实验 ${esc(scope.split_id)}</h2>
            <span class="count-pill">${scope.samples.train} 训练 · ${scope.samples.holdout} 留出</span>
          </div>
          <div class="predicates">
            <div class="predicate">
              <div class="predicate-label">initial<span class="tag plain">只用训练样本</span></div>
              <div class="predicate-code">${scope.per_guard
                .map((guard) => `<div>${esc(guard.initial)}</div>`)
                .join('')}</div>
              <div class="predicate-foot"><span>搜索空间 <b>${scope.per_guard
                .map((guard) => num(guard.candidates))
                .join(' / ')}</b> 个候选</span></div>
            </div>
            <div class="predicate refined">
              <div class="predicate-label">refined<span class="tag ok">+2 个合法反例</span></div>
              <div class="predicate-code">${scope.per_guard
                .map((guard) => `<div><b>${esc(guard.refined.split(' ∧ ')[0])}</b> ∧ ${esc(guard.refined.split(' ∧ ').slice(1).join(' ∧ '))}</div>`)
                .join('')}</div>
              <div class="predicate-foot"><span>训练集 FP：<b>0</b> · 规则在 ${scope.shuffles} 次打乱下不变</span></div>
            </div>
          </div>
          <div class="footnote">
            学习器只接收 <b>FeatureVector</b> 与明确的适用性布尔值；契约 ID、路径、模块名、目标名、期望输出和 oracle 值都不进入特征。
            加入反例后规则从「只看版本」收紧为「版本 AND 接口」。
          </div>
        </section>
      </div>

      <section class="card" style="margin-top:18px">
        <div class="card-head">${icon('chart')}<h2 class="card-title">留出集上的四种方法</h2>
          <span class="count-pill">${scope.samples.holdout} 个样本</span>
          <a class="card-link" href="#/records">看原始记录 ${icon('arrow-right')}</a>
        </div>
        <div class="method-table">
          <div class="method-row head">
            <span>方法</span><span>TP / FP / TN / FN</span><span>错误应用率</span><span>Bug Recall</span>
          </div>
          ${scope.methods
            .map(
              (method) => `<div class="method-row ${method.id === best?.id ? 'best' : ''}">
                <div>
                  <div class="method-name">${esc(method.name)}${method.id === best?.id ? ' · 最优' : ''}</div>
                  <div class="method-note">${esc(method.note)}</div>
                </div>
                <div class="method-confusion">
                  <span class="conf-chip tp">${method.tp}</span>
                  <span class="conf-chip fp">${method.fp}</span>
                  <span class="conf-chip">${method.tn}</span>
                  <span class="conf-chip fn">${method.fn}</span>
                </div>
                <div class="method-bar">
                  <span class="bar-track"><span class="bar-fill ${method.false_application_rate === 0 ? 'good' : ''}" style="width:${Math.round((method.false_application_rate || 0) * 100)}%"></span></span>
                  <span class="val">${pct(method.false_application_rate)}</span>
                </div>
                <div><span class="tag ${method.bug_recall === 1 ? 'ok' : 'plain'}">${method.bug_recall == null ? 'null' : `${Math.round(method.bug_recall * 100)}%`}</span></div>
              </div>`
            )
            .join('')}
        </div>
        <div class="footnote">
          ${scope.samples.holdout} 个留出样本、<b>公开标签</b>、<b>工程验证</b>：只能说明这组样本上反例精化有效，不是外部盲测，也不能外推为泛化结论。
          query 守卫没有留出缺陷，所以它的 Bug Recall 记为空值，而不是 100%。
        </div>
      </section>`;
  }

  /* ------------------------------------------------------------ 页面：警告 */
  function renderAlerts() {
    const data = ds();
    const violations = data.verifications.filter((record) => record.final_verdict === 'violation');
    return `<div class="page-head">
        <div>
          <h1>警告</h1>
          <p class="page-sub">只有「确认适用 + 执行失败」才会触发；Shadow 阶段的违规只记录，不阻断。</p>
        </div>
        <div class="page-actions"><span class="tag bad">${num(violations.length)} 条确认违规</span></div>
      </div>
      ${demoBanner()}
      <section class="card">
        <div class="card-head">${icon('alert')}<h2 class="card-title">回归警告</h2>
          <span class="count-pill">${num(data.alerts.length)}</span>
          <span class="card-link" style="pointer-events:none">${state.source === 'demo' ? '演示数据' : '本机记录'}</span>
        </div>
        <div id="list-region" style="padding:4px 16px 16px">${alertListMarkup()}</div>
      </section>`;
  }

  /* ------------------------------------------------------------ 抽屉 */
  function guardDrawer(guard) {
    const cases = guard.cases?.length
      ? `<table class="case-table"><thead><tr><th>case</th><th>参数</th><th>期望</th></tr></thead><tbody>
          ${guard.cases
            .map(
              (item) => `<tr>
                <td>${esc(item.id)}</td>
                <td>${esc(Object.entries(item.args || {}).map(([key, value]) => `${key}=${value}`).join(', ') || '—')}</td>
                <td>${item.raises ? `raise ${esc(item.raises)}` : esc(item.expected ?? '—')}</td>
              </tr>`
            )
            .join('')}
        </tbody></table>`
      : '<p class="page-sub">该守卫没有可展示的 case（演示数据）。</p>';

    return `<div class="drawer-head">
        <span class="tile">${icon('shield')}</span>
        <div style="min-width:0">
          <div class="drawer-title">${esc(guard.name)}</div>
          <div class="drawer-sub">${esc(guard.id)}</div>
        </div>
        <button class="drawer-close" type="button" data-drawer-close aria-label="关闭">${icon('x')}</button>
      </div>
      <div class="drawer-body">
        <div class="tag-row">
          ${guardStateTag(guard.state)}
          <span class="tag plain">v${esc(guard.version ?? '1')}</span>
          <span class="tag plain mono">${esc(guard.contract_version || '—')}</span>
          ${guard.evidence_reproduced ? '<span class="tag ok">buggy 失败 / fixed 通过</span>' : ''}
        </div>
        <section class="drawer-section">
          <h4>基本信息</h4>
          <div class="meta-grid">
            <div class="meta-item"><div class="meta-key">契约</div><div class="meta-val mono">${esc(guard.contract)}</div></div>
            <div class="meta-item"><div class="meta-key">接口</div><div class="meta-val">${esc(interfaceName(guard.interface_kind))}</div></div>
            <div class="meta-item"><div class="meta-key">注册时间</div><div class="meta-val">${fmtDateTime(guard.registered_at)}</div></div>
            <div class="meta-item"><div class="meta-key">来源证据</div><div class="meta-val mono">${esc(guard.evidence_id || '—')}</div></div>
          </div>
        </section>
        <section class="drawer-section">
          <h4>适用范围</h4>
          <div class="rule-box before"><span class="rule-tag">initial</span>${esc(guard.scope_initial || '—')}</div>
          <div class="rule-box" style="margin-top:8px"><span class="rule-tag">refined</span>${esc(guard.scope_refined || '—')}</div>
        </section>
        <section class="drawer-section">
          <h4>守卫 case（${guard.case_count}）</h4>
          ${cases}
        </section>
        <section class="drawer-section">
          <h4>fixed 自检</h4>
          <div class="meta-grid">
            <div class="meta-item"><div class="meta-key">结果</div><div class="meta-val">${esc(guard.validation?.outcome || '—')}</div></div>
            <div class="meta-item"><div class="meta-key">pytest 退出码</div><div class="meta-val">${esc(guard.validation?.exit_code ?? '—')}</div></div>
            <div class="meta-item"><div class="meta-key">耗时</div><div class="meta-val">${fmtDuration(guard.validation?.duration_ms)}</div></div>
            <div class="meta-item"><div class="meta-key">运行环境</div><div class="meta-val">pytest ${esc(guard.validation?.pytest || '—')} · Python ${esc(guard.validation?.python || '—')}</div></div>
          </div>
        </section>
        <section class="drawer-section">
          <h4>摘要</h4>
          <div class="rule-box">
            <div>guard ${esc(short(guard.digests?.guard))}</div>
            <div>test ${esc(short(guard.digests?.test))}</div>
            <div>evidence ${esc(short(guard.digests?.evidence))}</div>
          </div>
          <p class="footnote" style="padding:10px 0 0">摘要链用于一致性检查，不认证操作者、主机或 OS 执行真实性。</p>
        </section>
      </div>`;
  }

  function recordDrawer(record) {
    const decision = DECISION[record.scope_decision] || DECISION.unknown;
    const verdict = VERDICT[record.final_verdict] || VERDICT.inconclusive;
    return `<div class="drawer-head">
        <span class="tile ${record.final_verdict === 'violation' ? 'red' : ''}">${icon(record.final_verdict === 'violation' ? 'alert' : 'file')}</span>
        <div style="min-width:0">
          <div class="drawer-title">${esc(record.kind === 'verify' ? 'verify 记录' : 'replay 记录')} · ${verdict.label}</div>
          <div class="drawer-sub">${esc(record.id)} · ${esc(record.run_id || '')}</div>
        </div>
        <button class="drawer-close" type="button" data-drawer-close aria-label="关闭">${icon('x')}</button>
      </div>
      <div class="drawer-body">
        <div class="tag-row">
          <span class="tag ${decision.cls}">${icon(decision.icon)}${decision.label}</span>
          <span class="tag plain">execution ${esc(record.execution_outcome)}</span>
          ${record.kind === 'verify' ? '<span class="tag warn">Docker</span>' : '<span class="tag plain">本地重放</span>'}
          ${record.blocking ? '<span class="tag bad">阻断</span>' : ''}
        </div>
        <section class="drawer-section">
          <h4>记录</h4>
          <div class="meta-grid">
            <div class="meta-item"><div class="meta-key">守卫</div><div class="meta-val">${esc(record.guard_name)}</div></div>
            <div class="meta-item"><div class="meta-key">目标</div><div class="meta-val mono">${esc(record.target)}</div></div>
            <div class="meta-item"><div class="meta-key">时间</div><div class="meta-val">${fmtDateTime(record.at)}</div></div>
            <div class="meta-item"><div class="meta-key">耗时</div><div class="meta-val">${fmtDuration(record.duration_ms)}</div></div>
          </div>
        </section>
        ${record.trace?.length
          ? `<section class="drawer-section"><h4>失败断言</h4>${codePanel(record)}</section>`
          : `<section class="drawer-section"><h4>判定链路</h4>${flowPanel(record)}</section>`}
        ${record.violated_cases?.length ? `<section class="drawer-section"><h4>触发的 case</h4><div class="tag-row">${record.violated_cases.map((id) => `<span class="tag mono">${esc(id)}</span>`).join('')}</div></section>` : ''}
        <section class="drawer-section">
          <h4>证据引用</h4>
          <div class="rule-box">${esc(record.ref || '—')}</div>
          ${record.reason ? `<p class="footnote" style="padding:10px 0 0">reason：${esc(record.reason)}</p>` : ''}
        </section>
      </div>`;
  }

  function openDrawer(kind, id) {
    const data = ds();
    const payload = kind === 'guard' ? data.guards.find((item) => item.id === id) : data.verifications.find((item) => item.id === id);
    if (!payload) return;
    clearTimeout(drawerTimer);
    drawerRoot.innerHTML = `<div class="drawer-overlay" data-drawer-close></div>
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="详情">${kind === 'guard' ? guardDrawer(payload) : recordDrawer(payload)}</aside>`;
    requestAnimationFrame(() => drawerRoot.classList.add('open'));
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer() {
    if (!drawerRoot.classList.contains('open')) return;
    drawerRoot.classList.remove('open');
    document.body.style.overflow = '';
    clearTimeout(drawerTimer);
    drawerTimer = setTimeout(() => {
      drawerRoot.innerHTML = '';
    }, 260);
  }

  /* ------------------------------------------------------------ 提示 */
  let toastTimer = null;
  let drawerTimer = null;
  function toast(message) {
    let node = document.getElementById('cg-toast');
    if (!node) {
      node = document.createElement('div');
      node.id = 'cg-toast';
      node.style.cssText =
        'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);background:#0e1c16;color:#fff;padding:10px 16px;border-radius:10px;font-size:12.5px;z-index:60;opacity:0;transition:opacity .2s;box-shadow:0 12px 30px -12px rgba(0,0,0,.4)';
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      node.style.opacity = '0';
    }, 1800);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制');
    } catch (error) {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand('copy');
        toast('已复制');
      } catch (fallbackError) {
        toast('复制失败，请手动选择');
      }
      area.remove();
    }
  }

  /* ------------------------------------------------------------ 框架事件 */
  function updateChrome() {
    const data = ds();
    const guardCount = data.guards.length;
    const alertCount = data.alerts.length;
    document.getElementById('nav-guards').textContent = guardCount ? num(guardCount) : '';
    document.getElementById('nav-guards').hidden = !guardCount;
    document.getElementById('nav-alerts').textContent = alertCount ? num(alertCount) : '';
    document.getElementById('nav-alerts').hidden = !alertCount;
    document.getElementById('bell-dot').hidden = alertCount === 0;
    document.getElementById('side-meta').textContent = `v${DATA.meta.version} Beta · ${DATA.meta.branch} · ${DATA.meta.head}`;

    const toggle = document.getElementById('source-toggle');
    const demo = state.source === 'demo';
    toggle.classList.toggle('is-demo', demo);
    toggle.setAttribute('aria-pressed', String(demo));
    toggle.title = demo ? '当前为演示数据，点击切回真实记录' : '当前为真实记录，点击查看演示数据';
    document.getElementById('source-label').textContent = demo ? '演示数据' : '真实记录';

    document.querySelectorAll('.nav-item').forEach((item) => {
      item.classList.toggle('active', item.dataset.route === state.route);
    });
  }

  function syncSearchInputs() {
    document.querySelectorAll('[data-search-input]').forEach((input) => {
      if (input.value !== state.search) input.value = state.search;
    });
    const global = document.getElementById('global-search');
    if (global && global.value !== state.search) global.value = state.search;
  }

  function updateList() {
    const region = document.getElementById('list-region');
    if (!region) return;
    if (state.route === 'overview') region.innerHTML = overviewListMarkup();
    else if (state.route === 'guards') region.innerHTML = guardsListMarkup();
    else if (state.route === 'records') region.innerHTML = recordsListMarkup();
    else if (state.route === 'alerts') region.innerHTML = alertListMarkup();
  }

  function resetPages() {
    state.overviewPage = 1;
    state.guardsPage = 1;
    state.recordsPage = 1;
    state.alertsPage = 1;
  }

  function render() {
    updateChrome();
    const routes = { overview: renderOverview, guards: renderGuards, records: renderRecords, scope: renderScope, alerts: renderAlerts };
    const renderer = routes[state.route] || renderOverview;
    view.innerHTML = renderer() + pageFooter();
    syncSearchInputs();
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  function navigate(route) {
    if (!route) route = 'overview';
    if (location.hash !== `#/${route}`) {
      location.hash = `#/${route}`;
      return;
    }
    state.route = route;
    render();
  }

  /* ------------------------------------------------------------ 事件绑定 */
  view.addEventListener('click', (event) => {
    const sourceSwitch = event.target.closest('[data-source-switch]');
    if (sourceSwitch) {
      setSource(sourceSwitch.dataset.sourceSwitch);
      return;
    }

    const chip = event.target.closest('[data-chip]');
    if (chip) {
      state[chip.dataset.chip] = chip.dataset.value;
      resetPages();
      render();
      return;
    }

    const pageButton = event.target.closest('[data-page]');
    if (pageButton && !pageButton.disabled) {
      const key = pageButton.closest('[data-key]')?.dataset.key;
      const page = Number(pageButton.dataset.page);
      if (key) {
        state[`${key}Page`] = page;
        updateList();
        const region = document.getElementById('list-region');
        region?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
      return;
    }

    const guardRow = event.target.closest('tr[data-guard]');
    if (guardRow) {
      openDrawer('guard', guardRow.dataset.guard);
      return;
    }

    const recordRow = event.target.closest('tr[data-record]');
    if (recordRow) {
      openDrawer('record', recordRow.dataset.record);
      return;
    }

    const recordOpen = event.target.closest('[data-record-open]');
    if (recordOpen) {
      const alert = alertList().find((item) => item.id === recordOpen.dataset.recordOpen);
      const record = alert
        ? ds().verifications.find(
            (item) => item.guard_id === alert.guard_id && item.target === alert.target && item.at === alert.at
          ) || ds().verifications.find((item) => item.guard_id === alert.guard_id)
        : null;
      if (record) openDrawer('record', record.id);
      return;
    }

    const copyButton = event.target.closest('[data-copy]');
    if (copyButton) {
      event.stopPropagation();
      copyText(copyButton.dataset.copy || '');
    }
  });

  view.addEventListener('input', (event) => {
    const input = event.target.closest('[data-search-input]');
    if (!input) return;
    state.search = input.value;
    resetPages();
    syncSearchInputs();
    updateList();
  });

  view.addEventListener('change', (event) => {
    const select = event.target.closest('[data-filter]');
    if (!select) return;
    state[select.dataset.filter] = select.value;
    resetPages();
    updateList();
  });

  view.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    const row = event.target.closest('tr[data-guard]');
    if (row) {
      openDrawer('guard', row.dataset.guard);
      return;
    }
    const record = event.target.closest('tr[data-record]');
    if (record) openDrawer('record', record.dataset.record);
  });

  drawerRoot.addEventListener('click', (event) => {
    if (event.target.closest('[data-drawer-close]')) closeDrawer();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeDrawer();
    if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      event.preventDefault();
      document.getElementById('global-search').focus();
    }
  });

  document.getElementById('global-search').addEventListener('input', (event) => {
    state.search = event.target.value;
    resetPages();
    syncSearchInputs();
    updateList();
  });

  document.getElementById('global-search').addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.target.value = '';
      state.search = '';
      resetPages();
      syncSearchInputs();
      updateList();
      event.target.blur();
    }
  });

  function setSource(source) {
    state.source = source;
    localStorage.setItem('cg.source', source);
    resetPages();
    render();
    toast(source === 'demo' ? '已切换到演示数据（不代表本机真实记录）' : '已切换到真实记录');
  }

  document.getElementById('source-toggle').addEventListener('click', () => {
    setSource(state.source === 'demo' ? 'real' : 'demo');
  });

  document.getElementById('bell-dot').parentElement.addEventListener('click', () => navigate('alerts'));

  const ROUTES = ['overview', 'guards', 'records', 'scope', 'alerts'];

  function parseLocation() {
    const raw = location.hash.replace(/^#\/?/, '') || 'overview';
    const [path] = raw.split('?');
    const [route, id] = path.split('/');
    return { route: ROUTES.includes(route) ? route : 'overview', id: id ? decodeURIComponent(id) : '' };
  }

  function applyRoute() {
    const { route, id } = parseLocation();
    closeDrawer();
    state.route = route;
    render();
    if (id) openDrawer(route === 'records' ? 'record' : 'guard', id);
  }

  window.addEventListener('hashchange', applyRoute);

  /* ------------------------------------------------------------ 启动 */
  const params = new URLSearchParams(location.search);
  if (params.get('demo') === '1') state.source = 'demo';
  if (params.get('source') === 'real') state.source = 'real';
  applyRoute();
})();
