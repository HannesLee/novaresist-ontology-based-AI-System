"""프로그램 전체가 함께 쓰는 객체(저장소·정의·ERP·문서·함수)."""
from app import config
from app.functions.core import Onto, today
from app.ontology import schema as sch
from app.ontology.docs import Docs
from app.ontology.graphdb import GraphDB
from app.ontology.store import Store

_rt = {}


def get():
    if not _rt:
        store = Store(config.DB_FILE)
        erp = config.erp()
        d = sch.load(config.ONTOLOGY_FILE)
        docs = Docs(config.DOCS_DIR, store, today)
        graph = GraphDB(config.GRAPH_DIR)
        _rt.update(store=store, erp=erp, schema=d, docs=docs, graph=graph, onto=Onto(store, d, erp, docs, graph))
    return _rt


def reload_schema():
    rt = get()
    rt["schema"] = sch.load(config.ONTOLOGY_FILE)
    rt["onto"] = Onto(rt["store"], rt["schema"], rt["erp"], rt["docs"], rt["graph"])
    return rt
