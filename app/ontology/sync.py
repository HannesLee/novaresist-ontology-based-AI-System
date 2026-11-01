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
    def __init__(self, store=None, erp=None, onto_path=None):
        self.erp = erp or config.erp()
        self.store = store or Store(config.DB_FILE)
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
        """마지막 동기화 이후 modified가 바뀐 문서만 다시 읽는다."""
        last = self.store.raw_doctypes()
        total = 0
        for dt in self.parents:
            since = last.get(dt)
            flt = [["modified", ">", since]] if since else None
            for r in self.erp.get_all(dt, filters=flt, fields=("name",)):
                doc = self.erp.get(dt, r["name"])
                kids = {f: cdt for cdt, f in self.schema.tables(dt).items() if (cdt, dt) in self.fetch}
                self.store.put_doc(doc, kids)
                total += 1
        self.store.db.commit()
        return self.rebuild(kind="poll", detail=f"{total}건 다시 읽음") if total else 0

    # ---------- 객체 다시 만들기 ----------
    def rebuild(self, kind="rebuild", doctype="", name="", detail=""):
        with _lock:
            raw = Raw({dt: self.store.raw_rows(dt) for dt, _ in self.fetch})
            eng = Engine(self.schema, raw)
            objects, links, aliases = eng.build()
            changed, removed = self.store.replace_graph(objects, links, aliases)
            info = ", ".join(f"{t}:{i}" for t, i in changed[:20])
            self.store.log(kind, doctype, name, len(changed) + len(removed),
                           detail or (info + (" …" if len(changed) > 20 else "")))
            self.store.set_meta("last_sync", {"at": now(), "kind": kind, "doctype": doctype, "name": name,
                                              "changed": [list(c) for c in changed[:200]],
                                              "removed": [list(c) for c in removed[:200]]})
            return len(changed) + len(removed)
