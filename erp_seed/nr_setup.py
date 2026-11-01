"""1단계: ERPNext 기본 설정 + 추가 필드(Custom Field) + 추가 화면(Custom DocType).

ERPNext 기본 화면에 없는 정보(품의번호, 경유 에이전시, 공급사 회신 납기, ERP 입력일 등)를
추가 필드로 만든다. 고객 승인·판매 예측·월별 생산계획은 추가 화면으로 만든다.
"""
from erp_client import ERPError

COMPANY = "NovaResist Co., Ltd."
ABBR = "NR"

# (DocType, fieldname, label, fieldtype, options, insert_after)
CUSTOM_FIELDS = [
    # 품목
    ("Item", "custom_production_alias", "생산 약칭", "Data", None, "item_name"),
    ("Item", "custom_sub_category", "세부 분류", "Data", None, "item_group"),
    ("Item", "custom_storage_condition", "보관 조건", "Data", None, "custom_sub_category"),
    ("Item", "custom_safety_stock_months", "안전재고 정책(개월)", "Float", None, "safety_stock"),
    ("Item", "custom_hazardous", "위험물", "Check", None, "custom_storage_condition"),
    ("Item", "custom_density", "밀도(g/mL)", "Float", None, "custom_hazardous"),
    ("Item", "custom_qc_warehouse", "IQC 전 입고 창고", "Link", "Warehouse", "custom_density"),
    ("Item", "custom_pass_warehouse", "합격 창고", "Link", "Warehouse", "custom_qc_warehouse"),
    ("Item", "custom_solid_pct", "고형분(%)", "Float", None, "custom_pass_warehouse"),
    ("Item", "custom_annual_plan_bottles", "연 판매 계획(병)", "Int", None, "custom_solid_pct"),
    # 공급사·고객
    ("Supplier", "custom_bp_category", "공급 분류", "Data", None, "supplier_group"),
    ("Supplier", "custom_agency", "경유 에이전시", "Link", "Supplier", "custom_bp_category"),
    ("Supplier", "custom_incoterms", "인코텀즈", "Data", None, "custom_agency"),
    ("Supplier", "custom_payment_terms_text", "결제 조건", "Data", None, "custom_incoterms"),
    ("Supplier", "custom_rating", "평가 등급", "Data", None, "custom_payment_terms_text"),
    ("Supplier", "custom_std_lead_time", "표준 리드타임(일)", "Int", None, "custom_rating"),
    ("Supplier", "custom_customs_days", "평균 통관 일수(에이전시)", "Int", None, "custom_std_lead_time"),
    ("Customer", "custom_requal_days", "원재료 변경 시 재승인(일)", "Int", None, "customer_group"),
    ("Customer", "custom_min_shelf_life_days", "출하 가능 잔여 유효기간(일)", "Int", None, "custom_requal_days"),
    ("Customer", "custom_sales_share", "매출 비중", "Data", None, "custom_min_shelf_life_days"),
    # 설비
    ("Workstation", "custom_capacity", "용량(L) 또는 처리량", "Float", None, "workstation_type"),
    ("Workstation", "custom_pm_cycle_days", "정비 주기(일)", "Int", None, "custom_capacity"),
    # Batch(lot)
    ("Batch", "custom_supplier_lot", "공급사 lot", "Data", None, "batch_id"),
    # 구매요청
    ("Material Request", "custom_request_dept", "요청 부서", "Data", None, "material_request_type"),
    ("Material Request", "custom_request_reason", "요청 사유", "Data", None, "custom_request_dept"),
    # 발주(품의)
    ("Purchase Order", "custom_approval_no", "품의번호", "Data", None, "supplier"),
    ("Purchase Order", "custom_approval_submitted", "품의 상신일", "Date", None, "custom_approval_no"),
    ("Purchase Order", "custom_approval_date", "품의 승인일", "Date", None, "custom_approval_submitted"),
    ("Purchase Order", "custom_approver", "승인자", "Data", None, "custom_approval_date"),
    ("Purchase Order", "custom_agency", "경유 에이전시", "Link", "Supplier", "custom_approver"),
    ("Purchase Order", "custom_supplier_confirmed_date", "공급사 회신 납기", "Date", None, "schedule_date"),
    ("Purchase Order", "custom_transport", "운송", "Data", None, "custom_supplier_confirmed_date"),
    ("Purchase Order", "custom_note", "비고", "Small Text", None, "custom_transport"),
    # 입고
    ("Purchase Receipt", "custom_erp_entry_date", "ERP 입력일", "Date", None, "posting_date"),
    ("Purchase Receipt", "custom_coa_attached", "COA 첨부", "Check", None, "custom_erp_entry_date"),
    ("Purchase Receipt", "custom_supplier_lot", "공급사 lot", "Data", None, "custom_coa_attached"),
    ("Purchase Receipt", "custom_po_ref", "발주번호(수기)", "Data", None, "custom_supplier_lot"),
    # 검사
    ("Quality Inspection", "custom_category", "검사 구분", "Data", None, "inspection_type"),
    ("Quality Inspection", "custom_requested_at", "의뢰 일시", "Datetime", None, "report_date"),
    ("Quality Inspection", "custom_started_at", "검사 시작 일시", "Datetime", None, "custom_requested_at"),
    ("Quality Inspection", "custom_decided_at", "판정 일시", "Datetime", None, "custom_started_at"),
    ("Quality Inspection", "custom_erp_entry_at", "ERP 입력 일시", "Datetime", None, "custom_decided_at"),
    ("Quality Inspection", "custom_inspector", "검사자", "Data", None, "inspected_by"),
    ("Quality Inspection", "custom_supplier", "공급사", "Link", "Supplier", "custom_inspector"),
    # 작업지시·작업카드
    ("Work Order", "custom_batch_size_l", "배치량(L)", "Float", None, "qty"),
    ("Work Order", "custom_mix_tank", "배합 탱크", "Link", "Workstation", "custom_batch_size_l"),
    ("Work Order", "custom_wo_type", "구분(정규/샘플)", "Data", None, "custom_mix_tank"),
    ("Work Order", "custom_linked_so", "연결 수주", "Data", None, "custom_wo_type"),  # 샘플 WO가 수주보다 먼저 생기기도 해서 Data
    ("Work Order", "custom_fg_lot", "완제품 lot", "Link", "Batch", "custom_linked_so"),
    ("Work Order", "custom_yield_pct", "수율(%)", "Float", None, "custom_fg_lot"),
    ("Work Order", "custom_actual_start", "실제 시작일", "Date", None, "planned_start_date"),
    ("Work Order", "custom_actual_end", "실제 종료일", "Date", None, "custom_actual_start"),
    ("Work Order", "custom_planned_end", "계획 종료일", "Date", None, "custom_actual_end"),
    ("Work Order", "custom_migration_note", "이관 메모", "Small Text", None, "custom_yield_pct"),
    ("Job Card", "custom_filter_lot", "사용 필터 lot", "Data", None, "workstation"),
    ("Job Card", "custom_crew", "작업조", "Data", None, "custom_filter_lot"),
    # 수주·출하
    ("Sales Order", "custom_urgent", "긴급", "Check", None, "customer"),
    ("Sales Order", "custom_note", "비고", "Small Text", None, "custom_urgent"),
    ("Delivery Note", "custom_erp_entry_date", "ERP 입력일", "Date", None, "posting_date"),
    ("Delivery Note Item", "custom_remaining_shelf_life_days", "출하 시 잔여 유효기간(일)", "Int", None, "batch_no"),
    ("Delivery Note Item", "custom_on_time", "납기 준수", "Data", None, "custom_remaining_shelf_life_days"),
    # 부적합(NCR)
    ("Non Conformance", "custom_category", "구분", "Data", None, "subject"),
    ("Non Conformance", "custom_occurred_on", "발생일", "Date", None, "custom_category"),
    ("Non Conformance", "custom_lot", "관련 lot", "Link", "Batch", "custom_occurred_on"),
    ("Non Conformance", "custom_item", "품목", "Link", "Item", "custom_lot"),
    ("Non Conformance", "custom_customer", "고객", "Link", "Customer", "custom_item"),
    ("Non Conformance", "custom_cause", "원인", "Small Text", None, "custom_customer"),
    ("Non Conformance", "custom_closed_on", "종결일", "Date", None, "custom_cause"),
]

# 생산이 끝난 뒤에 채우는 값 (제출 후 수정 허용)
ALLOW_ON_SUBMIT = {("Work Order", "custom_actual_start"), ("Work Order", "custom_actual_end"),
                   ("Work Order", "custom_yield_pct"), ("Work Order", "custom_fg_lot")}

CUSTOM_DOCTYPES = [
    {
        "name": "NR Customer Approval", "label": "고객 승인",
        "fields": [
            ("customer", "고객", "Link", "Customer", 1),
            ("item", "SKU", "Link", "Item", 1),
            ("customer_item_code", "고객 품번", "Data", None, 0),
            ("approval_date", "승인일", "Date", None, 0),
            ("approved_materials", "승인된 원재료@공급사", "Small Text", None, 0),
        ],
    },
    {
        "name": "NR Sales Forecast", "label": "판매 예측(3개월 롤링)",
        "fields": [
            ("version", "버전", "Data", None, 1),
            ("created_on", "작성일", "Date", None, 0),
            ("customer", "고객", "Link", "Customer", 1),
            ("item", "SKU", "Link", "Item", 1),
            ("target_month", "대상월", "Data", None, 1),
            ("qty_bottles", "예측 수량(병)", "Int", None, 0),
        ],
    },
    {
        "name": "NR Production Plan", "label": "월별 생산계획(생판회의)",
        "fields": [
            ("plan_month", "계획월", "Data", None, 1),
            ("sop_version", "생판회의 버전", "Data", None, 0),
            ("item", "SKU", "Link", "Item", 1),
            ("qty_bottles", "계획 수량(병)", "Int", None, 0),
            ("plan_status", "구분", "Data", None, 0),
        ],
    },
]

# 이관 중에는 문서번호를 원본 번호(PO-26-0001 등) 그대로 쓰기 위해 '직접 입력(Prompt)' 방식으로 바꾼다.
PROMPT_NAMED = ["Supplier", "Customer", "Material Request", "Purchase Order", "Purchase Receipt",
                "Quality Inspection", "Work Order", "Stock Entry", "Sales Order", "Delivery Note",
                "Stock Reconciliation", "Non Conformance", "Downtime Entry", "BOM"]


def ensure(erp, doctype, name, doc, log):
    if erp.exists(doctype, name):
        return False
    d = dict(doc)
    d["doctype"] = doctype
    erp.insert(d)
    log(f"  + {doctype}: {name}")
    return True


def run(erp, log=print):
    log("[1/4] 기본 설정")
    # 회계연도 2025 (2025년에 낸 발주·수주를 이관하기 위해)
    if not erp.exists("Fiscal Year", "2025"):
        erp.insert({"doctype": "Fiscal Year", "year": "2025", "year_start_date": "2025-01-01",
                    "year_end_date": "2025-12-31", "companies": [{"company": COMPANY}]})
        log("  + Fiscal Year 2025")

    erp.set_single("Stock Settings", {
        "enable_serial_and_batch_no_for_item": 1,
        "allow_to_make_quality_inspection_after_purchase_or_delivery": 1,
        "use_serial_batch_fields": 1,
        "disable_serial_no_and_batch_selector": 1,
        "over_delivery_receipt_allowance": 10,
        "allow_negative_stock": 0,
        "valuation_method": "Moving Average",
    })
    erp.set_single("Selling Settings", {"so_required": "No", "dn_required": "No",
                                        "allow_multiple_items": 1, "cust_master_name": "Customer Name"})
    erp.set_single("Buying Settings", {"po_required": "No", "pr_required": "No", "allow_multiple_items": 1})
    erp.set_single("System Settings", {"float_precision": "3", "currency_precision": "0",
                                       "date_format": "yyyy-mm-dd", "time_zone": "Asia/Seoul"})

    # 단위
    for uom, whole in [("EA", 1), ("병", 1)]:
        ensure(erp, "UOM", uom, {"uom_name": uom, "must_be_whole_number": whole}, log)

    log("[2/4] 추가 필드")
    existing = {(d["dt"], d["fieldname"]) for d in erp.get_list("Custom Field", fields=["dt", "fieldname"])}
    for dt, fn, label, ft, opt, after in CUSTOM_FIELDS:
        if (dt, fn) in existing:
            continue
        doc = {"doctype": "Custom Field", "dt": dt, "fieldname": fn, "label": label, "fieldtype": ft,
               "insert_after": after}
        if opt:
            doc["options"] = opt
        if (dt, fn) in ALLOW_ON_SUBMIT:
            doc["allow_on_submit"] = 1
        erp.insert(doc)
        log(f"  + {dt}.{fn}")

    log("[3/4] 추가 화면")
    for spec in CUSTOM_DOCTYPES:
        if erp.exists("DocType", spec["name"]):
            continue
        fields = []
        for fn, label, ft, opt, reqd in spec["fields"]:
            f = {"fieldname": fn, "label": label, "fieldtype": ft, "reqd": reqd, "in_list_view": 1,
                 "in_standard_filter": 1 if ft in ("Link", "Data") else 0}
            if opt:
                f["options"] = opt
            fields.append(f)
        erp.insert({"doctype": "DocType", "name": spec["name"], "module": "Stock", "custom": 1,
                    "autoname": "hash", "fields": fields, "track_changes": 1, "allow_import": 1,
                    "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1,
                                     "delete": 1, "export": 1, "report": 1, "import": 1},
                                    {"role": "Stock User", "read": 1, "report": 1, "export": 1}],
                    "description": spec["label"]})
        log(f"  + DocType {spec['name']} ({spec['label']})")

    log("[4/4] 문서번호 원본 유지 설정")
    set_prompt_naming(erp, True, log)


def set_prompt_naming(erp, on, log=print):
    ps = {d["doc_type"]: d["name"] for d in erp.get_list(
        "Property Setter", filters=[["property", "=", "autoname"]], fields=["name", "doc_type"])}
    for dt in PROMPT_NAMED:
        if on and dt not in ps:
            erp.insert({"doctype": "Property Setter", "doctype_or_field": "DocType", "doc_type": dt,
                        "property": "autoname", "value": "Prompt", "property_type": "Data"})
            log(f"  + {dt}: 번호 직접 지정")
        elif not on and dt in ps:
            erp.delete("Property Setter", ps[dt])
            log(f"  - {dt}: 번호 자동 채번으로 복구")
