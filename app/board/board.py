"""작업대 (F15): 데이터 카드를 올려 두고, 골라서 '표 만들어 줘'.

카드 종류
  onto    온톨로지 객체 목록 (속성 + 연결된 객체 id 열)       예: 구매 건, 원재료
  erp     ERP 화면 원본 목록                                예: Item Price
  result  다른 카드로 만든 결과 (요청·코드를 기억 → 다시 실행하면 ERP 최신값으로 재계산)

계산은 Claude가 쓴 pandas 코드를 별도 프로세스에서 돌려서 한다(AI가 숫자를 짐작하지 않게).
"""
import json
import os
import pathlib
import pickle
import subprocess
import sys
import tempfile
import time
import uuid

import anthropic
import pandas as pd

from app import config

RUNNER = pathlib.Path(__file__).parent / "runner.py"
_cache = {}


def _db(rt):
    db = rt["store"].db
    db.execute("CREATE TABLE IF NOT EXISTS board_cards (id TEXT PRIMARY KEY, title TEXT, spec TEXT, created TEXT)")
    return db


def sources(rt):
    from app.agent.tools import ERP_DOCTYPES
    d = rt["schema"]
    return {"onto": [{"type": k, "name": v["name"]} for k, v in d["objects"].items() if "documents" not in v["source"]],
            "erp": ERP_DOCTYPES + ["Item Price", "Stock Ledger Entry"]}


def list_cards(rt):
    return [{"id": r[0], "title": r[1], **json.loads(r[2]), "created": r[3]}
            for r in _db(rt).execute("SELECT * FROM board_cards ORDER BY created")]


def add_card(rt, spec):
    cid = spec.get("id") or uuid.uuid4().hex[:8]
    title = spec.get("title") or _default_title(rt, spec)
    spec = {k: v for k, v in spec.items() if k not in ("id", "title")}
    db = _db(rt)
    with db:
        db.execute("INSERT OR REPLACE INTO board_cards VALUES (?,?,?,?)",
                   (cid, title, json.dumps(spec, ensure_ascii=False), time.strftime("%Y-%m-%d %H:%M:%S")))
    return card_data(rt, cid, refresh=True)


def delete_card(rt, cid):
    db = _db(rt)
    with db:
        db.execute("DELETE FROM board_cards WHERE id=?", (cid,))
    _cache.pop(cid, None)
    return {"ok": True}


def _default_title(rt, spec):
    if spec.get("source") == "onto":
        return rt["schema"]["objects"][spec["type"]]["name"]
    return spec.get("doctype", "카드")


def _get(rt, cid):
    r = _db(rt).execute("SELECT * FROM board_cards WHERE id=?", (cid,)).fetchone()
    if not r:
        raise KeyError(f"카드 {cid} 없음")
    return {"id": r[0], "title": r[1], **json.loads(r[2])}


def frame(rt, cid, refresh=False):
    """카드 → DataFrame (캐시)."""
    if not refresh and cid in _cache:
        return _cache[cid]
    c = _get(rt, cid)
    src = c.get("source")
    if src == "onto":
        df = onto_frame(rt, c["type"])
    elif src == "erp":
        rows = rt["erp"].get_all(c["doctype"], parent=c.get("parent"), filters=c.get("filters"),
                                 fields=c.get("fields") or ["*"])
        df = pd.DataFrame(rows)
        drop = [x for x in ("owner", "modified_by", "creation", "_user_tags", "_comments", "_assign", "_liked_by", "idx")
                if x in df.columns]
        df = df.drop(columns=drop)
    elif src == "result":
        dfs = {_get(rt, i)["title"]: frame(rt, i, refresh) for i in c["inputs"]}
        r = run_code(c["code"], dfs)
        if r.get("error"):
            raise RuntimeError(r["error"])
        df = r["df"]
    else:
        raise ValueError(f"카드 종류 '{src}' 모름")
    if c.get("query"):
        try:
            df = df.query(c["query"])
        except Exception:
            pass
    _cache[cid] = df
    return df


def onto_frame(rt, type_):
    """온톨로지 객체 목록 + 하나짜리 연결은 열로 펼친다 (예: 구매 건 → 주문(원재료), 발주처(공급사))."""
    s = rt["store"]
    spec = rt["schema"]["objects"][type_]
    one = [l["rel"] for l in spec.get("links") or [] if str(l.get("card", "")) in ("1", "0..1", "N..1")]
    lk = {}
    for r in s.db.execute("SELECT src_id, rel, dst_id FROM links WHERE src_type=?", (type_,)):
        if r[1] in one:
            lk.setdefault(r[0], {}).setdefault(r[1], r[2])
    rows = []
    for o in s.objs(type_):
        row = {"id": o["id"], "이름": o["title"], "ERP 상태": o["status"]}
        for k, v in o["props"].items():
            if isinstance(v, (list, dict)):
                continue
            row[k] = v
        for rel in one:
            row[rel] = lk.get(o["id"], {}).get(rel)
        rows.append(row)
    return pd.DataFrame(rows)


def card_data(rt, cid, refresh=False, limit=300):
    c = _get(rt, cid)
    try:
        df = frame(rt, cid, refresh)
    except Exception as e:
        return {**c, "error": str(e)[:600], "columns": [], "rows": [], "total": 0}
    return {**c, "columns": [str(x) for x in df.columns], "rows": json.loads(df.head(limit).to_json(orient="records", force_ascii=False)),
            "total": len(df), "at": time.strftime("%H:%M:%S")}


# ---------------- 만들기 ----------------
SUBMIT = {"name": "submit", "description": "결과를 만드는 pandas 코드 제출",
          "input_schema": {"type": "object", "properties": {
              "title": {"type": "string", "description": "결과 카드 제목(한국어, 짧게)"},
              "code": {"type": "string", "description": "def make(dfs): ... return df  — dfs는 {카드 제목: DataFrame}"},
              "chart": {"type": "object", "description": "선택. {type: bar|line|pie, x: 열, y: [열,…], title}"},
              "note": {"type": "string", "description": "계산 방법 한두 문장(가정 포함)"}},
              "required": ["title", "code"]}}


def describe(name, df):
    dtypes = {str(c): str(t) for c, t in df.dtypes.items()}
    sample = df.head(5).to_json(orient="records", force_ascii=False)
    return f"카드 '{name}': {len(df)}행\n열과 형식: {json.dumps(dtypes, ensure_ascii=False)}\n예시 5행: {sample}"


def make(rt, card_ids, request):
    dfs = {}
    for i in card_ids:
        c = _get(rt, i)
        dfs[c["title"]] = frame(rt, i)
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = ("아래 카드(표)로 사용자의 요청을 만족하는 결과 표를 만드는 파이썬 코드를 써라.\n"
              "- 함수 이름은 make(dfs), dfs는 {카드 제목: pandas DataFrame}. 결과 DataFrame 하나를 반환.\n"
              "- pandas, numpy만 사용. 파일·네트워크 접근 금지. 열 이름은 한국어로 읽기 쉽게.\n"
              "- 카드 사이 연결은 id 열과 연결 열(예: 구매 건의 '주문' = 원재료 id)로 한다.\n"
              "- 숫자는 반올림해 보기 좋게. 정렬·상위 N 등 요청을 지켜라.\n"
              "- 차트가 도움이 되면 chart도 준다.\n- 반드시 submit 도구로 제출한다.\n\n"
              + "\n\n".join(describe(k, v) for k, v in dfs.items()) + f"\n\n요청: {request}")
    msgs = [{"role": "user", "content": prompt}]
    last_err = None
    for attempt in range(3):
        r = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=4000, tools=[SUBMIT], messages=msgs)
        tu = next((b for b in r.content if b.type == "tool_use"), None)
        if tu is None:
            msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]},
                     {"role": "user", "content": "설명 대신 submit 도구로 코드를 제출하라."}]
            continue
        sub = tu.input
        res = run_code(sub["code"], dfs)
        if not res.get("error"):
            spec = {"source": "result", "inputs": card_ids, "code": sub["code"], "request": request,
                    "chart": sub.get("chart"), "note": sub.get("note", ""), "title": sub["title"]}
            out = add_card(rt, spec)
            return out
        last_err = res["error"]
        msgs += [{"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                               "content": f"실행 오류:\n{last_err}\n고쳐서 다시 제출하라."}]}]
    return {"error": f"3번 시도했지만 실행에 실패했습니다: {last_err}"}


def run_code(code, dfs, timeout=60):
    """별도 프로세스에서 실행 (ERP 키 등 환경변수 없이, 시간 제한)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp)
        (p / "code.py").write_text(code, encoding="utf-8")
        with open(p / "in.pkl", "wb") as f:
            pickle.dump(dfs, f)
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
        try:
            r = subprocess.run([sys.executable, "-I", str(RUNNER), tmp], capture_output=True, text=True,
                               timeout=timeout, env=env, cwd=tmp)
        except subprocess.TimeoutExpired:
            return {"error": f"{timeout}초 안에 끝나지 않았습니다"}
        if r.returncode != 0 or not (p / "out.pkl").exists():
            return {"error": (r.stderr or r.stdout)[-1500:]}
        with open(p / "out.pkl", "rb") as f:
            df = pickle.load(f)
        return {"df": df}
