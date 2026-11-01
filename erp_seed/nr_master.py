"""2단계: 기준정보 (창고, 품목그룹, 공급사, 에이전시, 고객, 품목, 설비, 공정, 검사 기준, 레시피(BOM), 고객 승인)."""
import csv
import os

from nr_setup import ABBR, COMPANY

UOM = {"kg": "Kg", "L": "Litre", "EA": "EA", "병": "병"}
COUNTRY = {"JP": "Japan", "KR": "Korea, Republic of", "CN": "China", "US": "United States", "DE": "Germany"}
WIP = f"WH-WIP - {ABBR}"


def wh(code):
    return f"{code} - {ABBR}"


def read(data_dir, sub, name):
    with open(os.path.join(data_dir, sub, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(x, default=None):
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return default


class Master:
    def __init__(self, erp, data_dir, log=print):
        self.erp, self.d, self.log = erp, data_dir, log
        self.m = {k: read(data_dir, "master", k + ".csv") for k in
                  ["agency", "bom", "customer", "customer_approval", "item_fg", "item_raw", "item_supplier",
                   "operation", "qc_template", "supplier", "warehouse", "workstation"]}

    def ensure(self, doctype, name, doc):
        if self.erp.exists(doctype, name):
            return False
        d = dict(doc)
        d["doctype"] = doctype
        self.erp.insert(d)
        return True

    def run(self):
        L = self.log
        L("[기준정보] 창고")
        self.warehouses()
        L("[기준정보] 그룹·직원·품질 절차")
        self.groups()
        L("[기준정보] 공급사·에이전시")
        self.suppliers()
        L("[기준정보] 고객")
        self.customers()
        L("[기준정보] 검사 기준")
        self.qc_templates()
        L("[기준정보] 품목(원재료 54, 완제품 24)")
        self.items()
        L("[기준정보] 설비·공정")
        self.workstations()
        L("[기준정보] 레시피(BOM)")
        self.boms()
        L("[기준정보] 고객 승인")
        self.approvals()
        L("[기준정보] 제조 설정")
        self.manufacturing_settings()

    # ---------------- 창고 ----------------
    def warehouses(self):
        parent = f"All Warehouses - {ABBR}"
        for r in self.m["warehouse"]:
            if self.ensure("Warehouse", wh(r["창고 코드"]), {
                "warehouse_name": r["창고 코드"], "company": COMPANY, "parent_warehouse": parent,
                "warehouse_type": None}):
                self.log(f"  + {r['창고 코드']} {r['창고명']}")
        self.ensure("Warehouse", WIP, {"warehouse_name": "WH-WIP", "company": COMPANY,
                                       "parent_warehouse": parent})
        # 창고 설명은 주소 필드 대신 별도 기록이 없어서 이름 옆 설명을 Warehouse의 'address_line_1'에 둔다
        for r in self.m["warehouse"]:
            self.erp.set_value("Warehouse", wh(r["창고 코드"]), {
                "address_line_1": f"{r['창고명']} / {r['보관 대상']}"[:140],
                "address_line_2": f"{r['온도 조건']} / 재고 상태: {r['재고 상태']}"[:140]})
        self.erp.set_value("Warehouse", WIP, {"address_line_1": "공정 재공(배합 탱크·충전 라인 투입분)"})

    # ---------------- 그룹 ----------------
    def groups(self):
        ig = "All Item Groups"
        self.ensure("Item Group", "원재료", {"item_group_name": "원재료", "parent_item_group": ig, "is_group": 1})
        for g in ["레진", "PAG", "솔벤트", "첨가제"]:
            self.ensure("Item Group", g, {"item_group_name": g, "parent_item_group": "원재료"})
        self.ensure("Item Group", "포장재", {"item_group_name": "포장재", "parent_item_group": ig})
        self.ensure("Item Group", "완제품", {"item_group_name": "완제품", "parent_item_group": ig, "is_group": 1})
        for g in sorted({r["제품군"] for r in self.m["item_fg"]}):
            self.ensure("Item Group", g, {"item_group_name": g, "parent_item_group": "완제품"})
        for g in sorted({r["공급 분류"] for r in self.m["supplier"]} | {"에이전시"}):
            self.ensure("Supplier Group", g, {"supplier_group_name": g, "parent_supplier_group": "All Supplier Groups"})
        for g in sorted({r["업종"] for r in self.m["customer"]}):
            self.ensure("Customer Group", g, {"customer_group_name": g, "parent_customer_group": "All Customer Groups"})
        # 설비 중단 기록에 필요한 담당자(정비팀), 작업조
        for first in ["정비팀", "생산1조", "생산2조"]:
            if not self.erp.get_list("Employee", filters=[["first_name", "=", first]]):
                self.erp.insert({"doctype": "Employee", "first_name": first, "gender": "Other",
                                 "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
                                 "company": COMPANY, "status": "Active"})
        # 부적합 보고서가 연결할 품질 절차(= SOP)
        for p in ["SOP-02 입고·IQC", "SOP-04 출하검사와 출하", "SOP-05 고객 클레임 대응"]:
            self.ensure("Quality Procedure", p, {"quality_procedure_name": p})

    # ---------------- 공급사 ----------------
    def suppliers(self):
        for a in self.m["agency"]:
            self.ensure("Supplier", a["에이전시 코드"], {
                "name": a["에이전시 코드"], "supplier_name": a["에이전시명"], "supplier_group": "에이전시",
                "supplier_type": "Company", "country": COUNTRY.get(a["국가"]),
                "custom_customs_days": int(num(a["평균 통관 일수"], 0))})
        for s in self.m["supplier"]:
            self.ensure("Supplier", s["BP 코드"], {
                "name": s["BP 코드"], "supplier_name": s["BP명"], "supplier_group": s["공급 분류"],
                "supplier_type": "Company", "country": COUNTRY.get(s["국가"]),
                "custom_bp_category": s["공급 분류"], "custom_agency": s["경유 에이전시"] or None,
                "custom_incoterms": s["인코텀즈"], "custom_payment_terms_text": s["결제 조건"],
                "custom_rating": s["평가 등급"], "custom_std_lead_time": int(num(s["표준 리드타임(일)"], 0))})

    def customers(self):
        for c in self.m["customer"]:
            self.ensure("Customer", c["고객 코드"], {
                "name": c["고객 코드"], "customer_name": c["고객명"], "customer_group": c["업종"],
                "customer_type": "Company", "territory": "All Territories",
                "custom_requal_days": int(num(c["원재료 변경 시 재승인(일)"], 0)),
                "custom_min_shelf_life_days": int(num(c["출하 가능 잔여 유효기간(일)"], 0)),
                "custom_sales_share": c["매출 비중"]})

    # ---------------- 검사 기준 ----------------
    def qc_templates(self):
        rows = self.m["qc_template"]
        for p in sorted({r["검사 항목"] for r in rows}):
            self.ensure("Quality Inspection Parameter", p, {"parameter": p})
        by = {}
        for r in rows:
            by.setdefault(r["템플릿"], []).append(r)
        for t, rs in by.items():
            params = []
            for r in rs:
                lo, hi = num(r["하한"]), num(r["상한"])
                numeric = 1 if (lo is not None or hi is not None) else 0
                p = {"specification": r["검사 항목"], "numeric": numeric}
                if numeric:
                    p["min_value"] = lo if lo is not None else -1e9
                    p["max_value"] = hi if hi is not None else 1e9
                else:
                    p["value"] = "적합"
                params.append(p)
            self.ensure("Quality Inspection Template", t, {
                "quality_inspection_template_name": t, "item_quality_inspection_parameter": params})

    # ---------------- 품목 ----------------
    def items(self):
        sup = {}
        for r in self.m["item_supplier"]:
            sup.setdefault(r["품목코드"], []).append(r)
        tmpl = {"레진": "IQC-레진", "PAG": "IQC-PAG", "솔벤트": "IQC-솔벤트", "첨가제": "IQC-첨가제", "포장재": "IQC-포장재"}
        for r in self.m["item_raw"]:
            code = r["품목코드"]
            rows = sup.get(code, [])
            main = next((x for x in rows if x["승인 구분"] == "주"), rows[0] if rows else None)
            batch = r["lot 관리"] == "예"
            uoms = [{"uom": UOM[r["기본 단위"]], "conversion_factor": 1}]
            dens = num(r["밀도(g/mL)"])
            if dens:
                uoms.append({"uom": "Litre", "conversion_factor": dens})
            doc = {
                "item_code": code, "item_name": r["품목명"], "item_group": r["분류"],
                "stock_uom": UOM[r["기본 단위"]], "is_stock_item": 1, "include_item_in_manufacturing": 1,
                "has_batch_no": 1 if batch else 0, "has_expiry_date": 1 if batch else 0,
                "shelf_life_in_days": int(num(r["유효기간(일)"], 0)), "lead_time_days": int(num(r["구매 리드타임(일)"], 0)),
                "valuation_rate": num(main["단가"]) if main else 0, "standard_rate": 0,
                "custom_production_alias": r["생산 약칭"], "custom_sub_category": r["세부 분류"],
                "custom_storage_condition": r["보관 조건"], "custom_safety_stock_months": num(r["안전재고(개월)"]),
                "custom_hazardous": 1 if r["위험물"] == "예" else 0, "custom_density": dens,
                "custom_qc_warehouse": wh(r["입고 창고"]), "custom_pass_warehouse": wh(r["합격 창고"]),
                "quality_inspection_template": tmpl[r["분류"]],
                "uoms": uoms,
                "supplier_items": [{"supplier": x["BP 코드"], "supplier_part_no": x["공급사 품명"]} for x in rows],
                "item_defaults": [{"company": COMPANY, "default_warehouse": wh(r["입고 창고"]),
                                   "default_supplier": main["BP 코드"] if main else None}],
                "description": "; ".join(f"{x['BP 코드']}({x['승인 구분']}) {x['공급사 품명']} {x['단가']}{x['단가 단위']}" for x in rows),
            }
            if self.ensure("Item", code, doc):
                self.log(f"  + {code} {r['품목명']}")
        appr = {}
        for a in self.m["customer_approval"]:
            appr.setdefault(a["SKU"], []).append(a)
        for r in self.m["item_fg"]:
            code = r["SKU"]
            doc = {
                "item_code": code, "item_name": r["제품명"], "item_group": r["제품군"], "stock_uom": "병",
                "is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 0,
                "has_batch_no": 1, "has_expiry_date": 1, "shelf_life_in_days": int(num(r["유효기간(일)"], 0)),
                "standard_rate": num(r["병당 단가(원)"]), "valuation_rate": round(num(r["병당 단가(원)"]) * 0.35),
                "custom_storage_condition": r["보관 조건"], "custom_solid_pct": num(r["고형분(%)"]),
                "custom_annual_plan_bottles": int(num(r["연 판매 계획(병, 평균)"], 0)),
                "quality_inspection_template": "OQC-완제품",
                "customer_items": [{"customer_name": a["고객 코드"], "ref_code": a["고객 품번"]} for a in appr.get(code, [])],
                "item_defaults": [{"company": COMPANY, "default_warehouse": wh("WH-70")}],
                "description": f"{r['제품명']} ({r['제품군']}, 1갤런 병)",
            }
            if self.ensure("Item", code, doc):
                self.log(f"  + {code} {r['제품명']}")

    # ---------------- 설비·공정 ----------------
    def workstations(self):
        types = sorted({r["종류"] for r in self.m["workstation"]} | {"칭량"})
        for t in types:
            self.ensure("Workstation Type", t, {"workstation_type": t})
        for r in self.m["workstation"]:
            self.ensure("Workstation", r["설비 코드"], {
                "workstation_name": r["설비 코드"], "workstation_type": r["종류"],
                # 동시에 걸 수 있는 작업 수 (작업 기록 기준: 충전 3, 여과 FL-1·2는 2, 탱크 1)
                "production_capacity": {"FI": 3, "FL": 2}.get(r["설비 코드"][:2], 1),
                "custom_capacity": num(r["용량(L) 또는 처리량"]), "custom_pm_cycle_days": int(num(r["정비 주기(일)"], 0)),
                "description": r["비고"]})
        self.ensure("Workstation", "칭량실", {"workstation_name": "칭량실", "workstation_type": "칭량",
                                           "production_capacity": 6, "description": "원재료 칭량"})
        for r in self.m["operation"]:
            if r["공정"] == "출하검사":
                continue
            self.ensure("Operation", r["공정"], {"name": r["공정"], "description": f"{r['공정']} ({r['설비']})"})

    def op_type(self, op):
        return {"칭량": "칭량", "배합": "배합 탱크", "숙성": "배합 탱크", "여과": "여과 라인", "충전·포장": "충전 라인(자동)"}[op]

    def boms(self):
        by = {}
        for r in self.m["bom"]:
            by.setdefault(r["SKU"], []).append(r)
        ops = [r for r in self.m["operation"] if r["공정"] != "출하검사"]
        for sku, rows in by.items():
            bom_name = f"BOM-{sku}-001"
            if self.erp.exists("BOM", bom_name):
                continue
            bottles = next((num(r["1,000 L당 투입량"]) for r in rows if r["원재료"] in ("PK-B01", "PK-B02")), 264)
            self.erp.insert({
                "doctype": "BOM", "name": bom_name, "item": sku, "company": COMPANY, "quantity": bottles,
                "is_active": 1, "is_default": 1, "with_operations": 1, "rm_cost_as_per": "Valuation Rate",
                "transfer_material_against": "Work Order",
                "items": [{"item_code": r["원재료"], "qty": num(r["1,000 L당 투입량"]), "uom": UOM[r["단위"]],
                           "stock_uom": UOM[r["단위"]], "conversion_factor": 1} for r in rows],
                "operations": [{"operation": o["공정"], "workstation_type": self.op_type(o["공정"]),
                                "time_in_mins": num(o["표준 시간(시간, 1,000 L 기준)"]) * 60} for o in ops],
                "docstatus": 1,
            })
            self.log(f"  + {bom_name} (1,000 L = {int(bottles)}병)")

    def approvals(self):
        have = {(d["customer"], d["item"]) for d in self.erp.get_list("NR Customer Approval", fields=["customer", "item"])}
        for a in self.m["customer_approval"]:
            if (a["고객 코드"], a["SKU"]) in have:
                continue
            self.erp.insert({"doctype": "NR Customer Approval", "customer": a["고객 코드"], "item": a["SKU"],
                             "customer_item_code": a["고객 품번"], "approval_date": a["승인일"],
                             "approved_materials": a["승인된 원재료@공급사"]})

    def manufacturing_settings(self):
        self.erp.set_single("Manufacturing Settings", {
            "backflush_raw_materials_based_on": "Material Transferred for Manufacture",
            "overproduction_percentage_for_work_order": 10,
            "transfer_extra_materials_percentage": 100,
            "job_card_excess_transfer": 1,
            "disable_capacity_planning": 1,
            "allow_overtime": 1,
            "allow_production_on_holidays": 1,
            "validate_components_quantities_per_bom": 0,
            "make_serial_no_batch_from_work_order": 0,
            "default_wip_warehouse": WIP,
            "default_fg_warehouse": wh("WH-60"),
        })
