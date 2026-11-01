// 온트윈 챗봇 위젯: ERPNext 화면 위에 뜬다. 지금 보고 있는 문서를 질문에 함께 보낸다.
(function () {
  if (window.__ontwin) return; window.__ontwin = true;
  const css = `
  #ow-btn{position:fixed;right:22px;bottom:22px;z-index:2147483000;background:#1f3a5f;color:#fff;border:none;border-radius:28px;padding:12px 18px;
    font:600 14px Pretendard,'Malgun Gothic',sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.25);cursor:pointer}
  #ow-panel{position:fixed;right:22px;bottom:80px;width:430px;height:min(640px,calc(100vh - 110px));z-index:2147483000;background:#fff;border-radius:14px;
    box-shadow:0 12px 40px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;font:14px Pretendard,'Malgun Gothic',sans-serif;color:#1d2433}
  #ow-panel.on{display:flex}
  #ow-head{background:#1f3a5f;color:#fff;padding:10px 14px;display:flex;align-items:center;gap:8px}
  #ow-head b{flex:1} #ow-head a{color:#bcd3ff;font-size:12px} #ow-head button{background:none;border:none;color:#fff;font-size:16px;cursor:pointer}
  #ow-ctx{font-size:12px;background:#eef3fb;color:#1f3a5f;padding:6px 12px;border-bottom:1px solid #e3e6ec}
  #ow-msgs{flex:1;overflow:auto;padding:12px;background:#f5f6f8}
  .ow-m{margin:0 0 10px;line-height:1.55} .ow-m.u{text-align:right}
  .ow-m .b{display:inline-block;text-align:left;padding:9px 12px;border-radius:10px;background:#fff;border:1px solid #e3e6ec;max-width:100%;overflow-x:auto}
  .ow-m.u .b{background:#1f3a5f;color:#fff;border:none}
  .ow-m table{border-collapse:collapse;font-size:12px;margin:6px 0} .ow-m td,.ow-m th{border:1px solid #e3e6ec;padding:3px 6px}
  .ow-m p{margin:4px 0} .ow-s{font-size:11.5px;color:#6b7385} .ow-s div:before{content:"→ "}
  .ow-meta{font-size:11.5px;color:#6b7385;margin-top:6px}
  #ow-form{display:flex;gap:6px;padding:10px;border-top:1px solid #e3e6ec}
  #ow-form textarea{flex:1;resize:none;border:1px solid #e3e6ec;border-radius:8px;padding:8px;font:inherit;height:42px}
  #ow-form button{background:#1f3a5f;color:#fff;border:none;border-radius:8px;padding:0 14px;cursor:pointer}
  .ow-sug{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px} .ow-sug button{border:1px solid #d5dbe6;background:#fff;border-radius:14px;padding:4px 10px;font-size:12px;cursor:pointer}`;
  const st = document.createElement('style'); st.textContent = css; document.head.append(st);
  // 온트윈 안(iframe)에서는 ERPNext 자체 메뉴를 숨기고 온트윈의 업무별 메뉴를 쓴다
  if (window.top !== window.self) {
    const em = document.createElement('style');
    em.textContent = `.dock,.body-sidebar-container{display:none!important}
      body{--dock-width:0px!important;--sidebar-width:0px!important}
      .main-section,.page-container,.layout-main,.container.page-body{margin-left:0!important;padding-left:0!important}`;
    document.head.append(em);
  }
  if (!window.marked) { const s = document.createElement('script'); s.src = '/ow/static/vendor/marked.min.js'; document.head.append(s); }

  const btn = document.createElement('button'); btn.id = 'ow-btn'; btn.textContent = '◐ 온트윈';
  const panel = document.createElement('div'); panel.id = 'ow-panel';
  panel.innerHTML = `<div id="ow-head"><b>◐ 온트윈</b><a href="/ow/" target="_blank">전체 화면 ↗</a><button id="ow-x">✕</button></div>
    <div id="ow-ctx"></div><div id="ow-msgs"></div>
    <form id="ow-form"><textarea id="ow-q" placeholder="이 화면에 대해 물어보세요"></textarea><button>보내기</button></form>`;
  document.body.append(btn, panel);
  const $ = s => panel.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  let history = [];

  function context() {
    try {
      const r = (window.frappe && frappe.get_route && frappe.get_route()) || [];
      if (r[0] === 'Form' && r[2]) return { text: `${r[1]} ${r[2]}`, doctype: r[1], name: r[2] };
      if (r[0] === 'List' && r[1]) return { text: `${r[1]} 목록`, doctype: r[1] };
      if (r[0]) return { text: r.join(' / ') };
    } catch (e) { }
    return { text: '' };
  }
  function suggestions(c) {
    const m = {
      'Purchase Order': ['이 건 언제 들어와?', '이 공급사 최근 납기 지켜?', '이 원재료 부족할 위험 있어?'],
      'Batch': ['이 lot 어디에 쓰였어?', '이 lot IQC 경계·이상치 있어?', '이 lot 출하해도 돼?'],
      'Non Conformance': ['원인 후보 찾아줘', '같은 위험이 있는 재고·출하분은?'],
      'Sales Order': ['이 주문 납기 지킬 수 있어?', '보낼 수 있는 재고 lot은?'],
      'Supplier': ['이 공급사 품질 경향 어때?', '이 공급사가 늦으면 영향받는 주문은?'],
      'Work Order': ['이 작업지시에 들어간 원재료 lot과 품질은?'],
      'Quality Inspection': ['이 검사 측정값 이상한 거 있어?'],
      'Delivery Note': ['이 출하 lot 추적해줘'],
    };
    return m[c.doctype] || ['오늘 확인해야 할 품질 이슈 있어?'];
  }
  function refreshCtx() {
    const c = context();
    $('#ow-ctx').textContent = c.text ? `지금 화면: ${c.text}` : '화면 정보 없음';
    if (!$('#ow-msgs').children.length || $('#ow-msgs').dataset.ctx !== c.text) {
      $('#ow-msgs').dataset.ctx = c.text;
      if (!history.length) $('#ow-msgs').innerHTML = `<div class="ow-m"><div class="b">${c.text ? `<b>${esc(c.text)}</b>에 대해 물어보세요.` : '무엇이든 물어보세요.'}
        <div class="ow-sug">${suggestions(c).map(s => `<button type="button">${esc(s)}</button>`).join('')}</div></div></div>`;
      panel.querySelectorAll('.ow-sug button').forEach(b => b.onclick = () => { $('#ow-q').value = b.textContent; $('#ow-form').requestSubmit(); });
    }
  }
  btn.onclick = () => { panel.classList.toggle('on'); refreshCtx(); $('#ow-q').focus(); };
  $('#ow-x').onclick = () => panel.classList.remove('on');
  window.addEventListener('hashchange', () => panel.classList.contains('on') && refreshCtx());
  setInterval(() => panel.classList.contains('on') && refreshCtx(), 2000);
  $('#ow-q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#ow-form').requestSubmit(); } });

  $('#ow-form').onsubmit = async e => {
    e.preventDefault();
    const q = $('#ow-q').value.trim(); if (!q) return; $('#ow-q').value = '';
    const c = context();
    add('u', esc(q));
    const box = add('a', '<div class="ow-s">생각하는 중…</div>');
    try {
      const r = await fetch('/ow/api/chat/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history, context: c.text, mode: 'ontology' }) });
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', res = null;
      while (true) {
        const { value, done } = await rd.read(); if (done) break;
        buf += dec.decode(value, { stream: true }); let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const ch = buf.slice(0, i); buf = buf.slice(i + 2);
          const ev = /event: (\w+)/.exec(ch)?.[1], data = JSON.parse(ch.slice(ch.indexOf('data: ') + 6));
          if (ev === 'step') box.querySelector('.ow-s').insertAdjacentHTML('beforeend', `<div>${esc(data.tool)}</div>`);
          if (ev === 'done') res = data; if (ev === 'error') throw new Error(data.error);
        }
        $('#ow-msgs').scrollTop = 1e9;
      }
      history = res.history.slice(-10);
      box.innerHTML = (window.marked ? marked.parse(res.answer.replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')) : esc(res.answer)) +
        `<div class="ow-meta">${res.seconds}초 · 함수 ${res.steps.length}번 · 근거 ${res.evidence.join(', ')}</div>`;
    } catch (err) { box.innerHTML = '오류: ' + esc(err.message); }
    $('#ow-msgs').scrollTop = 1e9;
  };
  function add(who, html) {
    const d = document.createElement('div'); d.className = 'ow-m ' + who; d.innerHTML = `<div class="b">${html}</div>`;
    $('#ow-msgs').append(d); $('#ow-msgs').scrollTop = 1e9; return d.querySelector('.b');
  }
})();
