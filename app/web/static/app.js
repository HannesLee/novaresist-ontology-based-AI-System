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
const toast = (t, ms = 2500) => { const d = document.createElement('div'); d.className = 'toast'; d.textContent = t; document.body.append(d); setTimeout(() => d.remove(), ms); };
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
  if (tab === 'erp' && !$('#erpFrame').src) $('#erpFrame').src = $('#erpFrame').dataset.src;
  if (!loaded[tab]) { loaded[tab] = true; ({ board: loadBoard, graph: () => graphMode('schema'), onto: () => ontoMode('rules'), sync: loadSync, compare: loadCmpLog })[tab]?.(); }
  if (tab === 'sync') loadSync();
}
$$('#nav button').forEach(b => b.onclick = () => show(b.dataset.tab));
$('#syncPill').onclick = () => show('sync');

// ---------------- 동기화 상태 ----------------
let lastSyncAt = null;
async function pollStatus() {
  try {
    const s = await api('sync');
    const n = Object.values(s.objects).reduce((a, b) => a + b, 0);
    $('.dot').className = 'dot ' + (s.error ? 'err' : 'live');
    const at = s.last?.at || '';
    $('#syncText').textContent = s.error ? 'ERP 연결 문제' : `실시간 · 객체 ${n.toLocaleString()} · 갱신 ${at.slice(11, 19)}`;
    if (lastSyncAt && at !== lastSyncAt && s.last?.changed?.length) {
      $('#syncPill').classList.remove('flash'); void $('#syncPill').offsetWidth; $('#syncPill').classList.add('flash');
      toast(`ERP 변경 반영: ${s.last.changed.slice(0, 3).map(c => c[1]).join(', ')}${s.last.changed.length > 3 ? ' 외' : ''}`);
    }
    lastSyncAt = at;
    if ($('#tab-sync').classList.contains('on')) renderSync(s);
  } catch (e) { $('.dot').className = 'dot err'; $('#syncText').textContent = '서버 연결 끊김'; }
}
setInterval(pollStatus, 5000); pollStatus();

// ---------------- 챗봇 ----------------
let history = [];
const q = $('#q');
q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#askForm').requestSubmit(); } });
q.addEventListener('input', () => { q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 160) + 'px'; });
$$('.examples button').forEach(b => b.onclick = () => { q.value = b.textContent; $('#askForm').requestSubmit(); });

$('#askForm').onsubmit = async e => {
  e.preventDefault();
  const question = q.value.trim(); if (!question) return;
  q.value = ''; q.style.height = 'auto';
  $('.hello')?.remove();
  addMsg('user', esc(question));
  const box = addMsg('bot', `<div class="live-steps"><span class="spin"></span> 생각하는 중…</div>`);
  const btn = $('#askForm button'); btn.disabled = true;
  try {
    const r = await streamChat({ question, mode: $('#mode').value, history }, step => {
      $('.live-steps', box).insertAdjacentHTML('beforeend', `<div>${esc(step.tool)} ${esc(JSON.stringify(step.input)).slice(0, 120)} <small>${step.ms}ms</small></div>`);
      box.parentElement.scrollIntoView({ block: 'end' });
    });
    history = r.history.slice(-12);
    renderAnswer(box, r, question);
  } catch (err) { box.innerHTML = `<span class="probs">오류: ${esc(err.message)}</span>`; }
  btn.disabled = false;
};

function addMsg(who, html) {
  const m = document.createElement('div'); m.className = 'msg ' + who;
  m.innerHTML = `<div class="bubble">${html}</div>`;
  $('#msgs').append(m); m.scrollIntoView({ block: 'end' });
  return $('.bubble', m);
}

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

function renderAnswer(box, r, question) {
  const u = r.usage || {};
  box.innerHTML = `${md(r.answer)}
    <div class="meta">${r.mode === 'erp' ? '<span class="chip">ERP만</span>' : ''}
      <span>${r.seconds}초 · 도구 ${r.steps.length}번 · 토큰 ${((u.input || 0) + (u.output || 0)).toLocaleString()}</span>
      <span class="exp">
        <button data-f="xlsx">엑셀</button><button data-f="pptx">PPT</button><button data-f="docx">워드</button>
      </span></div>
    ${r.evidence.length ? `<div class="meta">근거 ${r.evidence.map(x => `<button class="ev">${esc(x)}</button>`).join('')}</div>` : ''}
    ${r.unverified?.length ? `<div class="meta">도구 결과에 없는 번호(확인 필요): ${r.unverified.map(esc).join(', ')}</div>` : ''}
    <details class="steps"><summary>사용한 함수 ${r.steps.length}개 보기</summary>${r.steps.map(s =>
      `<div class="step"><b>${esc(s.tool)}</b> <code>${esc(JSON.stringify(s.input))}</code> <small>${s.ms}ms</small><pre>${esc(s.output)}</pre></div>`).join('')}</details>`;
  $$('.ev', box).forEach(b => b.onclick = () => openObject(b.textContent));
  $$('.exp button', box).forEach(b => b.onclick = () => download(b.dataset.f, { answer: r, question }));
}

async function download(fmt, body) {
  toast('파일 만드는 중…', 1500);
  const r = await fetch('/ow/api/export/' + fmt, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) return toast('내보내기 실패');
  const cd = r.headers.get('Content-Disposition') || '';
  const name = decodeURIComponent((/filename\*=UTF-8''(.+)/.exec(cd) || [])[1] || 'ontwin.' + fmt);
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = name; a.click();
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
  const props = { ...o['속성'] }; delete props['측정값'];
  return `<div class="muted">${esc(o['종류'])} · ${esc(o['ERP 문서'])} · ${esc(o['ERP 상태'])}</div>
    <h3 style="margin:4px 0 10px">${esc(o.id)} ${o['이름'] !== o.id ? '<small class="muted">' + esc(o['이름']) + '</small>' : ''}</h3>
    <button class="tograph">그래프로 보기</button>
    <h4>속성</h4>${kv(props)}
    ${meas ? `<h4>측정값</h4>${table(['항목', '값', '하한', '상한', '판정'], meas.map(m => ({ ...m, 하한: m['하한'] < -1e8 ? '' : m['하한'], 상한: m['상한'] > 1e8 ? '' : m['상한'] })))}` : ''}
    ${o['계산 속성'] ? `<h4>계산 속성 <small class="muted">(지금 계산)</small></h4>${kv(o['계산 속성'])}` : ''}
    ${links}${docs ? `<h4>관련 문서</h4>${docs}` : ''}`;
}

// ---------------- 작업대 ----------------
let sources = null; const selected = new Set();
async function loadBoard() {
  sources = sources || await api('board/sources');
  fillCardTypes();
  const cards = await api('board/cards');
  $('#cards').innerHTML = cards.length ? '' : '<p class="muted">카드가 없습니다. 위에서 데이터를 골라 올려 보세요. 예: 온톨로지 객체 → 구매 건, 원재료</p>';
  for (const c of cards) renderCard(await api('board/card/' + c.id));
}
function fillCardTypes() {
  const src = $('#cardSource').value;
  $('#cardType').innerHTML = src === 'onto' ? sources.onto.map(t => `<option value="${t.type}">${esc(t.name)}</option>`).join('')
    : sources.erp.map(d => `<option>${esc(d)}</option>`).join('');
}
$('#cardSource').onchange = fillCardTypes;
$('#addCard').onclick = async () => {
  const src = $('#cardSource').value, t = $('#cardType').value;
  const body = src === 'onto' ? { source: 'onto', type: t } : { source: 'erp', doctype: t };
  if ($('#cardTitle').value.trim()) body.title = $('#cardTitle').value.trim();
  $('#addCard').disabled = true;
  try { const c = await api('board/card', { method: 'POST', body }); if ($('#cards p')) $('#cards').innerHTML = ''; renderCard(c); $('#cardTitle').value = ''; }
  catch (e) { toast('카드를 만들지 못했습니다: ' + e.message, 4000); }
  $('#addCard').disabled = false;
};
function renderCard(c, replace) {
  const el = replace || document.createElement('div');
  el.className = 'card' + (c.source === 'result' ? ' result' : '') + (selected.has(c.id) ? ' sel' : '');
  el.dataset.id = c.id;
  const srcTxt = c.source === 'onto' ? '온톨로지 · ' + (sources?.onto.find(t => t.type === c.type)?.name || c.type)
    : c.source === 'erp' ? 'ERP · ' + c.doctype : '만든 자료 · ' + esc(c.request || '');
  el.innerHTML = `<h4>${esc(c.title)} <span class="tools">
      <button data-a="refresh" title="ERP 최신값으로 다시">⟳</button>
      <button data-a="xlsx">엑셀</button><button data-a="pptx">PPT</button><button data-a="docx">워드</button><button data-a="csv">CSV</button>
      <button data-a="del" title="삭제">✕</button></span></h4>
    <div class="sub">${srcTxt} · ${c.total ?? 0}행 ${c.at ? '· ' + c.at : ''}</div>
    ${c.error ? `<div class="probs">${esc(c.error)}</div>` : ''}
    ${c.note ? `<div class="sub">${esc(c.note)}</div>` : ''}
    ${c.chart ? '<div class="chart"></div>' : ''}
    <div class="tbl">${table(c.columns || [], c.rows || [], 200)}</div>
    ${c.code ? `<details><summary class="muted" style="font-size:12px">계산 코드</summary><pre class="code">${esc(c.code)}</pre></details>` : ''}`;
  if (!replace) $('#cards').append(el);
  el.onclick = e => {
    const a = e.target.dataset?.a;
    if (a === 'del') { api('board/card/' + c.id, { method: 'DELETE' }); selected.delete(c.id); el.remove(); updSel(); return; }
    if (a === 'refresh') { api(`board/card/${c.id}?refresh=1`).then(n => renderCard(n, el)); return; }
    if (a) { download(a, { card: c.id }); return; }
    if (e.target.closest('.tbl, details')) return;
    selected.has(c.id) ? selected.delete(c.id) : selected.add(c.id);
    el.classList.toggle('sel'); updSel();
  };
  if (c.chart) drawChart($('.chart', el), c);
}
function updSel() { $('#selCount').textContent = '선택 ' + selected.size; }
function drawChart(el, c) {
  const ch = c.chart, ys = Array.isArray(ch.y) ? ch.y : [ch.y];
  const rows = (c.rows || []).slice(0, 40);
  const chart = echarts.init(el);
  if (ch.type === 'pie') chart.setOption({ tooltip: {}, series: [{ type: 'pie', radius: '65%', data: rows.map(r => ({ name: r[ch.x], value: r[ys[0]] })) }] });
  else chart.setOption({
    tooltip: { trigger: 'axis' }, legend: { show: ys.length > 1, bottom: 0 }, grid: { left: 50, right: 16, top: 24, bottom: ys.length > 1 ? 70 : 50 },
    xAxis: { type: 'category', data: rows.map(r => r[ch.x]), axisLabel: { rotate: 30, fontSize: 10 } }, yAxis: { type: 'value' },
    series: ys.map(y => ({ name: y, type: ch.type === 'line' ? 'line' : 'bar', data: rows.map(r => r[y]) })),
    color: ['#1f3a5f', '#2f6fde', '#e08a1e', '#2e9e6a', '#d64545'],
  });
}
$('#makeForm').onsubmit = async e => {
  e.preventDefault();
  if (selected.size < 1) return toast('카드를 먼저 고르세요');
  const req = $('#makeReq').value.trim(); if (!req) return;
  const btn = $('#makeForm button'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 만드는 중';
  try {
    const r = await api('board/make', { method: 'POST', body: { cards: [...selected], request: req } });
    if (r.error) toast(r.error, 5000); else { renderCard(r); $('#makeReq').value = ''; $(`.card[data-id="${r.id}"]`).scrollIntoView({ behavior: 'smooth' }); }
  } catch (err) { toast('실패: ' + err.message, 5000); }
  btn.disabled = false; btn.textContent = '만들기';
};

// ---------------- 비교 ----------------
$('#cmpForm').onsubmit = async e => {
  e.preventDefault();
  const question = $('#cmpQ').value.trim(); if (!question) return;
  ['#cmpA', '#cmpB'].forEach(s => $(s).innerHTML = '<span class="spin"></span> 답하는 중…');
  const btn = $('#cmpForm button'); btn.disabled = true;
  try {
    const r = await api('compare', { method: 'POST', body: { question, docs: $('#cmpDocs').checked } });
    $('#cmpA').innerHTML = cmpHtml(r.erp); $('#cmpB').innerHTML = cmpHtml(r.ontology);
    $$('.cmp-body .ev').forEach(b => b.onclick = () => openObject(b.textContent));
    loadCmpLog();
  } catch (err) { toast(err.message); }
  btn.disabled = false;
};
function cmpHtml(r) {
  const u = r.usage || {};
  return `<div class="stats"><span>⏱ <b>${r.seconds}</b>초</span><span>도구 <b>${r.steps.length}</b>번</span><span>근거 <b>${r.evidence.length}</b>개</span>
    <span>토큰 <b>${((u.input || 0) + (u.output || 0)).toLocaleString()}</b></span></div>${md(r.answer)}
    <div class="meta">${r.evidence.map(x => `<button class="ev">${esc(x)}</button>`).join('')}</div>
    <details class="steps"><summary>도구 호출 ${r.steps.length}개</summary>${r.steps.map(s => `<div class="step"><b>${esc(s.tool)}</b> <code>${esc(JSON.stringify(s.input)).slice(0, 200)}</code></div>`).join('')}</details>`;
}
async function loadCmpLog() {
  const rows = await api('compare/log');
  $('#cmpLog').innerHTML = `<tr><th>시각</th><th>질문</th><th>일반 Claude (초/도구/근거)</th><th>온트윈 (초/도구/근거)</th></tr>` +
    rows.map(r => `<tr><td>${r.at}</td><td style="white-space:normal">${esc(r.question)}</td>${['erp', 'ontology'].map(m => { const s = r.summary[m] || {}; return `<td>${s.seconds}초 / ${s.tools} / ${s.evidence}</td>`; }).join('')}</tr>`).join('');
}

// ---------------- 그래프 ----------------
let cy = null, gmode = 'schema';
const COLORS = { supplier: '#2f6fde', agency: '#7a8cb3', material: '#2e9e6a', purchase: '#8a6fd1', receipt: '#a18cd6', raw_lot: '#3aa776',
  product: '#1f3a5f', work_order: '#c27c2c', equipment: '#8c8c8c', downtime: '#b5b5b5', filter_lot: '#9a9a9a', fg_lot: '#244a7a',
  inspection: '#d1a93a', ncr: '#d64545', customer: '#d1607a', approval: '#e39bb0', sales_order: '#c9799a', delivery: '#b08ba0', plan: '#b0b8c8', event: '#666' };
$$('[data-g]').forEach(b => b.onclick = () => graphMode(b.dataset.g));
// 설계도 배치: 왼쪽 구매 → 품질 → 생산 → 오른쪽 영업
const SCHEMA_POS = { agency: { x: 100, y: 80 }, supplier: { x: 100, y: 300 }, purchase: { x: 330, y: 190 }, receipt: { x: 560, y: 190 },
  material: { x: 330, y: 440 }, inspection: { x: 790, y: 60 }, raw_lot: { x: 790, y: 300 }, ncr: { x: 1020, y: 60 }, work_order: { x: 1020, y: 300 },
  equipment: { x: 1020, y: 520 }, downtime: { x: 1250, y: 620 }, filter_lot: { x: 790, y: 560 }, product: { x: 560, y: 560 }, approval: { x: 560, y: 760 },
  fg_lot: { x: 1250, y: 300 }, delivery: { x: 1480, y: 160 }, sales_order: { x: 1700, y: 300 }, customer: { x: 1700, y: 560 }, plan: { x: 1480, y: 760 }, event: { x: 100, y: 620 } };
async function graphMode(m, type, id) {
  gmode = m; $$('[data-g]').forEach(b => b.classList.toggle('on', b.dataset.g === m));
  if (cy) cy.destroy();
  cy = cytoscape({ container: $('#cy'), wheelSensitivity: 0.25, style: [
    { selector: 'node', style: { 'background-color': n => COLORS[n.data('type')] || '#888', label: 'data(label)', 'font-size': 10, color: '#1d2433',
      'text-valign': 'bottom', 'text-margin-y': 4, width: n => n.data('size') || 26, height: n => n.data('size') || 26, 'text-wrap': 'wrap', 'text-max-width': 120 } },
    { selector: 'node[flag="red"]', style: { 'border-width': 4, 'border-color': '#d64545' } },
    { selector: 'node[flag="orange"]', style: { 'border-width': 4, 'border-color': '#e08a1e' } },
    { selector: 'node:selected', style: { 'overlay-color': '#2f6fde', 'overlay-opacity': .15 } },
    { selector: 'edge', style: { width: 1.3, 'line-color': '#c5ccd8', 'target-arrow-color': '#c5ccd8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
      label: 'data(label)', 'font-size': 9, color: '#6b7385', 'text-rotation': 'autorotate', 'text-background-color': '#fff', 'text-background-opacity': .8 } },
  ] });
  cy.on('tap', 'node', e => nodeInfo(e.target.data()));
  cy.on('dbltap', 'node', e => { if (gmode === 'data') expand(e.target.data('otype'), e.target.data('oid')); });
  if (m === 'schema') {
    const g = await api('graph/schema');
    cy.add(g.nodes.map(n => ({ data: { id: n.id, type: n.id, label: `${n.label}\n${n.count.toLocaleString()}`, size: 50 + Math.min(40, Math.sqrt(n.count) * 1.5), schema: true },
      position: ((p) => ({ x: p.x * 0.6, y: p.y * 0.6 }))(SCHEMA_POS[n.id] || { x: 100, y: 900 }) })));
    cy.add(g.edges.map((e, i) => ({ data: { id: 'e' + i, source: e.source, target: e.target, label: e.label } })));
    cy.style().selector('node').style({ 'font-size': 20, 'text-max-width': 200 }).selector('edge').style({ 'font-size': 14, width: 2.5 }).update();
    cy.layout({ name: 'preset', padding: 30 }).run();
  } else if (type && id) { expand(type, id); }
  else { $('#gSide').innerHTML = '<p class="muted">위에서 객체를 찾아 시작하세요. 예: PL-260731-K03-01, 한빛폴리텍, RS-05</p>'; }
}
async function expand(type, id) {
  const g = await api(`graph/node?type=${type}&id=${encodeURIComponent(id)}`);
  const add = [];
  for (const n of g.nodes) if (!cy.getElementById(n.id).length) add.push({ data: { id: n.id, type: n.type, otype: n.type, oid: n.id.split('|').slice(1).join('|'),
    label: `${n.label}\n(${n.kind})`, flag: n.flags.some(f => f.includes('부적합') || f.includes('불합격')) ? 'red' : n.flags.length ? 'orange' : '' } });
  for (const e of g.edges) { const eid = e.source + '>' + e.target + e.label; if (!cy.getElementById(eid).length) add.push({ data: { id: eid, ...e } }); }
  cy.add(add);
  const focus = `${type}|${id}`;
  cy.layout({ name: 'concentric', animate: false, padding: 40, minNodeSpacing: 70, avoidOverlap: true,
    concentric: n => n.id() === focus ? 3 : n.neighborhood(`node[id = "${focus}"]`).length ? 2 : 1, levelWidth: () => 1 }).run();
  if (cy.zoom() > 1.1) { cy.zoom(1.1); cy.center(); }
  cy.getElementById(`${type}|${id}`).select();
  nodeInfo({ otype: type, oid: id });
}
async function nodeInfo(d) {
  if (d.schema) {
    const types = await api('types'); const t = types.find(x => x.type === d.id);
    $('#gSide').innerHTML = `<h3>${esc(t.name)} <small class="muted">${t.type}</small></h3><p>${esc(t.description)}</p>
      <div class="kv"><div>객체 수</div><div>${t.count.toLocaleString()}</div><div>현업 별칭</div><div>${esc(t.aliases.join(', '))}</div></div>
      <p><button onclick="show('onto'); ontoMode('objects')">정의 고치기</button></p>`;
    return;
  }
  const o = await api(`get?ref=${encodeURIComponent(d.oid)}&type=${d.otype}`);
  $('#gSide').innerHTML = objectHtml(o) + '<p class="muted">더블클릭하면 이 노드의 연결을 펼칩니다.</p>';
  $$('#gSide .ev').forEach(b => b.onclick = async () => { let t = b.dataset.t || guessType(b.dataset.id); if (!t) { const f = await api('find?q=' + encodeURIComponent(b.dataset.id)); t = f[0]?.type; } if (t) expand(t, b.dataset.id); });
  $('#gSide .tograph')?.remove();
}
function guessType(id) {
  const n = cy.nodes().filter(x => x.data('oid') === id); return n.length ? n[0].data('otype') : null;
}
$('#gFind').onsubmit = async e => {
  e.preventDefault();
  const r = await api('find?q=' + encodeURIComponent($('#gQ').value));
  if (!r.length || !r[0].id) return toast('찾지 못했습니다');
  if (gmode !== 'data') await graphMode('data');
  expand(r[0].type, r[0].id);
};

// ---------------- 온톨로지 편집 ----------------
let onto = null;
$$('[data-o]').forEach(b => b.onclick = () => ontoMode(b.dataset.o));
async function ontoMode(m) {
  $$('[data-o]').forEach(b => b.classList.toggle('on', b.dataset.o === m));
  onto = await api('onto');
  $('#ontoVer').textContent = 'v' + onto.version;
  $('#ontoInfo').textContent = `객체 ${onto.objects}종 · 규칙 ${onto.rules}개`;
  const body = $('#ontoBody');
  const doc = parseYaml(onto.yaml);
  if (m === 'rules') {
    body.innerHTML = `<p class="muted">숫자를 바꾸고 저장하면 바로 판정에 쓰입니다(예: C사 출하 기준 90 → 120일). 모든 수정은 이력에 남고 되돌릴 수 있습니다.</p>
      <table class="grid"><tr><th>규칙</th><th>조건</th><th>판단 → 다음 행동</th><th>숫자</th></tr>${doc.rules.map(r => `<tr><td><b>${esc(r.id)}</b></td><td>${esc(r.when)}</td>
      <td>${esc(r.then)} → ${esc(r.next)}</td><td>${Object.entries(r.params || {}).map(([k, v]) => `<label style="display:inline-flex;gap:4px;align-items:center;margin:2px 6px 2px 0">${esc(k)}
      <input class="param" data-path="rules.${r.id}.params.${k}" value="${esc(v)}"></label>`).join('') || '<span class="muted">—</span>'}</td></tr>`).join('')}</table>
      <p><input id="reason" placeholder="수정 이유 (예: C사 요청으로 기준 강화)" style="width:420px"> <button class="primary" id="saveParams">저장</button></p>`;
    $('#saveParams').onclick = async () => {
      const changed = $$('.param').filter(i => String(getPath(doc, i.dataset.path)) !== i.value);
      if (!changed.length) return toast('바뀐 숫자가 없습니다');
      let r;
      for (const i of changed) r = await api('onto/patch', { method: 'POST', body: { path: i.dataset.path, value: isNaN(+i.value) ? i.value : +i.value, reason: $('#reason').value } });
      showSave(r); ontoMode('rules');
    };
  } else if (m === 'objects') {
    body.innerHTML = `<p class="muted">현업 이름과 별칭을 고칩니다. 별칭은 쉼표로 구분합니다.</p>
      <table class="grid"><tr><th>id</th><th>이름</th><th>현업 별칭</th><th>설명</th><th>속성 수</th><th></th></tr>${Object.entries(doc.objects).map(([k, o]) => `<tr class="objrow" data-k="${k}">
      <td><code>${k}</code></td><td><input data-f="name" value="${esc(o.name)}"></td><td><input data-f="aliases" value="${esc((o.aliases || []).join(', '))}"></td>
      <td><input data-f="description" value="${esc(o.description || '')}"></td><td>${Object.keys(o.properties || {}).length}</td><td><button data-save>저장</button></td></tr>`).join('')}</table>
      <p class="muted">속성·연결 추가처럼 큰 수정은 '전체 정의(YAML)'에서 합니다.</p>`;
    $$('[data-save]').forEach(b => b.onclick = async () => {
      const tr = b.closest('tr'), k = tr.dataset.k, o = doc.objects[k];
      const vals = { name: $('[data-f=name]', tr).value, aliases: $('[data-f=aliases]', tr).value.split(',').map(s => s.trim()).filter(Boolean), description: $('[data-f=description]', tr).value };
      let r = null;
      for (const [f, v] of Object.entries(vals)) if (JSON.stringify(v) !== JSON.stringify(f === 'aliases' ? (o.aliases || []) : (o[f] || '')))
        r = await api('onto/patch', { method: 'POST', body: { path: `objects.${k}.${f}`, value: v, reason: `${o.name} ${f} 수정` } });
      r ? showSave(r) : toast('바뀐 내용이 없습니다');
      ontoMode('objects');
    });
  } else if (m === 'yaml') {
    body.innerHTML = `<textarea class="yaml" id="yamlText" spellcheck="false">${esc(onto.yaml)}</textarea>
      <p><input id="reason" placeholder="수정 이유" style="width:420px"> <button id="chkYaml">검증</button> <button class="primary" id="saveYaml">저장</button></p><div id="yamlRes"></div>`;
    $('#chkYaml').onclick = async () => { const r = await api('onto/check', { method: 'POST', body: { yaml: $('#yamlText').value } }); $('#yamlRes').innerHTML = resHtml(r); };
    $('#saveYaml').onclick = async () => { const r = await api('onto/save', { method: 'POST', body: { yaml: $('#yamlText').value, reason: $('#reason').value } }); showSave(r); if (r.ok) ontoMode('yaml'); else $('#yamlRes').innerHTML = resHtml(r); };
  } else {
    const vs = await api('onto/versions');
    body.innerHTML = vs.map((v, i) => `<div class="ver"><b>v${esc(v.version)}</b> <span class="muted">${esc(v.at)} · ${esc(v.author)}</span> ${esc(v.reason || '')}
      ${i > 0 ? `<button data-rb="${esc(v.version)}" style="float:right">이 버전으로 되돌리기</button>` : '<span class="chip" style="float:right">현재</span>'}
      <div class="changes">${v.changes.map(c => `<div><code>${esc(c.path)}</code> <span class="before">${esc(fmt(c.before))}</span> → <span class="after">${esc(fmt(c.after))}</span></div>`).join('')}</div></div>`).join('');
    $$('[data-rb]').forEach(b => b.onclick = async () => { if (!confirm(`v${b.dataset.rb}로 되돌릴까요? (새 버전으로 저장됩니다)`)) return; showSave(await api('onto/rollback', { method: 'POST', body: { version: b.dataset.rb } })); ontoMode('hist'); });
  }
}
function resHtml(r) {
  return (r.problems?.length ? `<div class="probs">${r.problems.map(esc).join('<br>')}</div>` : '<div style="color:var(--green)">문제 없음</div>') +
    (r.changes?.length ? `<div class="changes"><b>바뀌는 내용</b>${r.changes.map(c => `<div><code>${esc(c.path)}</code> <span class="before">${esc(fmt(c.before))}</span> → <span class="after">${esc(fmt(c.after))}</span></div>`).join('')}</div>` : '');
}
function showSave(r) { r?.ok ? toast(`저장됨: v${r.version} (바뀐 칸 ${r.changes.length}개) — 판정에 바로 반영`) : toast('저장 안 됨: ' + (r?.problems || []).join(' / '), 5000); }
function getPath(o, p) { return p.split('.').reduce((a, k) => Array.isArray(a) ? a.find(x => x.id === k) : a?.[k], o); }
// 화면 표시용 간단 YAML 읽기: 서버에서 JSON으로 받는 대신 js-yaml 사용
function parseYaml(text) { return window.jsyaml.load(text); }

// ---------------- 동기화 화면 ----------------
async function loadSync() { renderSync(await api('sync')); }
function renderSync(s) {
  const n = Object.values(s.objects).reduce((a, b) => a + b, 0);
  $('#syncInfo').innerHTML = `<div class="kv"><div>ERP 주소</div><div>${esc(s.erp)}</div><div>기준일</div><div>${esc(s.as_of)}</div>
    <div>객체 / 연결</div><div>${n.toLocaleString()} / ${s.links.toLocaleString()}</div><div>마지막 갱신</div><div>${esc(s.last?.at)} (${esc(s.last?.kind)})</div>
    <div>변경분 확인</div><div>${s.poll_sec}초마다 · 마지막 ${esc(s.last_poll || '—')}</div>${s.error ? `<div>오류</div><div class="probs">${esc(s.error)}</div>` : ''}</div>`;
  $('#syncCounts').innerHTML = '<tr><th>객체</th><th>수</th></tr>' + Object.entries(s.objects).map(([k, v]) => `<tr><td>${k}</td><td>${v.toLocaleString()}</td></tr>`).join('');
  $('#syncLog').innerHTML = '<tr><th>시각</th><th>종류</th><th>문서</th><th>바뀐 객체</th><th>내용</th></tr>' +
    s.log.map(l => `<tr><td>${l.at}</td><td>${esc(l.kind)}</td><td>${esc(l.doctype)} ${esc(l.name)}</td><td>${l.changed}</td><td style="white-space:normal">${esc(l.detail)}</td></tr>`).join('');
  $('#hookUrl').textContent = 'http://host.docker.internal:8501/ow/webhook';
}
$('#fullSync').onclick = async () => { $('#fullSync').disabled = true; await api('sync/full', { method: 'POST' }); $('#fullSync').disabled = false; loadSync(); toast('전체 동기화 완료'); };
