"""온톨로지 정의 수정·버전 관리 (F11).

저장할 때마다: 검증 → 버전 +0.1 → 전체 스냅숏(onto_versions) + 바뀐 칸(onto_changes) → ontology.yaml 다시 쓰기.
되돌리기도 '이전 스냅숏을 새 버전으로 저장'이라 이력은 지워지지 않는다.
"""
import difflib
import io
import json

import yaml
from ruamel.yaml import YAML

from app import config
from app.ontology import schema as sch
from app.ontology.store import now


def _ry():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def current(rt):
    text = config.ONTOLOGY_FILE.read_text(encoding="utf-8")
    d = yaml.safe_load(text)
    _ensure_base(rt, text, d)
    return {"yaml": text, "version": str(d["meta"]["version"]), "objects": len(d["objects"]), "rules": len(d["rules"])}


def _ensure_base(rt, text, d):
    db = rt["store"].db
    if not db.execute("SELECT 1 FROM onto_versions LIMIT 1").fetchone():
        with db:
            db.execute("INSERT INTO onto_versions VALUES (?,?,?,?,?)",
                       (str(d["meta"]["version"]), now(), "이시형", "처음 버전", text))


def flatten(x, p=""):
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out.update(flatten(v, f"{p}.{k}" if p else str(k)))
    elif isinstance(x, list) and x and all(isinstance(i, dict) and "id" in i for i in x):
        for i in x:
            out.update(flatten({k: v for k, v in i.items() if k != "id"}, f"{p}.{i['id']}"))
    else:
        out[p] = x
    return out


def diff(old, new):
    a, b = flatten(old), flatten(new)
    rows = []
    for k in sorted(set(a) | set(b)):
        if k == "meta.version":
            continue
        if a.get(k) != b.get(k):
            rows.append({"path": k, "before": a.get(k), "after": b.get(k)})
    return rows


def check(rt, text):
    """문법·참조·ERP 필드 검증 + 바뀐 내용 미리 보기."""
    try:
        d = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return {"ok": False, "problems": [f"YAML 문법 오류: {e}"]}
    probs = []
    for key in ("meta", "objects", "rules"):
        if key not in (d or {}):
            probs.append(f"'{key}' 구역이 없습니다")
    if probs:
        return {"ok": False, "problems": probs}
    for k, o in d["objects"].items():
        for need in ("name", "source"):
            if need not in o:
                probs.append(f"{k}: '{need}' 없음")
    try:
        s = sch.Schema(d, rt["erp"])
        probs += s.validate()
    except Exception as e:
        probs.append(f"ERP 필드 확인 실패: {e}")
    names = {}
    for k, o in d["objects"].items():
        for a in [o.get("name")] + list(o.get("aliases") or []):
            if a in names and names[a] != k:
                probs.append(f"별칭 '{a}'가 {names[a]}와 {k}에 같이 걸려 있습니다")
            names[a] = k
    old = yaml.safe_load(config.ONTOLOGY_FILE.read_text(encoding="utf-8"))
    return {"ok": not probs, "problems": probs, "changes": diff(old, d)}


def save(rt, text, author, reason):
    c = check(rt, text)
    if not c["ok"]:
        return c
    if not c["changes"]:
        return {"ok": False, "problems": ["바뀐 내용이 없습니다"]}
    old_text = config.ONTOLOGY_FILE.read_text(encoding="utf-8")
    _ensure_base(rt, old_text, yaml.safe_load(old_text))
    ver = _next_version(rt)
    y = _ry()
    data = y.load(text)
    data["meta"]["version"] = ver
    buf = io.StringIO()
    y.dump(data, buf)
    new_text = buf.getvalue()
    db = rt["store"].db
    with db:
        db.execute("INSERT INTO onto_versions VALUES (?,?,?,?,?)", (ver, now(), author, reason, new_text))
        db.executemany("INSERT INTO onto_changes VALUES (?,?,?,?)",
                       [(ver, r["path"], json.dumps(r["before"], ensure_ascii=False, default=str),
                         json.dumps(r["after"], ensure_ascii=False, default=str)) for r in c["changes"]])
    config.ONTOLOGY_FILE.write_text(new_text, encoding="utf-8")
    return {"ok": True, "version": ver, "changes": c["changes"]}


def _next_version(rt):
    vs = [r[0] for r in rt["store"].db.execute("SELECT version FROM onto_versions")]

    def key(v):
        return tuple(int(x) for x in str(v).split("."))
    top = max(vs, key=key)
    a, b = key(top)[:2]
    return f"{a}.{b + 1}"


def versions(rt):
    db = rt["store"].db
    out = []
    for v, at, au, rs in db.execute("SELECT version, saved_at, author, reason FROM onto_versions ORDER BY saved_at DESC, rowid DESC"):
        ch = [{"path": p, "before": json.loads(b), "after": json.loads(a)}
              for p, b, a in db.execute("SELECT path, before, after FROM onto_changes WHERE version=?", (v,))]
        out.append({"version": v, "at": at, "author": au, "reason": rs, "changes": ch})
    return out


def version_yaml(rt, v):
    r = rt["store"].db.execute("SELECT yaml FROM onto_versions WHERE version=?", (v,)).fetchone()
    return r[0] if r else None


def text_diff(a, b):
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), "이전", "새 버전", n=1))


def apply_patch(text, path, value):
    """'rules.R01_ship_shelf_life.params.C사' 같은 경로의 값을 바꾼 YAML 문자열(주석 유지)."""
    y = _ry()
    data = y.load(text)
    parts = path.split(".")
    node = data
    try:
        for i, p in enumerate(parts[:-1]):
            if isinstance(node, list):
                node = next(x for x in node if str(x.get("id")) == p)
            else:
                if p not in node:
                    node[p] = {}
                node = node[p]
        last = parts[-1]
        if isinstance(node, list):
            idx = next(i for i, x in enumerate(node) if str(x.get("id")) == last)
            node[idx] = value
        else:
            node[last] = value
    except (StopIteration, KeyError, TypeError) as e:
        return {"ok": False, "problems": [f"경로 '{path}'를 찾지 못했습니다 ({e})"]}
    buf = io.StringIO()
    y.dump(data, buf)
    return buf.getvalue()


# ===================== 쉬운 편집: 단어 정의 / 관계문 =====================
CARDS = {"1": "하나", "0..1": "없거나 하나", "N..1": "여럿이 하나에", "N..M": "여럿과 여럿", "N": "여럿", "1..5": "1~5개"}


def model(rt):
    """화면용 온톨로지 모델: 단어(객체) 정의와 관계문(연결·속성)."""
    d = yaml.safe_load(config.ONTOLOGY_FILE.read_text(encoding="utf-8"))
    store = rt["store"]
    oc = dict(store.db.execute("SELECT type, COUNT(*) FROM objects GROUP BY type").fetchall())
    lc = {}
    for st, rel, dt_, n in store.db.execute("SELECT src_type, rel, dst_type, COUNT(*) FROM links GROUP BY 1,2,3"):
        lc[(st, rel, dt_)] = n
    terms, links, props = [], [], []
    for k, o in d["objects"].items():
        src = o.get("source", {})
        terms.append({"key": k, "name": o.get("name", k), "aliases": o.get("aliases") or [],
                      "description": o.get("description", ""), "count": oc.get(k, 0),
                      "source": src.get("doctype") or ", ".join(src.get("doctypes", [])) or src.get("derived_from")
                      or ("문서: " + ", ".join(src.get("documents", [])) if src.get("documents") else ""),
                      "filter": src.get("filter", ""), "computed": list((o.get("computed") or {}).keys())})
        for i, l in enumerate(o.get("links") or []):
            tos = l["to"] if isinstance(l["to"], list) else [l["to"]]
            n = sum(v for (a, r, b), v in lc.items() if a == k and r == l["rel"] and (b in tos or "*" in tos))
            links.append({"subject": k, "index": i, "rel": l["rel"], "to": tos, "card": str(l.get("card", "")),
                          "phrase": l.get("phrase", ""),
                          "card_text": CARDS.get(str(l.get("card", "")), str(l.get("card", ""))), "via": l.get("via", ""),
                          "count": n})
        for name, field in (o.get("properties") or {}).items():
            filled = 0
            props.append({"subject": k, "name": name, "field": field})
    vals = {}
    for t, p in store.db.execute("SELECT type, props FROM objects"):
        try:
            for k2, v in json.loads(p).items():
                if v not in (None, "", []):
                    vals[(t, k2)] = vals.get((t, k2), 0) + 1
        except Exception:
            pass
    for p in props:
        p["filled"] = vals.get((p["subject"], p["name"]), 0)
    rules = [{"id": r["id"], "when": r["when"], "then": r["then"], "next": r["next"], "params": r.get("params") or {}}
             for r in d.get("rules", [])]
    return {"version": str(d["meta"]["version"]), "terms": terms, "links": links, "props": props, "rules": rules}


def apply_op(text, op):
    """편집 동작 하나를 YAML에 적용한 새 문자열. 실패하면 {'ok': False, 'problems': [...]}."""
    y = _ry()
    data = y.load(text)
    objs = data["objects"]
    kind = op.get("op")
    k = op.get("key") or op.get("subject")
    try:
        if kind == "term.update":
            o = objs[k]
            for f in ("name", "description"):
                if f in op:
                    o[f] = op[f]
            if "aliases" in op:
                o["aliases"] = [a for a in op["aliases"] if a]
        elif kind == "term.add":
            key = op["key"]
            if key in objs:
                return {"ok": False, "problems": [f"'{key}'는 이미 있는 id입니다"]}
            src = {"doctype": op["doctype"]}
            if op.get("filter"):
                src["filter"] = op["filter"]
            objs[key] = {"name": op["name"], "aliases": op.get("aliases") or [], "description": op.get("description", ""),
                         "source": src, "key": "name", "title": op.get("title") or "name", "properties": {}, "links": []}
        elif kind == "term.remove":
            if k not in objs:
                return {"ok": False, "problems": [f"'{k}' 없음"]}
            used = [f"{a}.{l['rel']}" for a, o in objs.items() if a != k for l in (o.get("links") or [])
                    if k in (l["to"] if isinstance(l["to"], list) else [l["to"]])]
            if used and not op.get("force"):
                return {"ok": False, "problems": [f"다른 관계문이 이 단어를 씁니다: {', '.join(used)}. 그 관계문을 먼저 지우거나 함께 지우기를 고르세요."]}
            for a, o in objs.items():
                if o.get("links"):
                    o["links"] = [l for l in o["links"] if k not in (l["to"] if isinstance(l["to"], list) else [l["to"]])]
            del objs[k]
        elif kind == "prop.add":
            objs[k].setdefault("properties", {})
            if objs[k]["properties"] is None:
                objs[k]["properties"] = {}
            objs[k]["properties"][op["name"]] = op["field"]
        elif kind == "prop.update":
            props = objs[k]["properties"]
            items = list(props.items())
            props.clear()
            for n, f in items:
                if n == op["name"]:
                    props[op.get("new_name") or n] = op.get("field") or f
                else:
                    props[n] = f
        elif kind == "prop.remove":
            del objs[k]["properties"][op["name"]]
        elif kind == "link.add":
            if objs[k].get("links") is None:
                objs[k]["links"] = []
            to = op["to"] if not isinstance(op["to"], list) or len(op["to"]) > 1 else op["to"][0]
            nl = {"rel": op["rel"], "to": to, "via": op["via"], "card": op.get("card", "1")}
            if op.get("phrase"):
                nl["phrase"] = op["phrase"]
            objs[k]["links"].append(nl)
        elif kind == "link.update":
            l = objs[k]["links"][int(op["index"])]
            for f in ("rel", "via", "card", "phrase"):
                if op.get(f):
                    l[f] = op[f]
            if op.get("to"):
                l["to"] = op["to"] if not isinstance(op["to"], list) or len(op["to"]) > 1 else op["to"][0]
        elif kind == "link.remove":
            del objs[k]["links"][int(op["index"])]
        else:
            return {"ok": False, "problems": [f"모르는 편집: {kind}"]}
    except (KeyError, IndexError, TypeError) as e:
        return {"ok": False, "problems": [f"편집할 곳을 찾지 못했습니다: {e}"]}
    buf = io.StringIO()
    y.dump(data, buf)
    return buf.getvalue()


def describe_op(op, m=None):
    k = op.get("key") or op.get("subject")
    return {"term.update": f"단어 '{k}' 정의 수정", "term.add": f"단어 '{op.get('name')}' 추가",
            "term.remove": f"단어 '{k}' 삭제", "prop.add": f"{k}에 속성 '{op.get('name')}' 추가",
            "prop.update": f"{k} 속성 '{op.get('name')}' 수정", "prop.remove": f"{k} 속성 '{op.get('name')}' 삭제",
            "link.add": f"관계문 추가: {k} -{op.get('rel')}→ {op.get('to')}", "link.update": f"{k} 관계문 수정",
            "link.remove": f"{k} 관계문 삭제"}.get(op.get("op"), op.get("op"))
