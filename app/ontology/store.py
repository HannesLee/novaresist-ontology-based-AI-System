"""SQLite 저장소.

raw        ERP 원본 행(문서·하위 표). 웹훅이 오면 이 표만 고치고 객체를 다시 만든다.
objects    온톨로지 객체          links    객체 사이 연결
aliases    객체를 부르는 이름들    facts    문서에서 꺼낸 사실
sync_log   갱신 기록              onto_versions / onto_changes   정의 수정 이력
"""
import json
import re
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw (doctype TEXT, name TEXT, parent TEXT, parenttype TEXT, modified TEXT, data TEXT,
    PRIMARY KEY (doctype, name));
CREATE INDEX IF NOT EXISTS raw_parent ON raw (doctype, parent);
CREATE TABLE IF NOT EXISTS objects (type TEXT, id TEXT, title TEXT, props TEXT, src_doctype TEXT, src_name TEXT,
    status TEXT, hash TEXT, updated_at TEXT, PRIMARY KEY (type, id));
CREATE TABLE IF NOT EXISTS links (src_type TEXT, src_id TEXT, rel TEXT, dst_type TEXT, dst_id TEXT, props TEXT);
CREATE INDEX IF NOT EXISTS links_src ON links (src_type, src_id);
CREATE INDEX IF NOT EXISTS links_dst ON links (dst_type, dst_id);
CREATE TABLE IF NOT EXISTS aliases (type TEXT, id TEXT, alias TEXT, norm TEXT);
CREATE INDEX IF NOT EXISTS aliases_norm ON aliases (norm);
CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY AUTOINCREMENT, subject_type TEXT, subject_id TEXT,
    predicate TEXT, value TEXT, since TEXT, source TEXT, confidence TEXT, status TEXT DEFAULT '미검토',
    reviewer TEXT, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS sync_log (at TEXT, kind TEXT, doctype TEXT, name TEXT, changed INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS onto_versions (version TEXT PRIMARY KEY, saved_at TEXT, author TEXT, reason TEXT, yaml TEXT);
CREATE TABLE IF NOT EXISTS onto_changes (version TEXT, path TEXT, before TEXT, after TEXT);
"""


def norm(s):
    """별칭 비교용: 소문자, 공백·하이픈·밑줄·괄호 제거."""
    return re.sub(r"[\s\-_()（）·.]", "", str(s)).lower()


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---------- raw ----------
    def put_raw(self, doctype, rows, replace_all=False, parent=None):
        if replace_all:
            if parent:
                self.db.execute("DELETE FROM raw WHERE doctype=? AND parenttype=?", (doctype, parent))
            else:
                self.db.execute("DELETE FROM raw WHERE doctype=?", (doctype,))
        self.db.executemany(
            "INSERT OR REPLACE INTO raw VALUES (?,?,?,?,?,?)",
            [(doctype, r["name"], r.get("parent"), r.get("parenttype"), r.get("modified"),
              json.dumps(r, ensure_ascii=False, default=str)) for r in rows])

    def put_doc(self, doc, child_tables):
        """문서 1건(하위 표 포함)을 바꿔 넣는다. child_tables: {fieldname: child doctype}"""
        dt = doc["doctype"]
        main = {k: v for k, v in doc.items() if not isinstance(v, list)}
        self.put_raw(dt, [main])
        for field, cdt in child_tables.items():
            self.db.execute("DELETE FROM raw WHERE doctype=? AND parent=? AND parenttype=?", (cdt, doc["name"], dt))
            self.put_raw(cdt, doc.get(field) or [])

    def raw_rows(self, doctype):
        return [json.loads(r[0]) for r in self.db.execute("SELECT data FROM raw WHERE doctype=?", (doctype,))]

    def raw_doctypes(self):
        return {r[0]: r[1] for r in self.db.execute("SELECT doctype, MAX(modified) FROM raw GROUP BY doctype")}

    # ---------- 객체 ----------
    def replace_graph(self, objects, links, aliases):
        """객체·연결·별칭을 통째로 바꾸고, 바뀐 객체 목록을 돌려준다."""
        old = {(r[0], r[1]): r[2] for r in self.db.execute("SELECT type, id, hash FROM objects")}
        t = now()
        changed = []
        rows = []
        for o in objects:
            h = o["hash"]
            k = (o["type"], o["id"])
            if old.get(k) != h:
                changed.append(k)
            rows.append((o["type"], o["id"], o["title"], json.dumps(o["props"], ensure_ascii=False, default=str),
                         o.get("src_doctype"), o.get("src_name"), o.get("status"), h, t))
        removed = set(old) - {(o["type"], o["id"]) for o in objects}
        with self.db:
            self.db.execute("DELETE FROM objects")
            self.db.executemany("INSERT INTO objects VALUES (?,?,?,?,?,?,?,?,?)", rows)
            self.db.execute("DELETE FROM links")
            self.db.executemany("INSERT INTO links VALUES (?,?,?,?,?,?)",
                                [(l["src_type"], l["src_id"], l["rel"], l["dst_type"], l["dst_id"],
                                  json.dumps(l.get("props") or {}, ensure_ascii=False, default=str)) for l in links])
            self.db.execute("DELETE FROM aliases")
            self.db.executemany("INSERT INTO aliases VALUES (?,?,?,?)",
                                [(a[0], a[1], a[2], norm(a[2])) for a in aliases])
        return changed, sorted(removed)

    def obj(self, type_, id_):
        r = self.db.execute("SELECT * FROM objects WHERE type=? AND id=?", (type_, id_)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["props"] = json.loads(d["props"])
        return d

    def objs(self, type_):
        out = []
        for r in self.db.execute("SELECT * FROM objects WHERE type=?", (type_,)):
            d = dict(r)
            d["props"] = json.loads(d["props"])
            out.append(d)
        return out

    def links_from(self, type_, id_, rel=None):
        q = "SELECT * FROM links WHERE src_type=? AND src_id=?" + (" AND rel=?" if rel else "")
        return [dict(r, props=json.loads(r["props"])) for r in self.db.execute(q, (type_, id_, rel) if rel else (type_, id_))]

    def links_to(self, type_, id_, rel=None):
        q = "SELECT * FROM links WHERE dst_type=? AND dst_id=?" + (" AND rel=?" if rel else "")
        return [dict(r, props=json.loads(r["props"])) for r in self.db.execute(q, (type_, id_, rel) if rel else (type_, id_))]

    def counts(self):
        o = dict(self.db.execute("SELECT type, COUNT(*) FROM objects GROUP BY type").fetchall())
        l = dict(self.db.execute("SELECT src_type||' -'||rel||'→ '||dst_type, COUNT(*) FROM links GROUP BY 1").fetchall())
        return o, l

    def log(self, kind, doctype="", name="", changed=0, detail=""):
        with self.db:
            self.db.execute("INSERT INTO sync_log VALUES (?,?,?,?,?,?)", (now(), kind, doctype, name, changed, detail))

    def set_meta(self, k, v):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, json.dumps(v, ensure_ascii=False)))

    def get_meta(self, k, default=None):
        r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else default
