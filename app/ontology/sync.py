"""ERP → 온톨로지 동기화.

full()        정의 파일이 필요로 하는 ERP 화면을 전부 읽어 raw에 넣고 객체를 만든다.
on_change()   웹훅: 문서 1건을 다시 읽어 raw를 고치고 객체를 다시 만든다.
poll()        웹훅이 없을 때: 마지막 동기화 이후 바뀐 문서만 다시 읽는다.
"""
import threading
import time

from app import config
from app.ontology import schema as sch
from app.ontology.engine import Engine, Raw
from app.ontology.store import Store, now

_lock = threading.Lock()


class Sync:
    def __init__(self, store=None, erp=None, onto_path=None, graph=None, docs=None):
        self.erp = erp or config.erp()
        self.store = store or Store(config.DB_FILE)
        self.graph = graph
        self.docs = docs
        self.onto_path = onto_path or config.ONTOLOGY_FILE
        self.reload_schema()

    def reload_schema(self):
        self.schema = sch.Schema(sch.load(self.onto_path), self.erp)
        self.fetch = self.schema.fetch_list()
        self.parents = {dt for dt, par in self.fetch if not par}

    # ---------- 읽기 ----------
    def full(self, log=print):
        t0 = time.time()
        for dt, par in self.fetch:
            rows = self.erp.get_all(dt, parent=par)
            self.store.put_raw(dt, rows, replace_all=True, parent=par)
            log(f"  {dt}{' (' + par + ' 하위)' if par else ''}: {len(rows)}행")
        self.store.db.commit()
        n = self.rebuild(kind="full")
        log(f"전체 동기화 {time.time() - t0:.0f}초, 바뀐 객체 {n}개")
        return n

    def on_change(self, doctype, name):
        """웹훅으로 받은 문서 1건 반영."""
        if doctype not in self.parents:
            return 0
        doc = self.erp.get(doctype, name)
        if doc is None:  # 삭제됨
            self.store.db.execute("DELETE FROM raw WHERE doctype=? AND name=?", (doctype, name))
        else:
            kids = {f: cdt for cdt, f in self.schema.tables(doctype).items() if (cdt, doctype) in self.fetch}
            self.store.put_doc(doc, kids)
        self.store.db.commit()
        return self.rebuild(kind="webhook", doctype=doctype, name=name)

    def poll(self):
        """바뀐 문서(새로 생김·수정·삭제)만 다시 읽는다. 문서 번호와 수정 시각만 비교하므로 가볍다."""
        total, gone = 0, 0
        for dt in self.parents:
            erp_rows = {r["name"]: str(r["modified"]) for r in self.erp.get_all(dt, fields=("name", "modified"))}
            mine = {r[0]: str(r[1]) for r in self.store.db.execute("SELECT name, modified FROM raw WHERE doctype=?", (dt,))}
            kids = {f: cdt for cdt, f in self.schema.tables(dt).items() if (cdt, dt) in self.fetch}
            for name, mod in erp_rows.items():
                if mine.get(name) != mod:
                    doc = self.erp.get(dt, name)
                    if doc:
                        self.store.put_doc(doc, kids)
                        total += 1
            for name in set(mine) - set(erp_rows):
                self.store.db.execute("DELETE FROM raw WHERE doctype=? AND name=?", (dt, name))
                for cdt in kids.values():
                    self.store.db.execute("DELETE FROM raw WHERE doctype=? AND parent=? AND parenttype=?", (cdt, name, dt))
                gone += 1
        self.store.db.commit()
        if total or gone:
            return self.rebuild(kind="poll", detail=f"다시 읽음 {total}건, 삭제 {gone}건")
        return 0

    # ---------- 객체 다시 만들기 ----------
    def rebuild(self, kind="rebuild", doctype="", name="", detail=""):
        with _lock:
            raw = Raw({dt: self.store.raw_rows(dt) for dt, _ in self.fetch})
            eng = Engine(self.schema, raw)
            objects, links, aliases = eng.build()
            if self.docs is not None:  # ERP 밖 문서 → 결정·사건 객체와 '언급' 연결
                eo, el, ea = self.docs.events(objects, aliases)
                objects += eo
                links += el
                aliases += ea
            changed, removed = self.store.replace_graph(objects, links, aliases)
            if self.graph is not None:
                try:
                    self.graph.load(self.schema.d, objects, links)
                except Exception as e:  # 그래프 DB 실패가 동기화를 막지 않게
                    self.store.log("graph_error", detail=str(e)[:300])
            info = ", ".join(f"{t}:{i}" for t, i in changed[:20])
            self.store.log(kind, doctype, name, len(changed) + len(removed),
                           detail or (info + (" …" if len(changed) > 20 else "")))
            self.store.set_meta("last_sync", {"at": now(), "kind": kind, "doctype": doctype, "name": name,
                                              "changed": [list(c) for c in changed[:200]],
                                              "removed": [list(c) for c in removed[:200]]})
            return len(changed) + len(removed)
