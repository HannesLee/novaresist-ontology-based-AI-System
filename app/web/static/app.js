// 온트윈 화면
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = async (path, opt = {}) => {
  const r = await fetch('/ow/api/' + path, {
    headers: { 'Content-Type': 'application/json' }, ...opt,
    body: opt.body && typeof opt.body !== 'string' ? JSON.stringify(opt.body) : opt.body,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const boldFix = s => (s || '').replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>');  // 한글 바로 앞뒤 굵게 표시 보정
const md = s => window.marked ? marked.parse(boldFix(s)) : esc(s);
const toast = (t, ms = 2600) => { const d = document.createElement('div'); d.className = 'toast'; d.textContent = t; document.body.append(d); setTimeout(() => d.remove(), ms); };
const fmt = v => v === null || v === undefined ? '' : typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 3 }))
  : Array.isArray(v) ? v.map(x => typeof x === 'object' && x ? Object.values(x).join(' ') : x).join(' · ')
  : typeof v === 'object' ? Object.entries(v).map(([k, x]) => `${k}: ${typeof x === 'object' ? fmt(x) : x}`).join(' · ') : v;
function table(cols, rows, limit = 300) {
  return `<table class="grid"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${
    rows.slice(0, limit).map(r => `<tr>${cols.map(c => `<td>${esc(fmt(r[c]))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

// ---------------- 탭 ----------------
const loaded = {};
function show(tab) {
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  $$('.tab').forEach(s => s.classList.toggle('on', s.id === 'tab-' + tab));
  if (!loaded[tab]) {
    loaded[tab] = true;
    ({ erp: initErp, graph: () => graphMode('schema'), onto: () => ontoMode('terms'), sync: loadSync })[tab]?.();
  }
  if (tab === 'sync') loadSync();
}
$$('#nav button').forEach(b => b.onclick = () => show(b.dataset.tab));
$('#syncPill').onclick = () => show('sync');
$('#offBtn').onclick = async () => {
  if (!confirm('온트윈을 끌까요? (ERPNext는 계속 켜져 있어요)')) return;
  try { await api('shutdown', { method: 'POST' }); } catch (e) { }
  document.body.innerHTML = '<div class="bye"><img src="/ow/static/img/logo.svg"><h2>온트윈을 껐어요</h2><p>바탕화면의 온트윈 아이콘으로 다시 켤 수 있어요. 이 창은 닫아도 됩니다.</p></div>';
  setTimeout(() => window.close(), 1500);
};

// ---------------- 동기화 상태 ----------------
let lastSyncAt = null;
async function pollStatus() {
  try {
    const s = await api('sync');
    const n = Object.values(s.objects).reduce((a, b) => a + b, 0);
    $('.dot').className = 'dot ' + (s.error ? 'err' : 'live');
    const at = s.last?.at || '';
    $('#syncText').textContent = s.error ? 'ERP 연결 문제' : `실시간 · 객체 ${n.toLocaleString()} · 그래프 ${(s.graph?.관계 || 0).toLocaleString()}관계 · ${at.slice(11, 19)}`;
    if (lastSyncAt && at !== lastSyncAt && s.last?.changed?.length) {
      $('#syncPill').classList.remove('flash'); void $('#syncPill').offsetWidth; $('#syncPill').classList.add('flash');
      toast(`ERP 변경 반영: ${s.last.changed.slice(0, 3).map(c => c[1]).join(', ')}${s.last.changed.length > 3 ? ' 외' : ''}`);
      loaded.graph = false;
    }
    lastSyncAt = at;
    if ($('#tab-sync').classList.contains('on')) renderSync(s);
  } catch (e) { $('.dot').className = 'dot err'; $('#syncText').textContent = '서버 연결 끊김'; }
}
setInterval(pollStatus, 5000); pollStatus();

// ---------------- 대화 공통 ----------------
async function streamChat(body, onStep) {
  const r = await fetch('/ow/api/chat/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '', result = null;
  while (true) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = /event: (\w+)/.exec(chunk)?.[1]; const data = JSON.parse(chunk.slice(chunk.indexOf('data: ') + 6));
      if (ev === 'step') onStep(data); else if (ev === 'done') result = data; else if (ev === 'error') throw new Error(data.error);
    }
  }
  return result;
}
const stepLine = s => `<div>${esc(s.tool)} <small>${esc(JSON.stringify(s.input)).slice(0, 110)} · ${s.ms}ms${s.cypher?.length ? ' · 그래프 질의 ' + s.cypher.length : ''}</small></div>`;

const modelName = id => (MODELS.find(m => m.id === id) || {}).name || id || '';
function renderAnswer(box, r, question, compact) {
  const u = r.usage || {};
  const nq = r.steps.reduce((a, s) => a + (s.cypher?.length || 0), 0);
  box.innerHTML = `${md(r.answer)}<div class="tables"></div>
    <div class="meta"><span class="chip">${esc(modelName(r.model))}</span><span class="chip">온톨로지 v${esc(r.onto_version || '')}</span>
      <span>${r.seconds}초 · 도구 ${r.steps.length}번${nq ? ' · 그래프 질의 ' + nq + '번' : ''}${compact ? '' : ' · 토큰 ' + ((u.input || 0) + (u.output || 0)).toLocaleString()}</span>
      <span class="exp"><button data-f="evid" title="온톨로지·그래프 질의·근거 그래프">🔎 증거</button>
        <button data-f="xlsx">엑셀</button><button data-f="pptx">PPT</button><button data-f="docx">워드</button></span></div>
    ${r.evidence.length ? `<div class="meta">근거 ${r.evidence.map(x => `<button class="ev">${esc(x)}</button>`).join('')}</div>` : ''}
    ${r.unverified?.length ? `<div class="meta">도구 결과에 없는 번호(확인 필요): ${r.unverified.map(esc).join(', ')}</div>` : ''}
    <details class="steps"><summary>사용한 도구 ${r.steps.length}개 보기</summary>${r.steps.map(s =>
      `<div class="step"><b>${esc(s.tool)}</b> <code>${esc(JSON.stringify(s.input))}</code> <small>${s.ms}ms</small>
       ${(s.cypher || []).map(c => `<pre class="cy">${esc(c)}</pre>`).join('')}<pre>${esc(s.output)}</pre></div>`).join('')}</details>`;
  $$('.ev', box).forEach(b => b.onclick = () => openObject(b.textContent));
  $$('.exp button', box).forEach(b => b.onclick = () => b.dataset.f === 'evid' ? openEvidence(r, question) : download(b.dataset.f, { answer: r, question }));
  for (const id of r.tables || []) resultTable($('.tables', box), id);
}

async function resultTable(el, id) {
  const c = await api('board/card/' + id);
  const d = document.createElement('div'); d.className = 'rtable';
  d.innerHTML = `<div class="rt-head"><b>📊 ${esc(c.title)}</b> <span class="muted">${c.total}행</span>
    <span class="exp"><button data-a="xlsx">엑셀</button><button data-a="pptx">PPT</button><button data-a="docx">워드</button><button data-a="csv">CSV</button><button data-a="refresh" title="ERP 최신값으로 다시 계산">⟳</button></span></div>
    ${c.note ? `<div class="muted small">${esc(c.note)}</div>` : ''}${c.chart ? '<div class="chart"></div>' : ''}<div class="tbl">${table(c.columns, c.rows, 100)}</div>
    <details><summary class="muted small">계산 코드</summary><pre class="code">${esc(c.code || '')}</pre></details>`;
  el.append(d);
  if (c.chart) drawChart($('.chart', d), c);
  $$('[data-a]', d).forEach(b => b.onclick = async () => {
    if (b.dataset.a === 'refresh') { await api(`board/card/${id}?refresh=1`); d.remove(); resultTable(el, id); return; }
    download(b.dataset.a, { card: id });
  });
}
function drawChart(el, c) {
  const ch = c.chart, ys = Array.isArray(ch.y) ? ch.y : [ch.y];
  const rows = (c.rows || []).slice(0, 40);
  const chart = echarts.init(el);
  if (ch.type === 'pie') chart.setOption({ tooltip: {}, series: [{ type: 'pie', radius: '65%', data: rows.map(r => ({ name: r[ch.x], value: r[ys[0]] })) }] });
  else chart.setOption({
    tooltip: { trigger: 'axis' }, legend: { show: ys.length > 1, bottom: 0 }, grid: { left: 56, right: 16, top: 20, bottom: ys.length > 1 ? 70 : 54 },
    xAxis: { type: 'category', data: rows.map(r => r[ch.x]), axisLabel: { rotate: 30, fontSize: 10 } }, yAxis: { type: 'value' },
    series: ys.map(y => ({ name: y, type: ch.type === 'line' ? 'line' : 'bar', data: rows.map(r => r[y]) })),
    color: ['#1f3a5f', '#2f6fde', '#e08a1e', '#2e9e6a', '#d64545'],
  });
}
async function download(fmt, body) {
  toast('파일 만드는 중…', 1500);
  const r = await fetch('/ow/api/export/' + fmt, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) return toast('내보내기 실패');
  const cd = r.headers.get('Content-Disposition') || '';
  const name = decodeURIComponent((/filename\*=UTF-8''(.+)/.exec(cd) || [])[1] || 'ontwin.' + fmt);
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = name; a.click();
}

// ---------------- 챗봇 탭 ----------------
let history = [];
const q = $('#q');
let MODELS = [];
function curModel() { try { return localStorage.getItem('ontwin.model') || ''; } catch (e) { return ''; } }
api('models').then(r => {
  MODELS = r.models;
  const saved = curModel() || r.default;
  $('#model').innerHTML = MODELS.map(m => `<option value="${m.id}" ${m.id === saved ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  $('#model').title = MODELS.map(m => `${m.name}: ${m.note}`).join('\n');
});
$('#model').onchange = e => { try { localStorage.setItem('ontwin.model', e.target.value); } catch (x) { } };
const hour = new Date().getHours();
$('#greet').textContent = hour < 12 ? '좋은 아침이에요. 무엇을 확인할까요?' : hour < 18 ? '무엇을 확인할까요?' : '오늘 하루 마무리, 무엇을 확인할까요?';
q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#askForm').requestSubmit(); } });
q.addEventListener('input', () => { q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 200) + 'px'; });
$$('#examples button').forEach(b => b.onclick = () => { q.value = b.textContent; $('#askForm').requestSubmit(); });
$('#askForm').onsubmit = async e => {
  e.preventDefault();
  const question = q.value.trim(); if (!question) return;
  q.value = ''; q.style.height = 'auto';
  $('#chatWrap').classList.remove('empty'); $('.hello')?.remove();
  addMsg('#msgs', 'user', esc(question));
  const box = addMsg('#msgs', 'bot', `<div class="live-steps"><span class="spin"></span> 생각하는 중…</div>`);
  const btn = $('#askForm .send'); btn.disabled = true;
  try {
    const r = await streamChat({ question, history, model: $('#model').value }, step => {
      $('.live-steps', box).insertAdjacentHTML('beforeend', stepLine(step)); box.parentElement.scrollIntoView({ block: 'end' });
    });
    history = r.history.slice(-12);
    renderAnswer(box, r, question);
  } catch (err) { box.innerHTML = `<span class="probs">오류: ${esc(err.message)}</span>`; }
  btn.disabled = false;
};
function addMsg(sel, who, html) {
  const m = document.createElement('div'); m.className = 'msg ' + who;
  m.innerHTML = `<div class="bubble">${html}</div>`;
  $(sel).append(m); m.scrollIntoView({ block: 'end' });
  return $('.bubble', m);
}

// ---------------- 증거 ----------------
async function openEvidence(r, question) {
  const p = await api('chat/prompt?mode=' + (r.mode || 'ontology'));
  const cys = r.steps.flatMap(s => (s.cypher || []).map(c => ({ tool: s.tool, c })));
  $('#drawerBody').innerHTML = `<h3 style="margin-top:0">🔎 이 답의 증거</h3>
    <p class="muted">질문: ${esc(question)}</p>
    <h4>① Claude API에 들어간 온톨로지</h4>
    <div class="kv"><div>모델</div><div>${esc(modelName(r.model) || p.model)} (${esc(r.model || p.model)})</div><div>온톨로지 버전</div><div>v${esc(r.onto_version || p.onto_version)}</div>
      <div>그래프 DB</div><div>LadybugDB · 노드 ${(p.graph.노드 || 0).toLocaleString()} · 관계 ${(p.graph.관계 || 0).toLocaleString()}</div>
      <div>도구</div><div>${p.tools.map(t => esc(t.name)).join(', ')}</div></div>
    <details><summary class="muted">시스템 프롬프트 전문 (${p.system.length.toLocaleString()}자)</summary><pre class="code">${esc(p.system)}</pre></details>
    <h4>② 실행한 그래프 질의 (${cys.length}개)</h4>
    ${cys.length ? cys.map(x => `<div class="small muted">${esc(x.tool)}</div><pre class="cy">${esc(x.c)}</pre>`).join('') : '<p class="muted">이 답에서는 그래프 질의를 쓰지 않았어요.</p>'}
    <h4>③ 근거 그래프 <small class="muted">답에 나온 id와 그 사이 연결</small></h4>
    <div id="evCy" class="ev-cy"></div>
    <h4>④ 도구 호출 순서</h4>${r.steps.map((s, i) => `<div class="small">${i + 1}. <b>${esc(s.tool)}</b> <code>${esc(JSON.stringify(s.input)).slice(0, 160)}</code></div>`).join('')}`;
  $('#drawer').classList.add('on');
  const g = await api('graph/subgraph', { method: 'POST', body: { ids: r.evidence } });
  const cy2 = cytoscape({ container: $('#evCy'), style: CY_STYLE, elements: [
    ...g.nodes.map(n => ({ data: { id: n.id, type: n.type, label: `${n.label}\n(${n.kind})`, flag: flagOf(n.flags) } })),
    ...g.edges.map((e, i) => ({ data: { id: 'x' + i, ...e } }))] });
  cy2.layout({ name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 90, padding: 20 }).run();
}

// ---------------- 객체 보기 (오른쪽 서랍) ----------------
async function openObject(ref, type) {
  const o = await api(`get?ref=${encodeURIComponent(ref)}${type ? '&type=' + type : ''}`);
  $('#drawerBody').innerHTML = objectHtml(o);
  $('#drawer').classList.add('on');
  $$('#drawerBody .ev').forEach(b => b.onclick = () => openObject(b.dataset.id, b.dataset.t));
  $('#drawerBody .tograph')?.addEventListener('click', () => { closeDrawer(); show('graph'); graphMode('data', o.type, o.id); });
}
function closeDrawer() { $('#drawer').classList.remove('on'); }
function objectHtml(o) {
  if (o['오류']) return `<p class="probs">${esc(o['오류'])}</p>`;
  const kv = obj => `<div class="kv">${Object.entries(obj || {}).map(([k, v]) => `<div>${esc(k)}</div><div>${esc(fmt(v))}</div>`).join('')}</div>`;
  const links = Object.entries(o['연결'] || {}).map(([rel, xs]) => `<h4>${esc(rel)}</h4>${xs.map(x => typeof x === 'string' ? `<span class="muted">${esc(x)}</span>` :
    `<button class="ev" data-id="${esc(x.id)}" data-t="${esc(x.type || '')}">${esc(x.id)}${x['이름'] ? ' · ' + esc(x['이름']) : ''}</button>`).join(' ')}`).join('');
  const docs = (o['관련 문서'] || []).map(d => `<div>📄 ${esc(d['날짜'])} ${esc(d['제목'])}</div>`).join('');
  const meas = o['속성']?.['측정값'];
  const props = { ...o['속성'] }; delete props['측정값']; delete props['내용'];
  return `<div class="muted">${esc(o['종류'])} · ${esc(o['ERP 문서'])} · ${esc(o['ERP 상태'])}</div>
    <h3 style="margin:4px 0 10px">${esc(o.id)} ${o['이름'] !== o.id ? '<small class="muted">' + esc(o['이름']) + '</small>' : ''}</h3>
    <button class="tograph">그래프로 보기</button>
    <h4>속성</h4>${kv(props)}
    ${o['속성']?.['내용'] ? `<h4>내용</h4><pre class="code">${esc(o['속성']['내용'])}</pre>` : ''}
    ${meas ? `<h4>측정값</h4>${table(['항목', '값', '하한', '상한', '판정'], meas.map(m => ({ ...m, 하한: m['하한'] < -1e8 ? '' : m['하한'], 상한: m['상한'] > 1e8 ? '' : m['상한'] })))}` : ''}
    ${o['계산 속성'] ? `<h4>계산 속성 <small class="muted">(지금 계산)</small></h4>${kv(o['계산 속성'])}` : ''}
    ${links}${docs ? `<h4>관련 문서</h4>${docs}` : ''}`;
}

// ---------------- 기초 정보: ERP 화면 2개 + 오른쪽 챗봇 ----------------
const ERP_MENU = [
  ['구매', [['material-request', '구매요청'], ['purchase-order', '발주(구매 건)'], ['purchase-receipt', '입고']]],
  ['품질', [['quality-inspection', '검사', 'IQC·출하검사 측정값'], ['non-conformance', '부적합·클레임'], ['quality-inspection-template', '검사 기준']]],
  ['생산', [['work-order', '작업지시'], ['job-card', '작업 기록', '공정·설비·필터 lot'], ['downtime-entry', '정비·중단'], ['nr-production-plan', '생산계획']]],
  ['재고', [['batch', 'lot', '원재료·완제품 lot'], ['stock-entry', '재고 이동'], ['query-report/Stock Balance', '재고 현황'], ['query-report/Batch-Wise Balance History', 'lot별 재고']]],
  ['영업', [['sales-order', '수주'], ['delivery-note', '출하'], ['nr-sales-forecast', '판매 예측']]],
  ['기준정보', [['item', '품목', '원재료·완제품'], ['supplier', '공급사'], ['customer', '고객'], ['nr-customer-approval', '고객 승인'], ['bom', '레시피(BOM)'], ['workstation', '설비'], ['warehouse', '창고']]],
];
const panes = []; let activePane = 0;
function initErp() {
  $('#erpNav').innerHTML = `<div class="nav-tools"><button id="splitBtn">◫ 화면 2개</button></div>` + ERP_MENU.map(([g, items]) => `<h5>${g}</h5>` + items.map(([r, label, sub]) =>
    `<button data-r="${esc(r)}">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ''}</button>`).join('')).join('');
  $$('#erpNav button[data-r]').forEach(b => b.onclick = () => openErp(b.dataset.r));
  $('#splitBtn').onclick = () => panes.length < 2 ? addPane('purchase-receipt') : closePane(1);
  addPane('purchase-order');
}
function label(route) { return $(`#erpNav button[data-r="${route}"]`)?.firstChild?.textContent || route; }
function addPane(route) {
  if (panes.length >= 2) return;
  const el = document.createElement('div'); el.className = 'pane';
  el.innerHTML = `<div class="pane-head"><span class="pt"></span><span class="pane-tools"><a target="_blank" title="새 창">↗</a><button class="pclose" title="닫기">✕</button></span></div><iframe></iframe>`;
  $('#panes').append(el);
  const p = { el, route }; panes.push(p);
  el.addEventListener('mousedown', () => setActive(panes.indexOf(p)), true);
  $('.pclose', el).onclick = e => { e.stopPropagation(); closePane(panes.indexOf(p)); };
  setActive(panes.length - 1); openErp(route);
  $('#splitBtn').textContent = panes.length < 2 ? '◫ 화면 2개' : '▭ 화면 1개';
}
function closePane(i) {
  if (panes.length <= 1) return;
  panes[i].el.remove(); panes.splice(i, 1); setActive(0);
  $('#splitBtn').textContent = '◫ 화면 2개';
}
function setActive(i) { activePane = i; panes.forEach((p, j) => p.el.classList.toggle('active', j === i)); }
function openErp(route) {
  const p = panes[activePane]; if (!p) return;
  const url = '/app/' + route.split('/').map(encodeURIComponent).join('/');
  p.route = route; $('iframe', p.el).src = url; $('a', p.el).href = url; $('.pt', p.el).textContent = label(route);
  $$('#erpNav button[data-r]').forEach(b => b.classList.toggle('on', panes.some(x => x.route === b.dataset.r)));
}
function erpContext() {
  return panes.map((p, i) => {
    let r = [];
    try { r = $('iframe', p.el).contentWindow.frappe.get_route(); } catch (e) { }
    const what = r[0] === 'Form' ? `${r[1]} ${r[2]} (문서)` : r[0] === 'List' ? `${r[1]} 목록` : r[0] === 'query-report' ? `${r[1]} 보고서` : label(p.route);
    return `화면${i + 1}: ${what}`;
  }).join(' / ');
}
let scHistory = [];
$('#scToggle').onclick = () => { $('#sideChat').classList.toggle('min'); $('#scToggle').textContent = $('#sideChat').classList.contains('min') ? '⟨' : '⟩'; };
$('#scQ').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#scForm').requestSubmit(); } });
$$('#sideChat .sug button').forEach(b => b.onclick = () => { $('#scQ').value = b.textContent; $('#scForm').requestSubmit(); });
setInterval(() => { if ($('#tab-erp').classList.contains('on') && panes.length) $('#scCtx').textContent = erpContext(); }, 2000);
$('#scForm').onsubmit = async e => {
  e.preventDefault();
  const question = $('#scQ').value.trim(); if (!question) return; $('#scQ').value = '';
  $('.sc-hello')?.remove();
  addMsg('#scMsgs', 'user', esc(question));
  const box = addMsg('#scMsgs', 'bot', `<div class="live-steps"><span class="spin"></span> 생각하는 중…</div>`);
  try {
    const r = await streamChat({ question, history: scHistory, context: erpContext(), mode: 'ontology', model: $('#model').value }, step => {
      $('.live-steps', box).insertAdjacentHTML('beforeend', stepLine(step)); $('#scMsgs').scrollTop = 1e9;
    });
    scHistory = r.history.slice(-10);
    renderAnswer(box, r, question, true);
  } catch (err) { box.innerHTML = `<span class="probs">오류: ${esc(err.message)}</span>`; }
  $('#scMsgs').scrollTop = 1e9;
};

// ---------------- 그래프 ----------------
let cy = null, gmode = 'schema';
const COLORS = { supplier: '#2f6fde', agency: '#7a8cb3', material: '#2e9e6a', purchase: '#8a6fd1', receipt: '#a18cd6', raw_lot: '#3aa776',
  product: '#1f3a5f', work_order: '#c27c2c', equipment: '#8c8c8c', downtime: '#b5b5b5', filter_lot: '#9a9a9a', fg_lot: '#244a7a',
  inspection: '#d1a93a', ncr: '#d64545', customer: '#d1607a', approval: '#e39bb0', sales_order: '#c9799a', delivery: '#b08ba0', plan: '#b0b8c8',
  event: '#5b6b82', measurement: '#e2c06a' };
const CY_STYLE = [
  { selector: 'node', style: { 'background-color': n => COLORS[n.data('type')] || '#888', label: 'data(label)', 'font-size': 10, color: '#1d2433',
    'text-valign': 'bottom', 'text-margin-y': 4, width: n => n.data('size') || 26, height: n => n.data('size') || 26, 'text-wrap': 'wrap', 'text-max-width': 130 } },
  { selector: 'node[flag="red"]', style: { 'border-width': 4, 'border-color': '#d64545' } },
  { selector: 'node[flag="orange"]', style: { 'border-width': 4, 'border-color': '#e08a1e' } },
  { selector: 'node:selected', style: { 'overlay-color': '#2f6fde', 'overlay-opacity': .15 } },
  { selector: 'edge', style: { width: 1.4, 'line-color': '#c5ccd8', 'target-arrow-color': '#c5ccd8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
    label: 'data(label)', 'font-size': 9, color: '#6b7385', 'text-rotation': 'autorotate', 'text-background-color': '#fff', 'text-background-opacity': .85 } },
  { selector: 'edge[empty="1"]', style: { 'line-style': 'dashed', 'line-color': '#e08a1e', 'target-arrow-color': '#e08a1e', color: '#c27c2c' } },
];
const flagOf = f => (f || []).some(x => x.includes('부적합') || x.includes('불합격')) ? 'red' : (f || []).length ? 'orange' : '';
const SCHEMA_POS = { agency: { x: 100, y: 80 }, supplier: { x: 100, y: 300 }, purchase: { x: 330, y: 190 }, receipt: { x: 560, y: 190 },
  material: { x: 330, y: 440 }, inspection: { x: 790, y: 60 }, measurement: { x: 1020, y: -120 }, raw_lot: { x: 790, y: 300 }, ncr: { x: 1020, y: 60 }, work_order: { x: 1020, y: 300 },
  equipment: { x: 1020, y: 520 }, downtime: { x: 1250, y: 620 }, filter_lot: { x: 790, y: 560 }, product: { x: 560, y: 560 }, approval: { x: 560, y: 760 },
  fg_lot: { x: 1250, y: 300 }, delivery: { x: 1480, y: 160 }, sales_order: { x: 1700, y: 300 }, customer: { x: 1700, y: 560 }, plan: { x: 1480, y: 760 }, event: { x: 100, y: 620 } };
$$('[data-g]').forEach(b => b.onclick = () => graphMode(b.dataset.g));
async function graphMode(m, type, id) {
  gmode = m; $$('[data-g]').forEach(b => b.classList.toggle('on', b.dataset.g === m));
  $('#graphBody').hidden = m === 'cypher'; $('#cypherBox').hidden = m !== 'cypher'; $('#gFind').hidden = m === 'cypher';
  if (m === 'cypher') return initCypher();
  if (cy) cy.destroy();
  cy = cytoscape({ container: $('#cy'), wheelSensitivity: 0.25, style: CY_STYLE });
  cy.on('tap', 'node', e => nodeInfo(e.target.data()));
  cy.on('tap', 'edge', e => e.target.data('schema') && edgeInfo(e.target.data()));
  cy.on('dbltap', 'node', e => { if (gmode === 'data') expand(e.target.data('otype'), e.target.data('oid')); });
  if (m === 'schema') {
    const g = await api('graph/schema');
    const extra = {}; let k = 0;
    cy.add(g.nodes.map(n => ({ data: { id: n.id, type: n.id, label: `${n.label}\n${n.count.toLocaleString()}`, size: 50 + Math.min(40, Math.sqrt(n.count) * 1.5), schema: true },
      position: ((p) => ({ x: p.x * 0.6, y: p.y * 0.6 }))(SCHEMA_POS[n.id] || { x: 100 + (k++) * 120, y: 900 }) })));
    cy.add(g.edges.map((e, i) => ({ data: { id: 'e' + i, source: e.source, target: e.target, label: `${e.label} ${e.count ? e.count.toLocaleString() : '(데이터 없음)'}`,
      rel: e.label, count: e.count, card: e.card, empty: e.count ? '0' : '1', schema: true } })));
    cy.style().selector('node').style({ 'font-size': 20, 'text-max-width': 200 }).selector('edge').style({ 'font-size': 13, width: 2.5 }).update();
    cy.layout({ name: 'preset', padding: 30 }).run();
    $('#gSide').innerHTML = `<h4 style="margin-top:0">설계도 v${esc(g.version)}</h4><p class="muted">온톨로지 정의 파일의 단어(노드)와 관계문(화살표)을 그대로 그립니다. 숫자는 실제 데이터 수입니다.
      주황 점선은 정의는 있는데 아직 데이터가 없는 관계문이에요.</p><div class="kv"><div>그래프 DB</div><div>노드 ${(g.graph.노드 || 0).toLocaleString()} · 관계 ${(g.graph.관계 || 0).toLocaleString()}</div></div>
      <p><button onclick="show('onto'); ontoMode('rels')">관계문 고치기</button></p>`;
  } else if (type && id) { expand(type, id); }
  else { $('#gSide').innerHTML = '<p class="muted">위에서 객체를 찾아 시작하세요. 예: PL-260731-K03-01, 한빛폴리텍, RS-05</p>'; }
}
async function expand(type, id) {
  const g = await api(`graph/node?type=${type}&id=${encodeURIComponent(id)}`);
  const add = [];
  for (const n of g.nodes) if (!cy.getElementById(n.id).length) add.push({ data: { id: n.id, type: n.type, otype: n.type, oid: n.id.split('|').slice(1).join('|'),
    label: `${n.label}\n(${n.kind})`, flag: flagOf(n.flags) } });
  for (const e of g.edges) { const eid = e.source + '>' + e.target + e.label; if (!cy.getElementById(eid).length) add.push({ data: { id: eid, ...e } }); }
  cy.add(add);
  const focus = `${type}|${id}`;
  cy.layout({ name: 'concentric', animate: false, padding: 40, minNodeSpacing: 70, avoidOverlap: true,
    concentric: n => n.id() === focus ? 3 : n.neighborhood(`node[id = "${focus}"]`).length ? 2 : 1, levelWidth: () => 1 }).run();
  if (cy.zoom() > 1.1) { cy.zoom(1.1); cy.center(); }
  cy.getElementById(focus).select();
  nodeInfo({ otype: type, oid: id });
}
async function nodeInfo(d) {
  if (d.schema) {
    const m = await api('onto/model'); const t = m.terms.find(x => x.key === d.id);
    if (!t) { $('#gSide').innerHTML = `<h3>측정값</h3><p class="muted">검사 1건의 항목별 측정값(순도·수분·금속 26종…). 그래프 DB에서 measurement 노드예요.</p>`; return; }
    const props = m.props.filter(p => p.subject === d.id);
    const rels = m.links.filter(l => l.subject === d.id || l.to.includes(d.id));
    $('#gSide').innerHTML = `<h3 style="margin-top:0">${esc(t.name)} <small class="muted">${t.key}</small></h3><p>${esc(t.description)}</p>
      <div class="kv"><div>객체 수</div><div>${t.count.toLocaleString()}</div><div>현업 별칭</div><div>${esc(t.aliases.join(', '))}</div><div>ERP 출처</div><div>${esc(t.source)}</div></div>
      <h4>관계문</h4>${rels.map(l => `<div class="small">${esc(nameOf(m, l.subject))} —${esc(l.rel)}→ ${l.to.map(x => esc(nameOf(m, x))).join('·')} <span class="muted">${l.count.toLocaleString()}</span></div>`).join('')}
      <h4>속성 ${props.length}</h4><div class="small">${props.map(p => esc(p.name)).join(', ')}</div>
      <p><button onclick="show('onto'); ontoMode('terms')">단어 정의 고치기</button></p>`;
    return;
  }
  const o = await api(`get?ref=${encodeURIComponent(d.oid)}&type=${d.otype}`);
  $('#gSide').innerHTML = objectHtml(o) + '<p class="muted">더블클릭하면 이 노드의 연결을 펼칩니다.</p>';
  $$('#gSide .ev').forEach(b => b.onclick = async () => { let t = b.dataset.t; if (!t) { const f = await api('find?q=' + encodeURIComponent(b.dataset.id)); t = f[0]?.type; } if (t) expand(t, b.dataset.id); });
  $('#gSide .tograph')?.remove();
}
function edgeInfo(d) {
  $('#gSide').innerHTML = `<h4 style="margin-top:0">관계문</h4><p><b>${esc(d.source)}</b> —${esc(d.rel)}→ <b>${esc(d.target)}</b></p>
    <div class="kv"><div>개수</div><div>${esc(d.card)}</div><div>실제 연결</div><div>${(d.count || 0).toLocaleString()}</div></div>
    <p><button onclick="show('onto'); ontoMode('rels')">관계문 고치기</button></p>`;
}
const nameOf = (m, k) => m.terms.find(t => t.key === k)?.name || k;
$('#gFind').onsubmit = async e => {
  e.preventDefault();
  const r = await api('find?q=' + encodeURIComponent($('#gQ').value));
  if (!r.length || !r[0].id) return toast('찾지 못했습니다');
  if (gmode !== 'data') await graphMode('data');
  expand(r[0].type, r[0].id);
};
async function initCypher() {
  const p = await api('chat/prompt');
  $('#cySchema').textContent = p.system.split('그래프 스키마 (그래프 DB, Cypher)')[1] || '';
  loadCyLog();
}
async function loadCyLog() {
  const rows = await api('graph/log?n=40');
  $('#cyLog').innerHTML = '<tr><th>시각</th><th>누가</th><th>질의</th><th>행</th><th>ms</th></tr>' +
    rows.map(r => `<tr><td>${r.at}</td><td>${esc(r.who)}</td><td style="white-space:pre-wrap;font-family:monospace;font-size:11.5px">${esc(r.cypher)}</td><td>${r.rows}</td><td>${r.ms}</td></tr>`).join('');
}
$('#cyRun').onclick = async () => {
  $('#cyInfo').textContent = '실행 중…';
  try {
    const r = await api('graph/query', { method: 'POST', body: { cypher: $('#cyQ').value } });
    if (r['오류']) { $('#cyOut').innerHTML = `<p class="probs">${esc(r['오류'])}</p>`; $('#cyInfo').textContent = ''; return; }
    const rows = r['결과'], cols = rows.length ? Object.keys(rows[0]) : [];
    $('#cyOut').innerHTML = table(cols, rows, 200); $('#cyInfo').textContent = `${r['행 수']}행`;
  } catch (e) { $('#cyOut').innerHTML = `<p class="probs">${esc(e.message)}</p>`; }
  loadCyLog();
};

// ---------------- 온톨로지 ----------------
let OM = null, fieldsCache = {};
$$('[data-o]').forEach(b => b.onclick = () => ontoMode(b.dataset.o));
async function fieldsOf(doctype) {
  if (!doctype) return [];
  if (!fieldsCache[doctype]) fieldsCache[doctype] = await api('erp/fields?doctype=' + encodeURIComponent(doctype)).catch(() => []);
  return fieldsCache[doctype];
}
async function ontoOp(op, after) {
  const r = await api('onto/op', { method: 'POST', body: op });
  if (r.ok) { toast(`저장됨 v${r.version} — 객체·그래프 DB에 바로 반영`); loaded.graph = false; }
  else toast('저장 안 됨: ' + (r.problems || []).join(' / '), 6000);
  if (r.ok || after === 'always') ontoMode(after && after !== 'always' ? after : curOnto);
  return r;
}
let curOnto = 'terms';
async function ontoMode(m) {
  curOnto = m;
  $$('[data-o]').forEach(b => b.classList.toggle('on', b.dataset.o === m));
  OM = await api('onto/model');
  $('#ontoVer').textContent = 'v' + OM.version;
  $('#ontoInfo').textContent = `단어 ${OM.terms.length}개 · 관계문 ${OM.links.length}개 · 속성 ${OM.props.length}개 · 규칙 ${OM.rules.length}개`;
  const body = $('#ontoBody');
  if (m === 'terms') return renderTerms(body);
  if (m === 'rels') return renderRels(body);
  if (m === 'hist') return renderHist(body);
  if (m === 'yaml') return renderYaml(body);
}
function renderTerms(body) {
  body.innerHTML = `<p class="lead">회사에서 쓰는 <b>단어</b>를 정의합니다. 이름·현업 별칭·뜻을 고치면 AI가 그 말로 알아듣고, 그래프 노드 이름도 바뀌어요.</p>
    <details class="addbox"><summary>＋ 새 단어 추가</summary>
      <div class="form-grid"><label>이름<input id="ntName" placeholder="예: 견적"></label><label>id (영문)<input id="ntKey" placeholder="예: quotation"></label>
      <label>ERP 화면<select id="ntDt"></select></label><label>조건(선택)<input id="ntFilter" placeholder="예: status = Open"></label>
      <label class="wide">별칭(쉼표)<input id="ntAl" placeholder="예: RFQ, 견적서"></label><label class="wide">뜻<input id="ntDesc"></label></div>
      <button class="primary" id="ntAdd">추가</button></details>
    <div class="terms">${OM.terms.map(t => `<div class="term" data-k="${t.key}">
      <div class="term-head"><input class="tname" value="${esc(t.name)}"><code>${t.key}</code><span class="chip">${t.count.toLocaleString()}개</span></div>
      <label>현업 별칭<input class="tal" value="${esc(t.aliases.join(', '))}"></label>
      <label>뜻<textarea class="tdesc" rows="2">${esc(t.description)}</textarea></label>
      <div class="small muted">ERP 출처: ${esc(t.source)}${t.filter ? ' · 조건: ' + esc(t.filter) : ''}${t.computed.length ? ' · 계산 속성: ' + esc(t.computed.join(', ')) : ''}</div>
      <div class="term-tools"><button class="tsave primary">저장</button><button class="tdel">삭제</button></div></div>`).join('')}</div>`;
  api('erp/doctypes').then(ds => $('#ntDt').innerHTML = ds.map(d => `<option>${esc(d)}</option>`).join(''));
  $('#ntAdd').onclick = () => ontoOp({ op: 'term.add', key: $('#ntKey').value.trim(), name: $('#ntName').value.trim(), doctype: $('#ntDt').value,
    filter: $('#ntFilter').value.trim(), aliases: $('#ntAl').value.split(',').map(s => s.trim()).filter(Boolean), description: $('#ntDesc').value });
  $$('.term').forEach(el => {
    const k = el.dataset.k;
    $('.tsave', el).onclick = () => ontoOp({ op: 'term.update', key: k, name: $('.tname', el).value.trim(), description: $('.tdesc', el).value,
      aliases: $('.tal', el).value.split(',').map(s => s.trim()).filter(Boolean) });
    $('.tdel', el).onclick = async () => {
      if (!confirm(`'${$('.tname', el).value}' 단어를 지울까요? 이 단어를 쓰는 관계문도 함께 지워집니다.`)) return;
      ontoOp({ op: 'term.remove', key: k, force: true });
    };
  });
}
function termOptions(sel, multi) {
  return OM.terms.map(t => `<option value="${t.key}" ${(multi ? sel.includes(t.key) : sel === t.key) ? 'selected' : ''}>${esc(t.name)}</option>`).join('');
}
// 개수: 주어 1개당 상대가 몇 개인가
const CARD_OPTS = [['1', '꼭 1개'], ['0..1', '없거나 1개'], ['N', '여러 개']];
const cardGroup = c => ({ '1': '1', 'N..1': '1', '0..1': '0..1' }[c] || 'N');
// 받침에 맞춰 조사 고르기: 공급사를 / 원재료 lot을 / 구매 건은
function hasBatchim(word) {
  const ch = String(word).trim().slice(-1);
  const code = ch.charCodeAt(0);
  if (code >= 0xAC00 && code <= 0xD7A3) return (code - 0xAC00) % 28 !== 0;
  return /[bcdfgjklmnpqrstvxz0-9]$/i.test(ch);
}
function josa(word, pair) {
  const [a, b] = { '을(를)': ['을', '를'], '이(가)': ['이', '가'], '은(는)': ['은', '는'], '와(과)': ['과', '와'], '으로(로)': ['으로', '로'] }[pair] || [pair, pair];
  return hasBatchim(word) ? a : b;
}
function sentenceTail(target, phrase) {  // "을(를) 경유한다" → "를 경유한다"
  const m = /^(을\(를\)|이\(가\)|은\(는\)|와\(과\)|으로\(로\))(.*)$/.exec(phrase || '');
  return m ? josa(target, m[1]) + m[2] : (phrase || '');
}
function renderRels(body) {
  const subj = body.dataset.subj || '';
  const links = OM.links.filter(l => !subj || l.subject === subj || l.to.includes(subj));
  const props = OM.props.filter(p => !subj || p.subject === subj);
  body.innerHTML = `<p class="lead"><b>관계문</b>은 온톨로지의 뼈대예요. "구매 건은 공급사에 발주한다"처럼 <b>주어 + 대상 + 동사</b> 문장으로 씁니다. '1개당'은 주어 하나에 대상이 몇 개 붙는지예요(구매 건 1개당 공급사는 꼭 1개). 고치면 그래프 DB와 AI가 바로 바뀌어요.</p>
    <div class="relbar">단어로 좁히기 <select id="relSubj"><option value="">전체</option>${termOptions(subj)}</select></div>
    <h4>연결 관계문 <small class="muted">${links.length}개</small></h4>
    <div class="stmts">${links.map(l => { const sn = nameOf(OM, l.subject), tn = l.to.includes('*') ? '모든 단어' : l.to.map(x => nameOf(OM, x)).join('·');
      return `<div class="stmt rel" data-s="${l.subject}" data-i="${l.index}" data-card="${esc(l.card)}">
      <div class="sentence"><span class="w">${esc(sn)}</span>${josa(sn, '은(는)')}
      <select class="lto" ${l.to.length > 1 ? 'multiple size="2"' : ''}>${l.to.includes('*') ? '<option value="*" selected>모든 단어</option>' : ''}${termOptions(l.to, true)}</select><span class="tail">${esc(sentenceTail(tn, l.phrase))}</span></div>
      <div class="detail">
        <label>동사<input class="lphrase" value="${esc(l.phrase)}" placeholder="예: 을(를) 경유한다"></label>
        <label>${esc(sn)} 1개당 <select class="lcard">${CARD_OPTS.map(([v, t]) => `<option value="${v}" ${v === cardGroup(l.card) ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        <label>관계 이름<input class="lrel" value="${esc(l.rel)}"></label>
        <label>ERP 근거<input class="lvia" value="${esc(l.via)}"></label>
        <span class="cnt ${l.count ? '' : 'zero'}">${l.count ? l.count.toLocaleString() + '개 연결' : '데이터 없음'}</span>
        <button class="lsave">저장</button><button class="ldel">삭제</button></div></div>`; }).join('')}
    </div>
    <details class="addbox"><summary>＋ 연결 관계문 추가</summary>
      <div class="stmt"><select id="nlS">${termOptions(subj)}</select>은(는) <select id="nlT">${termOptions('')}</select>
      <input id="nlPhrase" placeholder="동사 예: 을(를) 납품한다"> · 1개당 <select id="nlCard">${CARD_OPTS.map(([v, t]) => `<option value="${v}">${t}</option>`).join('')}</select>
      · 관계 이름 <input id="nlRel" placeholder="예: 납품" style="width:90px"> · ERP 근거 <select id="nlVia"></select><button class="primary" id="nlAdd">추가</button></div>
      <p class="muted small">ERP 근거는 주어 단어의 ERP 화면에서 상대를 가리키는 칸이에요. 하위 표 칸은 '하위표.칸' 형식이에요.</p></details>
    <h4>속성 관계문 <small class="muted">${props.length}개</small></h4>
    <div class="stmts">${props.map(p => `<div class="stmt prop" data-s="${p.subject}" data-n="${esc(p.name)}">
      <span class="w">${esc(nameOf(OM, p.subject))}</span>${josa(nameOf(OM, p.subject), '은(는)')} <input class="pname" value="${esc(p.name)}"> 속성을 가진다
      <span class="muted small">ERP 칸</span><input class="pfield" value="${esc(p.field)}">
      <span class="cnt ${p.filled ? '' : 'zero'}">${p.filled ? p.filled.toLocaleString() + '개 값' : '값 없음'}</span>
      <button class="psave">저장</button><button class="pdel">삭제</button></div>`).join('')}</div>
    <details class="addbox"><summary>＋ 속성 관계문 추가</summary>
      <div class="stmt"><select id="npS">${termOptions(subj)}</select>은(는) <input id="npName" placeholder="속성 이름 예: 원산지"> 속성을 가진다
      <span class="muted small">ERP 칸</span><select id="npField"></select><button class="primary" id="npAdd">추가</button></div></details>
    <h4>규칙문 <small class="muted">조건 → 판단 → 다음 행동, 숫자는 바로 고칠 수 있어요</small></h4>
    <table class="grid rules"><tr><th>규칙</th><th>조건</th><th>판단 → 다음 행동</th><th>숫자</th></tr>${OM.rules.map(r => `<tr><td><b>${esc(r.id)}</b></td><td>${esc(r.when)}</td>
      <td>${esc(r.then)} → ${esc(r.next)}</td><td>${Object.entries(r.params).map(([k, v]) => `<label class="pp">${esc(k)}<input class="param" data-path="rules.${r.id}.params.${k}" data-v="${esc(v)}" value="${esc(v)}"></label>`).join('') || '<span class="muted">—</span>'}</td></tr>`).join('')}</table>
    <p><button class="primary" id="saveParams">규칙 숫자 저장</button></p>`;
  $('#relSubj').onchange = e => { body.dataset.subj = e.target.value; renderRels(body); };
  const srcOf = k => OM.terms.find(t => t.key === k)?.source?.split(',')[0]?.trim();
  const fillFields = async (selS, selF, linkOnly) => {
    const fs = await fieldsOf(srcOf($(selS).value));
    $(selF).innerHTML = fs.filter(f => !linkOnly || f.link || f.type === 'Link' || f.type === 'Dynamic Link' || f.type === 'Data').map(f =>
      `<option value="${esc(f.field)}">${esc(f.label)} (${esc(f.field)})${f.link ? ' → ' + esc(f.link) : ''}</option>`).join('');
  };
  $('#nlS').onchange = () => fillFields('#nlS', '#nlVia', true); fillFields('#nlS', '#nlVia', true);
  $('#npS').onchange = () => fillFields('#npS', '#npField', false); fillFields('#npS', '#npField', false);
  $('#nlAdd').onclick = () => ontoOp({ op: 'link.add', subject: $('#nlS').value, to: $('#nlT').value, rel: $('#nlRel').value.trim() || $('#nlPhrase').value.replace(/^\S*\)\s*/, '').replace(/한다$|다$/, '').trim(),
    phrase: $('#nlPhrase').value.trim(), card: $('#nlCard').value, via: $('#nlVia').value });
  $('#npAdd').onclick = () => ontoOp({ op: 'prop.add', subject: $('#npS').value, name: $('#npName').value.trim(), field: $('#npField').value });
  $$('.stmt.rel').forEach(el => el.querySelector('.lto').addEventListener('change', () => {  // 대상이 바뀌면 조사도 다시
    const tn = [...el.querySelector('.lto').selectedOptions].map(o => o.textContent).join('·');
    el.querySelector('.tail').textContent = sentenceTail(tn, el.querySelector('.lphrase').value); }));
  $$('.stmt.rel .lphrase').forEach(i => i.addEventListener('input', () => { const el = i.closest('.stmt');
    const tn = [...el.querySelector('.lto').selectedOptions].map(o => o.textContent).join('·'); el.querySelector('.tail').textContent = sentenceTail(tn, i.value); }));
  $$('.stmt[data-i]').forEach(el => {
    const base = { subject: el.dataset.s, index: +el.dataset.i };
    $('.lsave', el).onclick = () => { const cg = $('.lcard', el).value, orig = el.dataset.card;
      ontoOp({ op: 'link.update', ...base, rel: $('.lrel', el).value.trim(), phrase: $('.lphrase', el).value.trim(), via: $('.lvia', el).value.trim(),
        card: cg === cardGroup(orig) ? orig : cg, to: [...$('.lto', el).selectedOptions].map(o => o.value) }); };
    $('.ldel', el).onclick = () => confirm('이 관계문을 지울까요?') && ontoOp({ op: 'link.remove', ...base });
  });
  $$('.stmt.prop').forEach(el => {
    const base = { subject: el.dataset.s, name: el.dataset.n };
    $('.psave', el).onclick = () => ontoOp({ op: 'prop.update', ...base, new_name: $('.pname', el).value.trim(), field: $('.pfield', el).value.trim() });
    $('.pdel', el).onclick = () => confirm('이 속성을 지울까요?') && ontoOp({ op: 'prop.remove', ...base });
  });
  $('#saveParams').onclick = async () => {
    const changed = $$('.param').filter(i => i.dataset.v !== i.value);
    if (!changed.length) return toast('바뀐 숫자가 없습니다');
    let r;
    for (const i of changed) r = await api('onto/patch', { method: 'POST', body: { path: i.dataset.path, value: isNaN(+i.value) ? i.value : +i.value } });
    r?.ok ? toast(`저장됨 v${r.version} — 판정에 바로 반영`) : toast('저장 안 됨: ' + (r?.problems || []).join(' / '), 5000);
    ontoMode('rels');
  };
}
async function renderHist(body) {
  const vs = await api('onto/versions');
  body.innerHTML = `<p class="lead">모든 수정은 버전으로 남고, 언제든 되돌릴 수 있어요(되돌리기도 새 버전으로 저장).</p>` + vs.map((v, i) => `<div class="ver"><b>v${esc(v.version)}</b> <span class="muted">${esc(v.at)} · ${esc(v.author)}</span> ${esc(v.reason || '')}
    ${i > 0 ? `<button data-rb="${esc(v.version)}" style="float:right">이 버전으로 되돌리기</button>` : '<span class="chip" style="float:right">현재</span>'}
    <div class="changes">${v.changes.slice(0, 30).map(c => `<div><code>${esc(c.path)}</code> <span class="before">${esc(fmt(c.before))}</span> → <span class="after">${esc(fmt(c.after))}</span></div>`).join('')}</div></div>`).join('');
  $$('[data-rb]').forEach(b => b.onclick = async () => {
    if (!confirm(`v${b.dataset.rb}로 되돌릴까요?`)) return;
    const r = await api('onto/rollback', { method: 'POST', body: { version: b.dataset.rb } });
    r.ok ? toast(`v${r.version}로 저장(되돌림)`) : toast('실패: ' + (r.problems || []).join(' / ')); loaded.graph = false; ontoMode('hist');
  });
}
async function renderYaml(body) {
  const o = await api('onto');
  body.innerHTML = `<p class="lead">정의 파일(ontology.yaml) 전체. 단어·관계문 화면으로 안 되는 큰 수정만 여기서 하세요.</p>
    <textarea class="yaml" id="yamlText" spellcheck="false">${esc(o.yaml)}</textarea>
    <p><input id="reason" placeholder="수정 이유" style="width:420px"> <button id="chkYaml">검증</button> <button class="primary" id="saveYaml">저장</button></p><div id="yamlRes"></div>`;
  const res = r => (r.problems?.length ? `<div class="probs">${r.problems.map(esc).join('<br>')}</div>` : '<div style="color:var(--green)">문제 없음</div>') +
    (r.changes?.length ? `<div class="changes"><b>바뀌는 내용</b>${r.changes.map(c => `<div><code>${esc(c.path)}</code> <span class="before">${esc(fmt(c.before))}</span> → <span class="after">${esc(fmt(c.after))}</span></div>`).join('')}</div>` : '');
  $('#chkYaml').onclick = async () => $('#yamlRes').innerHTML = res(await api('onto/check', { method: 'POST', body: { yaml: $('#yamlText').value } }));
  $('#saveYaml').onclick = async () => { const r = await api('onto/save', { method: 'POST', body: { yaml: $('#yamlText').value, reason: $('#reason').value } }); if (r.ok) { toast('저장됨 v' + r.version); loaded.graph = false; ontoMode('yaml'); } else $('#yamlRes').innerHTML = res(r); };
}

// ---------------- 동기화 화면 ----------------
async function loadSync() { renderSync(await api('sync')); }
function renderSync(s) {
  const n = Object.values(s.objects).reduce((a, b) => a + b, 0);
  $('#syncInfo').innerHTML = `<div class="kv"><div>ERP 주소</div><div>${esc(s.erp)}</div><div>기준일</div><div>${esc(s.as_of)}</div>
    <div>객체 / 연결</div><div>${n.toLocaleString()} / ${s.links.toLocaleString()}</div>
    <div>그래프 DB</div><div>LadybugDB · 노드 ${(s.graph?.노드 || 0).toLocaleString()} · 관계 ${(s.graph?.관계 || 0).toLocaleString()} · 적재 ${s.graph?.['적재(초)'] ?? '-'}초</div>
    <div>마지막 갱신</div><div>${esc(s.last?.at)} (${esc(s.last?.kind)})</div>
    <div>변경분 확인</div><div>${s.poll_sec}초마다 · 마지막 ${esc(s.last_poll || '—')}</div>${s.error ? `<div>오류</div><div class="probs">${esc(s.error)}</div>` : ''}</div>`;
  $('#syncCounts').innerHTML = '<tr><th>객체</th><th>수</th></tr>' + Object.entries(s.objects).map(([k, v]) => `<tr><td>${k}</td><td>${v.toLocaleString()}</td></tr>`).join('');
  $('#syncLog').innerHTML = '<tr><th>시각</th><th>종류</th><th>문서</th><th>바뀐 객체</th><th>내용</th></tr>' +
    s.log.map(l => `<tr><td>${l.at}</td><td>${esc(l.kind)}</td><td>${esc(l.doctype)} ${esc(l.name)}</td><td>${l.changed}</td><td style="white-space:normal">${esc(l.detail)}</td></tr>`).join('');
  $('#hookUrl').textContent = 'http://host.docker.internal:8501/ow/webhook';
}
$('#fullSync').onclick = async () => { $('#fullSync').disabled = true; await api('sync/full', { method: 'POST' }); $('#fullSync').disabled = false; loadSync(); toast('전체 동기화 완료'); };
