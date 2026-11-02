"""온트윈 서버 (http://localhost:8501).

/ow/            온트윈 화면       /ow/api/...   온트윈 API      /ow/webhook   ERPNext 웹훅
그 밖의 모든 주소  ERPNext로 중계 (같은 주소에서 ERP 화면을 그대로 쓰고, 챗봇 위젯을 끼워 넣는다)
"""
import asyncio
import json
import pathlib
import threading
import time

import httpx
from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import config, runtime
from app.agent import chat
from app.ontology import editor
from app.ontology.sync import Sync

STATIC = pathlib.Path(__file__).parent / "static"
app = FastAPI(title="Ontwin")
app.mount("/ow/static", StaticFiles(directory=STATIC), name="static")

STATE = {"sync": None, "poll_sec": 20, "last_poll": None, "poll_error": None}


def rt():
    return runtime.get()


def sync():
    if STATE["sync"] is None:
        r = rt()
        STATE["sync"] = Sync(store=r["store"], erp=r["erp"], graph=r["graph"], docs=r["docs"])
    return STATE["sync"]


def after_change():
    rt()["onto"].clear()


# ---------------- 백그라운드: 변경분 가져오기 (웹훅이 안 닿아도 1분 안에 반영) ----------------
def _poller():
    while True:
        time.sleep(STATE["poll_sec"])
        try:
            n = sync().poll()
            STATE["last_poll"] = time.strftime("%H:%M:%S")
            STATE["poll_error"] = None
            if n:
                after_change()
        except Exception as e:  # ERP가 꺼져 있어도 서버는 계속 돈다
            STATE["poll_error"] = str(e)[:300]


@app.on_event("startup")
def _start():
    s = sync()
    if not s.store.objs("supplier"):
        try:
            s.full(log=lambda *_: None)
        except Exception as e:
            STATE["poll_error"] = f"첫 동기화 실패: {e}"[:300]
    threading.Thread(target=_poller, daemon=True).start()


# ---------------- 화면 ----------------
@app.get("/ow")
@app.get("/ow/")
def home():
    return FileResponse(STATIC / "index.html")


# ---------------- 웹훅 ----------------
@app.post("/ow/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = dict(await request.form())
    dt, name = body.get("doctype"), body.get("name")
    if not dt or not name:
        return {"ok": False, "why": "doctype, name 필요"}
    n = await asyncio.to_thread(sync().on_change, dt, name)
    after_change()
    return {"ok": True, "changed": n}


# ---------------- 동기화 상태 ----------------
@app.get("/ow/api/sync")
def sync_status():
    s = sync()
    o, l = s.store.counts()
    logs = [dict(r) for r in s.store.db.execute("SELECT * FROM sync_log ORDER BY rowid DESC LIMIT 30")]
    return {"objects": o, "links": sum(l.values()), "last": s.store.get_meta("last_sync"), "log": logs,
            "poll_sec": STATE["poll_sec"], "last_poll": STATE["last_poll"], "error": STATE["poll_error"],
            "erp": config.ERP_URL, "as_of": config.AS_OF or "오늘(실시간)",
            "graph": rt()["graph"].stats if rt().get("graph") else {}}


@app.post("/ow/api/sync/full")
def sync_full():
    n = sync().full(log=lambda *_: None)
    after_change()
    return {"changed": n}


# ---------------- 온톨로지 조회 ----------------
@app.get("/ow/api/find")
def api_find(q: str, type: str = None):
    return rt()["onto"].find(q, type)


@app.get("/ow/api/get")
def api_get(ref: str, type: str = None):
    return rt()["onto"].get(ref, type)


@app.get("/ow/api/types")
def api_types():
    d = rt()["schema"]
    o, _ = rt()["store"].counts()
    return [{"type": k, "name": v["name"], "aliases": v.get("aliases", []), "count": o.get(k, 0),
             "description": v.get("description", "")} for k, v in d["objects"].items()]


@app.get("/ow/api/objects")
def api_objects(type: str, q: str = "", limit: int = 200):
    r = rt()["onto"].list_objects(type, limit=5000)
    rows = r.get("목록", [])
    if q:
        rows = [x for x in rows if q.lower() in json.dumps(x, ensure_ascii=False, default=str).lower()]
    return {"total": len(rows), "rows": rows[:limit]}


@app.get("/ow/api/graph/schema")
def graph_schema():
    """설계도: 정의 파일의 객체·관계문 + 실제 데이터 수. 정의만 있고 데이터가 없는 관계문도 보여 준다."""
    d = rt()["schema"]
    st = rt()["store"]
    o, _ = st.counts()
    lc = {}
    for a, r, b, n in st.db.execute("SELECT src_type, rel, dst_type, COUNT(*) FROM links GROUP BY 1,2,3"):
        lc[(a, r, b)] = n
    nodes = [{"id": k, "label": v["name"], "count": o.get(k, 0)} for k, v in d["objects"].items()]
    edges, seen = [], set()
    for k, v in d["objects"].items():
        for l in v.get("links") or []:
            tos = l["to"] if isinstance(l["to"], list) else [l["to"]]
            if "*" in tos:  # '모든 객체' 관계문: 실제로 이어진 상대만 그린다
                tos = sorted({b for (a, r, b) in lc if a == k and r == l["rel"]})
            for t in tos:
                if t in d["objects"]:
                    seen.add((k, l["rel"], t))
                    edges.append({"source": k, "target": t, "label": l["rel"], "card": l.get("card", ""),
                                  "count": lc.get((k, l["rel"], t), 0)})
    if any(v.get("measurements") for v in d["objects"].values()):
        g = rt().get("graph")
        n = 0
        try:
            n = g.scalar("MATCH (m:measurement) RETURN count(m)") if g else 0
        except Exception:
            pass
        nodes.append({"id": "measurement", "label": "측정값", "count": int(n or 0), "derived": True})
        for k, v in d["objects"].items():
            if v.get("measurements"):
                edges.append({"source": k, "target": "measurement", "label": "측정값", "card": "N", "count": int(n or 0)})
    gs = rt().get("graph").stats if rt().get("graph") else {}
    return {"nodes": nodes, "edges": edges, "version": str(d["meta"]["version"]), "graph": gs}


@app.get("/ow/api/graph/node")
def graph_node(type: str, id: str):
    """객체 하나와 바로 이웃(데이터 그래프 펼치기)."""
    s, o = rt()["store"], rt()["onto"]
    me = s.obj(type, id)
    if not me:
        return {"nodes": [], "edges": []}
    flags = _flags(type, id)
    nodes = {(type, id): {"id": f"{type}|{id}", "type": type, "label": me["title"], "kind": o.type_name(type), "flags": flags}}
    edges = []
    for l in s.links_from(type, id):
        nodes.setdefault((l["dst_type"], l["dst_id"]), None)
        edges.append({"source": f"{type}|{id}", "target": f"{l['dst_type']}|{l['dst_id']}", "label": l["rel"]})
    for l in s.links_to(type, id):
        nodes.setdefault((l["src_type"], l["src_id"]), None)
        edges.append({"source": f"{l['src_type']}|{l['src_id']}", "target": f"{type}|{id}", "label": l["rel"]})
    out = []
    for (t, i), v in list(nodes.items())[:150]:
        if v is None:
            x = s.obj(t, i)
            v = {"id": f"{t}|{i}", "type": t, "label": x["title"] if x else i, "kind": o.type_name(t), "flags": _flags(t, i)}
        out.append(v)
    ids = {n["id"] for n in out}
    return {"nodes": out, "edges": [e for e in edges if e["source"] in ids and e["target"] in ids]}


def _flags(t, i):
    """그래프 색 표시: 규칙 판정."""
    o = rt()["onto"]
    f = []
    try:
        if t == "raw_lot" and o.iqc_of_lot(i, only_flagged=True):
            f.append("IQC 경계·이상치")
        if t in ("raw_lot", "fg_lot") and any(l["src_type"] == "ncr" for l in o.s.links_to(t, i, "대상")):
            f.append("부적합")
        if t == "inspection" and (o.s.obj(t, i) or {}).get("props", {}).get("판정") == "Rejected":
            f.append("불합격")
    except Exception:
        pass
    return f


# ---------------- 챗봇·비교 ----------------
@app.post("/ow/api/chat")
def api_chat(body: dict = Body(...)):
    r = chat.ask(rt(), body["question"], mode=body.get("mode", "ontology"), history=body.get("history"),
                 context=body.get("context"))
    return r


@app.post("/ow/api/chat/stream")
def api_chat_stream(body: dict = Body(...)):
    """도구 호출을 하나씩 흘려보내고 마지막에 답을 보낸다 (Server-Sent Events)."""
    import queue
    qq = queue.Queue()

    def work():
        try:
            r = chat.ask(rt(), body["question"], mode=body.get("mode", "ontology"), history=body.get("history"),
                         context=body.get("context"), on_step=lambda s: qq.put(("step", s)))
            qq.put(("done", r))
        except Exception as e:
            qq.put(("error", {"error": str(e)[:500]}))

    threading.Thread(target=work, daemon=True).start()

    def gen():
        while True:
            kind, data = qq.get()
            yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/ow/api/chat/prompt")
def chat_prompt(mode: str = "ontology"):
    """증거: Claude API에 실제로 보내는 시스템 프롬프트(온톨로지·규칙·그래프 스키마 포함)와 도구 목록."""
    from app.agent import tools as T
    tools = T.ONTO_TOOLS if mode == "ontology" else T.ERP_TOOLS
    return {"system": chat.system_prompt(rt(), mode), "tools": [{"name": t["name"], "description": t["description"]} for t in tools],
            "model": config.CLAUDE_MODEL, "onto_version": str(rt()["schema"]["meta"]["version"]),
            "graph": rt()["graph"].stats if rt().get("graph") else {}}


@app.post("/ow/api/graph/query")
def graph_query_api(body: dict = Body(...)):
    """그래프 질의 화면: 사람이 직접 Cypher(읽기 전용)."""
    g = rt().get("graph")
    try:
        rows = g.query(body["cypher"], body.get("params") or {}, limit=500, who="사람")
    except Exception as e:
        return {"오류": str(e)[:800]}
    return {"행 수": len(rows), "결과": rows}


@app.get("/ow/api/graph/log")
def graph_log(n: int = 50):
    g = rt().get("graph")
    return list(reversed(g.log[-n:])) if g else []


@app.post("/ow/api/graph/subgraph")
def graph_subgraph(body: dict = Body(...)):
    """증거 그래프: 답에 나온 id들과 그 사이 연결."""
    s = rt()["store"]
    o = rt()["onto"]
    keys = {}
    for i in body.get("ids", [])[:60]:
        r = s.db.execute("SELECT type, id FROM objects WHERE id=? LIMIT 3", (i,)).fetchall()
        if not r:
            r = s.db.execute("SELECT type, id FROM objects WHERE id LIKE ? LIMIT 3", (i + ":%",)).fetchall()
        for t, x in r:
            keys[(t, x)] = True
    nodes = []
    for (t, x) in keys:
        ob = s.obj(t, x)
        nodes.append({"id": f"{t}|{x}", "type": t, "label": ob["title"] if ob else x, "kind": o.type_name(t), "flags": _flags(t, x)})
    ids = {n["id"] for n in nodes}
    edges = []
    for (t, x) in keys:
        for l in s.links_from(t, x):
            k = f"{l['dst_type']}|{l['dst_id']}"
            if k in ids:
                edges.append({"source": f"{t}|{x}", "target": k, "label": l["rel"]})
    return {"nodes": nodes, "edges": edges}


@app.post("/ow/api/shutdown")
def shutdown():
    """화면의 '끄기' 버튼: 서버를 끈다."""
    import os
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"ok": True}


@app.post("/ow/api/compare")
def api_compare(body: dict = Body(...)):
    """같은 질문을 'ERP 조회만 가진 Claude'와 '온트윈'에 동시에."""
    out = {}

    def run(mode):
        try:
            out[mode] = chat.ask(rt(), body["question"], mode=mode, docs=body.get("docs", False))
        except Exception as e:
            out[mode] = {"answer": f"오류: {e}", "steps": [], "evidence": [], "usage": {}, "seconds": 0}

    ts = [threading.Thread(target=run, args=(m,)) for m in ("erp", "ontology")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    _save_compare(body["question"], out)
    return out


def _save_compare(q, out):
    s = rt()["store"]
    with s.db:
        s.db.execute("CREATE TABLE IF NOT EXISTS compare_log (at TEXT, question TEXT, result TEXT)")
        s.db.execute("INSERT INTO compare_log VALUES (?,?,?)",
                     (time.strftime("%Y-%m-%d %H:%M:%S"), q, json.dumps(out, ensure_ascii=False, default=str)))


@app.get("/ow/api/compare/log")
def compare_log():
    s = rt()["store"]
    s.db.execute("CREATE TABLE IF NOT EXISTS compare_log (at TEXT, question TEXT, result TEXT)")
    rows = s.db.execute("SELECT rowid, at, question, result FROM compare_log ORDER BY rowid DESC LIMIT 50").fetchall()
    out = []
    for r in rows:
        res = json.loads(r[3])
        out.append({"id": r[0], "at": r[1], "question": r[2],
                    "summary": {m: {"seconds": v.get("seconds"), "tools": len(v.get("steps", [])),
                                    "evidence": len(v.get("evidence", []))} for m, v in res.items()}})
    return out


# ---------------- 온톨로지 편집 ----------------
@app.get("/ow/api/onto")
def onto_get():
    return editor.current(rt())


@app.post("/ow/api/onto/check")
def onto_check(body: dict = Body(...)):
    return editor.check(rt(), body["yaml"])


@app.post("/ow/api/onto/save")
def onto_save(body: dict = Body(...)):
    r = editor.save(rt(), body["yaml"], body.get("author", "이시형"), body.get("reason", ""))
    if r.get("ok"):
        runtime.reload_schema()
        STATE["sync"] = None
        sync().ensure_raw()
        sync().rebuild(kind="정의 수정", detail=f"v{r['version']} {body.get('reason', '')}")
        after_change()
    return r


@app.post("/ow/api/onto/patch")
def onto_patch(body: dict = Body(...)):
    """작은 수정(규칙 숫자, 별칭, 이름, 설명)을 경로로: {path: 'rules.R01_ship_shelf_life.params.C사', value: 120}"""
    y = editor.apply_patch(editor.current(rt())["yaml"], body["path"], body["value"])
    if isinstance(y, dict):
        return y
    return onto_save({"yaml": y, "author": body.get("author", "이시형"), "reason": body.get("reason") or f"{body['path']} 수정"})


@app.get("/ow/api/onto/model")
def onto_model():
    return editor.model(rt())


@app.post("/ow/api/onto/op")
def onto_op(body: dict = Body(...)):
    """쉬운 편집: 단어·속성·관계문 추가/수정/삭제 → 검증 → 새 버전 저장 → 객체·그래프 DB 다시 만들기"""
    y = editor.apply_op(editor.current(rt())["yaml"], body)
    if isinstance(y, dict):
        return y
    return onto_save({"yaml": y, "author": body.get("author", "이시형"), "reason": body.get("reason") or editor.describe_op(body)})


@app.get("/ow/api/erp/fields")
def erp_fields(doctype: str):
    """ERP 화면의 필드 목록(하위 표 필드는 '하위표.필드'). 관계문·속성 고를 때 쓴다."""
    e = rt()["erp"]
    m = e.meta(doctype)
    out, skip = [], ("Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading")
    for f in m["fields"]:
        if f["fieldtype"] in skip:
            continue
        if f["fieldtype"] in ("Table", "Table MultiSelect"):
            try:
                for cf in e.meta(f["options"])["fields"]:
                    if cf["fieldtype"] not in skip + ("Table",):
                        out.append({"field": f"{f['options']}.{cf['fieldname']}", "label": f"{f['label'] or f['options']} › {cf.get('label') or cf['fieldname']}",
                                    "type": cf["fieldtype"], "link": cf.get("options") if cf["fieldtype"] == "Link" else None})
            except Exception:
                pass
            continue
        out.append({"field": f["fieldname"], "label": f.get("label") or f["fieldname"], "type": f["fieldtype"],
                    "link": f.get("options") if f["fieldtype"] == "Link" else None})
    return out


@app.get("/ow/api/erp/doctypes")
def erp_doctypes():
    from app.agent.tools import ERP_DOCTYPES
    return ERP_DOCTYPES


@app.get("/ow/api/onto/versions")
def onto_versions():
    return editor.versions(rt())


@app.post("/ow/api/onto/rollback")
def onto_rollback(body: dict = Body(...)):
    y = editor.version_yaml(rt(), body["version"])
    if y is None:
        return {"ok": False, "why": "버전 없음"}
    return onto_save({"yaml": y, "author": body.get("author", "이시형"), "reason": f"v{body['version']}로 되돌림"})


# ---------------- 작업대·내보내기 ----------------
from app.board import board as B  # noqa: E402
from app.export import office  # noqa: E402


@app.get("/ow/api/board/sources")
def board_sources():
    return B.sources(rt())


@app.get("/ow/api/board/cards")
def board_cards():
    return B.list_cards(rt())


@app.post("/ow/api/board/card")
def board_add(body: dict = Body(...)):
    return B.add_card(rt(), body)


@app.delete("/ow/api/board/card/{cid}")
def board_del(cid: str):
    return B.delete_card(rt(), cid)


@app.get("/ow/api/board/card/{cid}")
def board_card(cid: str, refresh: int = 0):
    return B.card_data(rt(), cid, refresh=bool(refresh))


@app.post("/ow/api/board/make")
def board_make(body: dict = Body(...)):
    return B.make(rt(), body["cards"], body["request"])


@app.post("/ow/api/export/{fmt}")
def export(fmt: str, body: dict = Body(...)):
    data, name, mime = office.export(rt(), fmt, body)
    from urllib.parse import quote
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ---------------- ERPNext 중계 ----------------
# 쿠키를 저장하지 않는 클라이언트: 로그인 세션은 브라우저 쿠키 그대로 오간다(사용자끼리 섞이지 않게)
import http.cookiejar as _cj  # noqa: E402
_client = httpx.AsyncClient(base_url=config.ERP_URL, timeout=120, follow_redirects=False, trust_env=False,
                            cookies=_cj.CookieJar(policy=_cj.DefaultCookiePolicy(allowed_domains=[])))
HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "accept-encoding", "upgrade"}
WIDGET = '<script src="/ow/static/widget.js" defer></script>'


@app.get("/")
def root():
    return RedirectResponse("/ow/")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def erp_proxy(path: str, request: Request):
    if path.startswith("ow/") or path == "ow":
        return JSONResponse({"error": "not found"}, status_code=404)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    headers["accept-encoding"] = "identity"
    body = await request.body()
    try:
        r = await _client.request(request.method, "/" + path, params=request.query_params, content=body, headers=headers)
    except httpx.HTTPError as e:
        return HTMLResponse(f"<h3>ERPNext에 연결할 수 없습니다</h3><p>{config.ERP_URL}: {e}</p>", status_code=502)
    out_headers = []
    for k, v in r.headers.multi_items():
        kl = k.lower()
        if kl in HOP or kl in ("content-encoding", "x-frame-options", "content-security-policy", "server", "date"):
            continue
        if kl == "location":
            v = v.replace(config.ERP_URL.rstrip("/"), "")
        if kl == "set-cookie":
            v = v.replace("; Secure", "")
        out_headers.append((k, v))
    content = r.content
    if "text/html" in r.headers.get("content-type", "") and b"</body>" in content and not path.startswith("api/"):
        content = content.replace(b"</body>", WIDGET.encode() + b"</body>", 1)
    resp = Response(content, status_code=r.status_code)
    for k, v in out_headers:
        resp.headers.append(k, v)
    return resp
