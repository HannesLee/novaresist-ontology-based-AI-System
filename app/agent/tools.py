"""Claude에게 주는 도구.

온톨로지 모드: 함수 층(app.functions.core)의 질문 도구
ERP 모드(비교용): ERP 원시 조회 도구만 — '일반 Claude + ERP'에 해당
"""
import json

S = {"type": "string"}
SA = {"type": "array", "items": {"type": "string"}}

ONTO_TOOLS = [
    {"name": "graph_query", "description": "그래프 DB(온톨로지 그래프)에 읽기 전용 Cypher 질의. 여러 단계 연결을 한 번에 따라갈 때 쓴다. "
                                         "라벨·관계·열 이름은 시스템 프롬프트의 그래프 스키마 그대로(공백은 _). 예: "
                                         "MATCH (s:supplier)<-[:제조사]-(r:raw_lot)<-[:대상]-(:inspection)-[:측정값]->(m:measurement) "
                                         "WHERE m.항목='금속 Zn' RETURN s.이름, r.id, m.값 ORDER BY m.값 DESC LIMIT 10",
     "input_schema": {"type": "object", "properties": {"cypher": S, "params": {"type": "object"}}, "required": ["cypher"]}},
    {"name": "find", "description": "이름·코드·별칭(공급사 품명, 생산 약칭, 고객 품번, 줄임 이름 포함)으로 객체를 찾는다.",
     "input_schema": {"type": "object", "properties": {"text": S, "type": {"type": "string", "description": "객체 종류(선택): 공급사, 원재료, 원재료 lot, 완제품 lot, 구매 건, 수주 …"}},
                      "required": ["text"]}},
    {"name": "get", "description": "객체 하나의 속성, 계산 속성(실시간 재고·지연·이상치 등), 연결된 객체, 관련 문서를 본다.",
     "input_schema": {"type": "object", "properties": {"ref": {"type": "string", "description": "id 또는 이름"}, "type": S},
                      "required": ["ref"]}},
    {"name": "list_objects", "description": "한 종류 객체 목록. where로 속성 값 필터(포함 일치). 예: type='구매 건', where={'운송':'항공'}",
     "input_schema": {"type": "object", "properties": {"type": S, "where": {"type": "object"}, "limit": {"type": "integer"}},
                      "required": ["type"]}},
    {"name": "trace_back", "description": "완제품 lot 역추적: 작업지시, 공정 설비, 필터 lot, 투입 원재료 lot(공급사·입고·IQC 경계·이상치), 출하, 클레임, 현재 재고.",
     "input_schema": {"type": "object", "properties": {"fg_lot": S}, "required": ["fg_lot"]}},
    {"name": "trace_forward", "description": "원재료 lot(또는 원재료·공급사·제조일 범위 조건) → 들어간 완제품 lot, 현재 위치, 출하 고객.",
     "input_schema": {"type": "object", "properties": {"raw_lots": SA, "material": S, "supplier": S,
                                                       "mfg_from": {"type": "string", "description": "YYYY-MM-DD"}, "mfg_to": S}}},
    {"name": "common_factors", "description": "문제 완제품 lot들의 공통 요인(원재료 lot, 원재료@공급사, 설비, 필터 lot, IQC 경계·이상치)을 비교군(같은 제품 나머지 lot)과 비교.",
     "input_schema": {"type": "object", "properties": {"fg_lots": SA, "compare": SA}, "required": ["fg_lots"]}},
    {"name": "measurement_trend", "description": "원재료(·공급사)의 IQC 측정값 lot별 추이와 경계(규격 여유 20% 미만)·이상치(비교군 평균±2σ 밖). item 없으면 항목별 요약.",
     "input_schema": {"type": "object", "properties": {"material": S, "supplier": S, "item": {"type": "string", "description": "예: 금속 Zn, 수분, 분자량"},
                                                       "date_from": S, "date_to": S}, "required": ["material"]}},
    {"name": "suspect_lots", "description": "조건(원재료·공급사·제조일 범위 또는 lot 목록)에 맞는 의심 원재료 lot, 재고, 영향 완제품 lot, 출하 고객 (규칙 R08).",
     "input_schema": {"type": "object", "properties": {"material": S, "supplier": S, "mfg_from": S, "mfg_to": S, "raw_lots": SA}}},
    {"name": "shippable", "description": "완제품 lot을 고객에게 출하할 수 있는지와 사유(잔여 유효기간 R01, 출하검사, 출하 창고, 고객 승인 R02, 부적합).",
     "input_schema": {"type": "object", "properties": {"fg_lot": S, "customer": S}, "required": ["fg_lot", "customer"]}},
    {"name": "requal_needed", "description": "원재료를 새 공급사로 바꾸면 재승인이 필요한 고객·제품과 기간 (R02).",
     "input_schema": {"type": "object", "properties": {"material": S, "supplier": S}, "required": ["material", "supplier"]}},
    {"name": "shortage_forecast", "description": "원재료 재고 + 미입고 발주 − 확정 생산계획 사용량 → 월별 예상 재고, 부족 시점, 안전재고 (R04).",
     "input_schema": {"type": "object", "properties": {"material": S, "months": {"type": "integer"}}, "required": ["material"]}},
    {"name": "impacted_orders", "description": "원재료 지연(material) 또는 설비 중단(equipment, 기간)으로 영향받는 작업지시·수주.",
     "input_schema": {"type": "object", "properties": {"material": S, "delay_days": {"type": "integer"}, "equipment": S,
                                                       "date_from": S, "date_to": S}}},
    {"name": "make_table", "description": "엑셀·파워포인트로 내보낼 표(자료)를 만든다. 사용자가 '표/자료/보고서 만들어줘'라고 하면 쓴다. "
                                        "sources에는 쓸 데이터(온톨로지 객체 종류 이름 예: '구매 건','원재료','완제품 lot', 또는 ERP 화면 예: 'Purchase Order')를, "
                                        "request에는 만들 표를 구체적으로 적는다(정렬·필터·상위 N·열). 계산은 코드로 하므로 숫자가 정확하다.",
     "input_schema": {"type": "object", "properties": {"sources": SA, "request": S}, "required": ["sources", "request"]}},
    {"name": "search_docs", "description": "ERP 밖 문서(메일, 회의록, 결정 기록, SOP, 운영 규칙집)를 키워드로 찾는다.",
     "input_schema": {"type": "object", "properties": {"query": S}, "required": ["query"]}},
    {"name": "read_doc", "description": "문서 본문 읽기 (search_docs 또는 get의 '관련 문서'에 나온 경로).",
     "input_schema": {"type": "object", "properties": {"path": S}, "required": ["path"]}},
]

ERP_TOOLS = [
    {"name": "erp_doctypes", "description": "ERP에서 쓸 수 있는 화면(doctype) 목록과 주요 필드.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "erp_list", "description": "ERPNext 목록 조회 (frappe.client.get_list). 하위 표(예: Purchase Order Item)는 parent에 상위 화면 이름을 준다.",
     "input_schema": {"type": "object", "properties": {
         "doctype": S, "filters": {"type": "array", "description": "[[필드, 연산자, 값], …] 예: [['supplier','=','BP-KR01']]"},
         "fields": SA, "parent": S, "limit": {"type": "integer"}, "order_by": S}, "required": ["doctype"]}},
    {"name": "erp_get", "description": "ERPNext 문서 1건 전체(하위 표 포함).",
     "input_schema": {"type": "object", "properties": {"doctype": S, "name": S}, "required": ["doctype", "name"]}},
    {"name": "erp_batch_qty", "description": "품목의 lot별·창고별 현재 재고.",
     "input_schema": {"type": "object", "properties": {"item_code": S}, "required": ["item_code"]}},
]

DOC_TOOLS = [t for t in ONTO_TOOLS if t["name"] in ("search_docs", "read_doc")]

ERP_DOCTYPES = ["Supplier", "Item", "Item Supplier", "Material Request", "Purchase Order", "Purchase Order Item",
                "Purchase Receipt", "Purchase Receipt Item", "Batch", "Quality Inspection", "Quality Inspection Reading",
                "Work Order", "Job Card", "Stock Entry", "Stock Entry Detail", "BOM", "BOM Item", "Workstation",
                "Downtime Entry", "Non Conformance", "Customer", "NR Customer Approval", "Sales Order", "Sales Order Item",
                "Delivery Note", "Delivery Note Item", "NR Sales Forecast", "NR Production Plan", "Bin", "Warehouse"]


def run(rt, mode, name, args):
    """도구 실행 → 결과(dict/list)."""
    o = rt["onto"]
    if name == "make_table":
        return make_table(rt, args.get("sources") or [], args.get("request", ""))
    if mode == "ontology" or name in ("search_docs", "read_doc"):
        fn = getattr(o, name, None)
        if fn is None or name.startswith("_"):
            return {"오류": f"도구 '{name}' 없음"}
        return fn(**args)
    e = rt["erp"]
    if name == "erp_doctypes":
        out = {}
        for dt in ERP_DOCTYPES:
            m = e.meta(dt)
            out[dt] = [f["fieldname"] for f in m["fields"]
                       if f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break", "HTML")][:40]
        return out
    if name == "erp_list":
        a = {"doctype": args["doctype"], "fields": args.get("fields") or ["name"],
             "limit_page_length": args.get("limit", 100)}
        for k in ("filters", "parent", "order_by"):
            if args.get(k):
                a[k] = args[k]
        return e.call_post("frappe.client.get_list", **a)
    if name == "erp_get":
        return e.get(args["doctype"], args["name"]) or {"오류": "없음"}
    if name == "erp_batch_qty":
        return e.call("erpnext.stock.doctype.batch.batch.get_batch_qty", item_code=args["item_code"], for_stock_levels=1)
    return {"오류": f"도구 '{name}' 없음"}


def dumps(x, limit=14000):
    s = json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + f" …(잘림, 전체 {len(s)}자. 조건을 좁혀 다시 조회)"


def make_table(rt, sources, request):
    """대화에서 자료 만들기: 데이터 카드를 만들고 작업대 계산기로 표를 만든다."""
    from app.board import board as B
    ids = []
    for src in sources:
        t = rt["onto"].resolve_type(src)
        spec = {"source": "onto", "type": t, "title": rt["schema"]["objects"][t]["name"]} if t else \
            {"source": "erp", "doctype": src, "title": src}
        c = B.add_card(rt, spec)
        if c.get("error"):
            return {"오류": f"데이터 '{src}'를 읽지 못했습니다: {c['error']}"}
        ids.append(c["id"])
    r = B.make(rt, ids, request)
    if r.get("error"):
        return {"오류": r["error"]}
    return {"표": r["title"], "card_id": r["id"], "열": r["columns"], "행 수": r["total"],
            "미리보기": r["rows"][:12], "계산 방법": r.get("note", ""), "차트": r.get("chart")}
