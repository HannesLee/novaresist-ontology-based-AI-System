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
