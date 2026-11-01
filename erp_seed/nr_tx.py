"""3단계: 기초재고(2026-01-01) + 2026년 거래를 날짜 순서대로 넣는다.

원칙
- 문서번호는 원본 그대로 (PO-26-0001, GR-26-0001, QI-26-0001, WO-26-0001, SO-26-0001, DN-26-0001 ...).
- 재고 이동 순서는 stock_move.csv(lot 이동 이력)의 순서를 그대로 따른다.
- ERP 도입일은 2026-01-01. 2025년에 시작돼 2026년으로 넘어온 문서는 '이관 문서'로 처리한다.
  * 2025년 발주·구매요청·수주: 원래 날짜로 만든다(회계연도 2025 사용).
  * 2025년에 생산까지 끝난 작업지시(WO-25-0067): 완제품 lot만 기초재고로 이관하고 작업지시는 만들지 않는다.
  * 2025년에 원재료를 투입하고 2026년에 완료된 작업지시: 투입된 원재료를 재공 창고(WH-WIP) 기초재고로 이관한다.
- 이미 들어간 문서는 건너뛴다. 중간에 멈추면 다시 실행하면 이어서 진행한다.
"""
import csv
import datetime as dt
import json
import os
from collections import OrderedDict, defaultdict

from erp_client import ERPError
from nr_master import UOM, WIP, wh
from nr_setup import ABBR, COMPANY

CUTOVER = "2026-01-01"
EPS = 1e-6


def read(d, sub, name):
    with open(os.path.join(d, sub, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def f(x, default=0.0):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return default


def r3(x):
    return round(x + 0.0, 3)


def wh_of(code):
    """stock_move의 장소 코드 → ERPNext 창고."""
    if code.startswith("WH-"):
        return wh(code)
    if code.startswith(("MX-", "FI-")):
        return WIP
    return None  # 공급사(BP-), 고객(CU-)


class Loader:
    def __init__(self, erp, data_dir, user, log=print):
        self.erp, self.d, self.user, self.log = erp, data_dir, user, log
        self.m = {k: read(data_dir, "master", k + ".csv") for k in ["item_raw", "item_fg", "item_supplier"]}
        self.e = {k: read(data_dir, "erp", k + ".csv") for k in [
            "stock_opening_2026", "sales_forecast", "sales_order", "delivery_note", "material_request",
            "purchase_order", "purchase_receipt", "quality_inspection", "quality_inspection_reading",
            "production_plan", "work_order", "job_card", "stock_entry_manufacture", "stock_move",
            "downtime", "non_conformance", "stock_reconciliation"]}
        self.raw = {r["품목코드"]: r for r in self.m["item_raw"]}
        self.fg = {r["SKU"]: r for r in self.m["item_fg"]}
        self.batch_items = {c for c, r in self.raw.items() if r["lot 관리"] == "예"} | set(self.fg)
        self.stock_uom = {c: UOM[r["기본 단위"]] for c, r in self.raw.items()} | {c: "병" for c in self.fg}
        self.price = {}
        for r in self.m["item_supplier"]:
            if r["승인 구분"] == "주" or r["품목코드"] not in self.price:
                self.price[r["품목코드"]] = f(r["단가"])
        for c, r in self.fg.items():
            self.price[c] = round(f(r["병당 단가(원)"]) * 0.35)
        self.cache = {}

    # =====================================================================
    # 계획 만들기 (CSV → 순서가 정해진 작업 목록)
    # =====================================================================
    def build(self, verbose=False, until=None):
        """until: 이 날짜까지의 거래만 넣는다. 기본값은 오늘 —
        ERPNext는 미래 날짜 입고를 막기 때문에, 오늘 이후 거래는 그날이 오면 이어서 넣는다."""
        self.until = until or dt.date.today().isoformat()
        E = self.e
        self.ops = []          # (정렬키, 종류, 데이터)
        self.batches = {}      # lot → Batch 문서
        self.warn = []

        po = {r["발주번호"]: r for r in E["purchase_order"]}
        mr = {r["구매요청번호"]: r for r in E["material_request"]}
        gr = {r["입고번호"]: r for r in E["purchase_receipt"]}
        qi = {r["검사번호"]: r for r in E["quality_inspection"]}
        wo = {r["작업지시번호"]: r for r in E["work_order"]}
        readings = defaultdict(list)
        for r in E["quality_inspection_reading"]:
            readings[r["검사번호"]].append(r)
        self.readings = readings
        so = OrderedDict()
        for r in E["sales_order"]:
            so.setdefault(r["수주번호"], []).append(r)
        dn = OrderedDict()
        for r in E["delivery_note"]:
            dn.setdefault(r["출하번호"], []).append(r)
        se_rows = defaultdict(list)
        fin = {}
        for r in E["stock_entry_manufacture"]:
            if r["구분"] == "제조 완료":
                fin[r["작업지시번호"]] = r
            else:
                se_rows[r["작업지시번호"]].append(r)
        self.se_rows, self.fin = se_rows, fin
        jc = defaultdict(list)
        for r in E["job_card"]:
            jc[r["작업지시번호"]].append(r)
        self.jc = jc

        # ---- 이관 구분 ----
        done_before = {w for w, r in fin.items() if r["일자"] < CUTOVER}            # WO-25-0067
        carry = {w for w, rows in se_rows.items()
                 if w not in done_before and any(x["일자"] < CUTOVER for x in rows)}  # WO-25-0073, 0075
        self.done_before, self.carry = done_before, carry

        # ---- lot 정보(Batch) ----
        fg_exp = {}
        for r in E["delivery_note"]:
            d = dt.date.fromisoformat(r["실제출하일"]) + dt.timedelta(days=int(f(r["출하시잔여유효기간_일"])))
            fg_exp.setdefault(r["완제품lot"], d.isoformat())
        for r in E["stock_opening_2026"]:
            if r["품목"] in self.batch_items and r["lot"] not in self.batches:
                self.batches[r["lot"]] = {"item": r["품목"], "expiry_date": r["유효기간"],
                                          "custom_supplier_lot": r["공급사lot"]}
        for r in E["purchase_receipt"]:
            if r["품목"] in self.batch_items and r["사내lot"] not in self.batches:
                self.batches[r["사내lot"]] = {"item": r["품목"], "manufacturing_date": r["제조일"],
                                             "expiry_date": r["유효기간"], "custom_supplier_lot": r["공급사lot"],
                                             "supplier": r["공급사"],
                                             "description": f"입고 {r['입고번호']} / 발주 {r['발주번호']}"}
        for w, r in fin.items():
            lot = r["원재료lot"]
            mfg = r["일자"]
            sku = r["품목"]
            exp = fg_exp.get(lot) or (dt.date.fromisoformat(mfg) + dt.timedelta(days=int(f(self.fg[sku]["유효기간(일)"])))).isoformat()
            b = {"item": sku, "manufacturing_date": mfg, "expiry_date": exp}
            if w not in done_before:
                b.update({"reference_doctype": "Work Order", "reference_name": w})
            self.batches.setdefault(lot, b)

        # 기록이 없는 lot(2025년 입고 후 2025년에 다 쓴 lot 등): lot 번호의 입고일 + 품목 유효기간으로 만든다
        refs = [(x["품목"], x["원재료lot"]) for rows in se_rows.values() for x in rows]
        refs += [(r["품목"], r["lot"]) for r in E["stock_move"]]
        for item, lot in refs:
            if item in self.batch_items and lot and lot not in self.batches:
                m_ = lot.split("-")[1]
                rec = dt.date(2000 + int(m_[:2]), int(m_[2:4]), int(m_[4:6]))
                life = int(f((self.raw.get(item) or self.fg.get(item))["유효기간(일)"]))
                self.batches[lot] = {"item": item, "expiry_date": (rec + dt.timedelta(days=life)).isoformat(),
                                     "description": "ERP 도입 전 입고 lot (입고일 기준 유효기간 추정)"}

        # ---- 장부(재고 시뮬레이션): 넘치는 출고가 없는지 확인 ----
        self.led = defaultdict(float)

        # ---- 기초재고 ----
        open_rows = []
        for r in E["stock_opening_2026"]:
            open_rows.append((r["품목"], wh(r["창고"]), r["lot"], f(r["수량"])))
        for w in sorted(carry):
            for x in se_rows[w]:
                if x["일자"] < CUTOVER:
                    open_rows.append((x["품목"], WIP, x["원재료lot"], f(x["수량"])))
        agg = OrderedDict()
        for item, w_, lot, q in open_rows:
            key = (item, w_, lot if item in self.batch_items else None)
            agg[key] = agg.get(key, 0) + q
        import math
        whole = {c for c, u in self.stock_uom.items() if u in ("EA", "병")}
        # 낱개 단위(EA·병) 기초재고에 소수점이 있으면 올림 (원본 데이터의 반올림 흔적)
        self.opening = [(k[0], k[1], k[2], math.ceil(v - 1e-9) if k[0] in whole else r3(v))
                        for k, v in agg.items() if v > EPS]
        for item, w_, lot, q in self.opening:
            self.led[(item, w_, lot)] += q

        # ---- 하루 단위 정렬키 ----
        seq = [0]

        def key(date, pri):
            seq[0] += 1
            return (date, pri, seq[0])

        # 문서(재고 무관): 0 구구매요청 1 발주 2 수주 3 작업지시
        for r in E["material_request"]:
            self.ops.append((key(r["요청일"], 0), "MR", r))
        for r in E["purchase_order"]:
            self.ops.append((key(r["발주일"], 1), "PO", r))
        for s, rows in so.items():
            self.ops.append((key(rows[0]["수주일"], 2), "SO", rows))
        for w, r in wo.items():
            if w in done_before:
                continue
            first = min([r["계획시작일"], r["실제시작일"]] + [x["일자"] for x in se_rows[w]])
            self.ops.append((key(first, 3), "WO", r))

        # 재고 이동: stock_move 순서대로 묶기
        groups = OrderedDict()
        for i, r in enumerate(E["stock_move"]):
            reason = r["사유"]
            kind, ref = reason.rsplit(" ", 1)
            gk = (r["일자"], kind, ref)
            if gk not in groups:
                groups[gk] = {"date": r["일자"], "kind": kind, "ref": ref, "rows": [], "i": i}
            groups[gk]["rows"].append(r)
        for g in groups.values():
            self.ops.append((key(g["date"], 10), "MOVE", g))

        # 입고(GR)는 stock_move에 '입고'로 있다. 취소된 중복 입고(-D)는 따로
        for r in E["purchase_receipt"]:
            if r["상태"] == "취소":
                self.ops.append((key(r["실제입고일"], 11), "GR_DUP", r))

        # 포장재 IQC (창고 이동 없음 → 검사 기록만)
        moved_qi = {g["ref"] for g in groups.values() if g["kind"].startswith(("IQC", "출하검사"))}
        for q, r in qi.items():
            if q not in moved_qi:
                self.ops.append((key(r["판정일시"][:10], 12), "QI_ONLY", r))

        for r in E["non_conformance"]:
            self.ops.append((key(r["발생일"], 20), "NCR", r))
        for i, r in enumerate(E["downtime"]):
            self.ops.append((key(r["시작일"], 21), "DT", dict(r, _i=i + 1)))
        recon = E["stock_reconciliation"]
        if recon:
            self.ops.append((key(recon[0]["실사일"], 30), "RECON", recon))

        self.ops.sort(key=lambda x: x[0])
        self.later = [op for op in self.ops if op[0][0] > self.until]
        self.ops = [op for op in self.ops if op[0][0] <= self.until]

        # 장부로 출고량 점검(넘치면 깎는다)
        self.groups = groups
        self.qi, self.po, self.mr, self.gr, self.wo, self.so, self.dn = qi, po, mr, gr, wo, so, dn
        self._dry_ledger()
        if verbose:
            from collections import Counter
            c = Counter(k for _, k, _ in self.ops)
            print(f"기준일 {self.until} (이후 거래 {len(self.later)}건은 나중에)")
            print("작업 목록:", dict(c), "기초재고 행:", len(self.opening), "lot:", len(self.batches))
            print("이관: 2025 완료 WO", sorted(self.done_before), "/ 재공 이관 WO", sorted(self.carry))
            for w_ in self.warn[:30]:
                print("  주의:", w_)
            print("주의 건수:", len(self.warn))
        return self.ops

    def _move_lines(self, g):
        """stock_move 묶음 → [품목, 출발창고, 도착창고, lot, 수량] 목록.
        lot 관리를 안 하는 품목(포장재)은 같은 품목끼리 합치고, 낱개 단위는 정수로 맞춘다."""
        if "_lines" in g:
            return g["_lines"]
        out, idx = [], {}
        for r in g["rows"]:
            item = r["품목"]
            lot = r["lot"] if item in self.batch_items else None
            src = None if g["kind"] == "생산 완료" else wh_of(r["출발창고"])  # 완제품은 제조로 새로 생김
            k = (item, src, wh_of(r["도착창고"]), lot)
            if k in idx:
                out[idx[k]][4] += f(r["수량"])
            else:
                idx[k] = len(out)
                out.append([item, src, k[2], lot, f(r["수량"])])
        for line in out:
            if self.stock_uom[line[0]] in ("EA", "병"):
                line[4] = float(round(line[4]))
        g["_lines"] = out
        return out

    def _dry_ledger(self):
        """장부를 미리 돌려서 (1) 넘치는 출고는 가용량으로 깎고 (2) 작업지시별 재공(투입량)을 계산한다."""
        led = self.led
        self.clamped = {}
        self.wip = defaultdict(lambda: defaultdict(float))   # WO → (품목, lot) → 투입량
        for w in self.carry:
            for x in self.se_rows[w]:
                if x["일자"] < CUTOVER:
                    lot = x["원재료lot"] if x["품목"] in self.batch_items else None
                    self.wip[w][(x["품목"], lot)] += f(x["수량"])
        for k, kind, g in self.ops:
            if kind != "MOVE":
                continue
            if g["kind"] == "생산 완료":
                for (item, lot), q in self.wip[g["ref"]].items():
                    have = led[(item, WIP, lot)]
                    if q > have + 1e-3:
                        self.warn.append(f"{g['ref']} 소비 {item} {lot} {q} > 재공 {have:.3f}")
                    led[(item, WIP, lot)] -= min(q, have)
            for i, (item, s, t, lot, q) in enumerate(self._move_lines(g)):
                if s:
                    have = led[(item, s, lot)]
                    if q > have + 1e-6:
                        if q - have > 0.05:
                            self.warn.append(f"{g['date']} {g['kind']} {g['ref']} {item} {lot} {q} > {have:.3f} @{s}")
                        q = max(have, 0)
                        if self.stock_uom[item] in ("EA", "병"):
                            q = float(int(q + 1e-9))
                        self.clamped[(id(g), i)] = r3(q)
                    led[(item, s, lot)] -= q
                if t:
                    led[(item, t, lot)] += q
                if g["kind"] in ("생산 투입", "충전"):
                    self.wip[g["ref"]][(item, lot)] += q

    # =====================================================================
    # 실행
    # =====================================================================
    def run(self, until=None):
        self.build(until=until)
        erp = self.erp
        self.log(f"[거래] 작업 {len(self.ops)}건, lot {len(self.batches)}개")
        self.have = {dt_: erp.names(dt_) for dt_ in [
            "Material Request", "Purchase Order", "Purchase Receipt", "Quality Inspection", "Work Order",
            "Stock Entry", "Sales Order", "Delivery Note", "Stock Reconciliation", "Non Conformance",
            "Downtime Entry", "Batch"]}
        import nr_setup
        nr_setup.set_prompt_naming(erp, True, log=lambda *a: None)
        self.opening_stock()
        self.forecast_and_plan()
        n = len(self.ops)
        last_month = None
        for i, (k, kind, data) in enumerate(self.ops):
            date = k[0]
            if date[:7] != last_month:
                last_month = date[:7]
                self.log(f"[거래] {last_month} … ({i}/{n})")
            self.t = self.ptime(k)
            getattr(self, "op_" + kind)(data, date)
        self.log(f"[거래] 완료 — {self.until}까지 반영" + (f" (이후 {len(self.later)}건은 그날이 지나면 다시 실행)" if self.later else ""))

    def ptime(self, k):
        """하루 안에서 순서대로 시각을 배정 (07:00부터 15초 간격)."""
        date, pri, s = k
        day = self.cache.setdefault("_day", {})
        n = day.get(date, 0)
        day[date] = n + 1
        sec = 7 * 3600 + n * 15
        return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

    def done(self, doctype, name):
        return name in self.have.get(doctype, set())

    def mark(self, doctype, name):
        self.have.setdefault(doctype, set()).add(name)

    def insert(self, doc, submit=True):
        if submit:
            doc["docstatus"] = 1
        doc.setdefault("company", COMPANY) if doc["doctype"] not in ("Batch", "Downtime Entry", "Non Conformance") else None
        try:
            if submit and doc["doctype"] in ("Purchase Order", "Sales Order"):
                # 제출 상태로 바로 넣으면 상태값이 'Draft'로 남는 문제가 있어 저장 → 제출 두 단계로
                doc["docstatus"] = 0
                res = self.erp.insert(doc)
                self.erp.submit(self.erp.get(doc["doctype"], res["name"]))
            else:
                res = self.erp.insert(doc)
        except ERPError:
            self.log("  실패한 문서: " + json.dumps(doc, ensure_ascii=False, default=str)[:1200])
            raise
        self.mark(doc["doctype"], doc.get("name") or res.get("name"))
        return res

    # ---------------- lot ----------------
    def ensure_batch(self, lot):
        if not lot or self.done("Batch", lot):
            return
        b = self.batches.get(lot)
        if not b:
            raise ERPError(f"lot 정보 없음: {lot}")
        doc = {"doctype": "Batch", "batch_id": lot}
        doc.update({k: v for k, v in b.items() if v})
        if not doc.get("manufacturing_date"):
            # 비워 두면 ERPNext가 오늘 날짜를 넣는다 → lot 번호의 날짜(완제품=생산일, 원재료=입고일)로 채운다
            m_ = lot.split("-")[1]
            doc["manufacturing_date"] = f"20{m_[:2]}-{m_[2:4]}-{m_[4:6]}"
            if lot.startswith("RL-"):
                doc["description"] = (doc.get("description", "") + " 제조일 미상(이관 lot) — 입고일로 기록").strip()
        try:
            self.erp.insert(doc)
        except ERPError as e:
            if "Duplicate" not in str(e) and "already exists" not in str(e):
                raise
        self.mark("Batch", lot)

    # ---------------- 기초재고 ----------------
    def opening_stock(self):
        name = "SR-OPEN-2026"
        if self.done("Stock Reconciliation", name):
            return
        self.log(f"[기초재고] {len(self.opening)}행 (2026-01-01 00:00 기준)")
        items = []
        for item, w_, lot, q in self.opening:
            self.ensure_batch(lot)
            row = {"item_code": item, "warehouse": w_, "qty": q, "valuation_rate": self.price.get(item, 1) or 1}
            if lot:
                row.update({"batch_no": lot, "use_serial_batch_fields": 1})
            items.append(row)
        self.insert({"doctype": "Stock Reconciliation", "name": name, "purpose": "Opening Stock",
                     "posting_date": CUTOVER, "posting_time": "00:00:01", "set_posting_time": 1,
                     "expense_account": f"Temporary Opening - {ABBR}",
                     "items": items})

    # ---------------- 판매 예측·월 생산계획(추가 화면) ----------------
    def forecast_and_plan(self):
        erp = self.erp
        have = {(d["version"], d["customer"], d["item"], d["target_month"]) for d in erp.get_list(
            "NR Sales Forecast", fields=["version", "customer", "item", "target_month"])}
        docs = [{"doctype": "NR Sales Forecast", "version": r["버전"], "created_on": r["작성일"],
                 "customer": r["고객"], "item": r["SKU"], "target_month": r["대상월"],
                 "qty_bottles": int(f(r["예측수량_병"]))} for r in self.e["sales_forecast"]
                if r["작성일"] <= self.until and (r["버전"], r["고객"], r["SKU"], r["대상월"]) not in have]
        for i in range(0, len(docs), 200):
            erp.call_post("frappe.client.insert_many", docs=docs[i:i + 200])
        if docs:
            self.log(f"[판매 예측] {len(docs)}행")
        have = {(d["plan_month"], d["item"]) for d in erp.get_list("NR Production Plan", fields=["plan_month", "item"])}
        docs = [{"doctype": "NR Production Plan", "plan_month": r["계획월"], "sop_version": r["생판회의버전"],
                 "item": r["SKU"], "qty_bottles": int(f(r["계획수량_병"])), "plan_status": r["구분"]}
                for r in self.e["production_plan"]
                if r["계획월"] <= self.until[:7] and (r["계획월"], r["SKU"]) not in have]
        for i in range(0, len(docs), 200):
            erp.call_post("frappe.client.insert_many", docs=docs[i:i + 200])
        if docs:
            self.log(f"[월 생산계획] {len(docs)}행")

    # ---------------- 구매 ----------------
    def op_MR(self, r, date):
        name = r["구매요청번호"]
        if self.done("Material Request", name):
            return
        item = r["품목"]
        self.insert({"doctype": "Material Request", "name": name, "material_request_type": "Purchase",
                     "transaction_date": r["요청일"], "schedule_date": r["필요일"],
                     "custom_request_dept": r["요청부서"], "custom_request_reason": r["요청사유"],
                     "items": [{"item_code": item, "qty": f(r["수량"]), "uom": UOM[r["단위"]],
                                "schedule_date": r["필요일"], "warehouse": wh(self.raw[item]["입고 창고"])}]})

    def child(self, doctype, name, item=None):
        key = (doctype, name)
        if key not in self.cache:
            self.cache[key] = self.erp.get(doctype, name)
        d = self.cache[key]
        for row in d["items"]:
            if item is None or row["item_code"] == item:
                return row["name"]
        raise ERPError(f"{doctype} {name}에 {item} 행이 없음")

    def op_PO(self, r, date):
        name = r["발주번호"]
        if self.done("Purchase Order", name):
            return
        item = r["품목"]
        row = {"item_code": item, "qty": f(r["수량"]), "uom": UOM[r["단위"]], "rate": f(r["단가_원"]),
               "schedule_date": r["납기요청일"], "warehouse": wh(self.raw[item]["입고 창고"]),
               "supplier_part_no": r["공급사품명"]}
        if r["구매요청번호"]:
            row.update({"material_request": r["구매요청번호"],
                        "material_request_item": self.child("Material Request", r["구매요청번호"])})
        self.insert({"doctype": "Purchase Order", "name": name, "supplier": r["공급사"],
                     "transaction_date": r["발주일"], "schedule_date": r["납기요청일"], "currency": "KRW",
                     "custom_approval_no": r["품의번호"], "custom_approval_submitted": r["품의상신일"] or None,
                     "custom_approval_date": r["품의승인일"] or None, "custom_approver": r["승인자"],
                     "custom_agency": r["경유에이전시"] or None,
                     "custom_supplier_confirmed_date": r["공급사회신납기"] or None,
                     "custom_transport": r["운송"], "custom_note": r["비고"],
                     "items": [row]})

    def pr_doc(self, r, name):
        item = r["품목"]
        p = self.po[r["발주번호"]]
        unit = r["단위"]
        q = f(r["수량"])
        row = {"item_code": item, "qty": q, "received_qty": q, "uom": UOM[unit],
               "warehouse": wh(r["입고창고"]), "purchase_order": r["발주번호"],
               "purchase_order_item": self.child("Purchase Order", r["발주번호"]),
               "supplier_part_no": r["공급사품명"]}
        rate = f(p["단가_원"])
        extra = {}
        if unit == "L":
            # 솔벤트를 L로 입고한 경우: 밀도로 kg 환산 (lot 이력 수량과 맞추기 위해 실제 비율 사용).
            # ERPNext는 발주(kg)와 단위가 다르면 발주 연결을 막는다 → 현장에서처럼 발주 연결 없이 입고하고
            # 발주번호는 수기 필드에만 남긴다(이것도 실제로 생기는 데이터 결함).
            kg = self.gr_kg.get(name) if hasattr(self, "gr_kg") else None
            cf = round((kg / q) if kg else f(self.raw[item]["밀도(g/mL)"]), 9)
            row.update({"conversion_factor": cf, "rate": round(rate * cf, 2)})
            row.pop("purchase_order")
            row.pop("purchase_order_item")
            extra = {"remarks": f"L 단위로 입고(발주는 kg). 발주 연결 못 함 — 발주번호 {r['발주번호']}"}
        else:
            row.update({"conversion_factor": 1, "rate": rate})
        lot = r["사내lot"] if item in self.batch_items else None
        if lot:
            row.update({"batch_no": lot, "use_serial_batch_fields": 1})
        return {"doctype": "Purchase Receipt", "name": name, "supplier": r["공급사"],
                "posting_date": r["실제입고일"], "posting_time": self.t, "set_posting_time": 1,
                "currency": "KRW", "custom_erp_entry_date": r["ERP입력일"],
                "custom_coa_attached": 1 if r["COA첨부"] == "예" else 0,
                "custom_supplier_lot": r["공급사lot"], "supplier_delivery_note": r["공급사lot"],
                "custom_po_ref": r["발주번호"], "items": [row], **extra}, lot

    def op_GR_DUP(self, r, date):
        name = r["입고번호"]
        if self.done("Purchase Receipt", name):
            return
        doc, lot = self.pr_doc(r, name)
        # 같은 발주에 두 번 입고하면 ERPNext가 초과 입고로 막는다 → 중복분은 발주 연결 없이 들어갔다가 취소된 것으로 기록
        doc["items"][0].pop("purchase_order", None)
        doc["items"][0].pop("purchase_order_item", None)
        doc["remarks"] = f"중복 입력(발주 {r['발주번호']}) — 같은 날 취소"
        self.ensure_batch(lot)
        self.insert(doc)
        self.erp.cancel("Purchase Receipt", name)

    # ---------------- 재고 이동 ----------------
    def op_MOVE(self, g, date):
        kind = g["kind"]
        if kind == "입고":
            return self.mv_receipt(g, date)
        if kind in ("IQC 합격", "IQC 불합격", "출하검사"):
            return self.mv_inspection(g, date)
        if kind in ("생산 투입", "충전"):
            return self.mv_issue(g, date)
        if kind == "생산 완료":
            return self.mv_finish(g, date)
        if kind == "출하":
            return self.mv_delivery(g, date)
        raise ERPError(f"모르는 이동 종류: {kind}")

    def mv_receipt(self, g, date):
        name = g["ref"]
        if self.done("Purchase Receipt", name):
            return
        r = self.gr[name]
        if r["단위"] == "L":
            self.gr_kg = getattr(self, "gr_kg", {})
            self.gr_kg[name] = sum(f(x["수량"]) for x in g["rows"])
        doc, lot = self.pr_doc(r, name)
        self.ensure_batch(lot)
        self.insert(doc)

    def qty(self, g, i, q):
        return self.clamped.get((id(g), i), q)

    def se_items(self, g):
        items = []
        for i, (item, s, t, lot, q) in enumerate(self._move_lines(g)):
            q = self.qty(g, i, q)
            if q <= EPS:
                continue
            row = {"item_code": item, "qty": r3(q), "uom": self.stock_uom[item], "conversion_factor": 1}
            if s:
                row["s_warehouse"] = s
            if t:
                row["t_warehouse"] = t
            if lot:
                row.update({"batch_no": lot, "use_serial_batch_fields": 1})
            items.append(row)
        return items

    def mv_inspection(self, g, date):
        q = self.qi[g["ref"]]
        tag = "IQC" if g["kind"].startswith("IQC") else "OQC"
        se_name = f"SE-{tag}-{g['ref'][3:]}"
        if not self.done("Stock Entry", se_name):
            self.insert({"doctype": "Stock Entry", "name": se_name, "stock_entry_type": "Material Transfer",
                         "purpose": "Material Transfer", "posting_date": date, "posting_time": self.t,
                         "set_posting_time": 1, "remarks": f"{g['kind']} {g['ref']}", "items": self.se_items(g)})
        self.make_qi(q, se_name)

    def make_qi(self, q, se_name=None):
        name = q["검사번호"]
        if self.done("Quality Inspection", name):
            return
        lot = q["lot"]
        item = q["품목"]
        incoming = q["구분"] == "입고"
        ref_type, ref_name = "Stock Entry", se_name
        gr_of_lot = self.cache.setdefault("_gr_by_lot", {r["사내lot"]: r["입고번호"] for r in self.e["purchase_receipt"]
                                                          if r["상태"] != "취소"})
        if incoming and lot in gr_of_lot and self.done("Purchase Receipt", gr_of_lot[lot]):
            ref_type, ref_name = "Purchase Receipt", gr_of_lot[lot]
        if not ref_name:
            raise ERPError(f"{name}: 연결할 문서 없음")
        readings = []
        for x in self.readings.get(name, []):
            lo, hi, v = x["하한"], x["상한"], x["측정값"]
            try:
                fv = float(v)
                numeric = 1
            except ValueError:
                numeric = 0
            rd = {"specification": x["항목"], "manual_inspection": 1}
            if numeric and (lo or hi):
                ok = (not lo or fv >= f(lo) - EPS) and (not hi or fv <= f(hi) + EPS)
                rd.update({"numeric": 1, "reading_1": v, "min_value": f(lo) if lo else -1e9,
                           "max_value": f(hi) if hi else 1e9, "status": "Accepted" if ok else "Rejected"})
            else:
                rd.update({"numeric": 0, "reading_value": v, "value": "적합",
                           "status": "Accepted" if v in ("확인", "적합", "이상 없음") or numeric else "Rejected"})
            readings.append(rd)
        tmpl = self.cache.setdefault("_tmpl", {})
        if item not in tmpl:
            tmpl[item] = (self.erp.call("frappe.client.get_value", doctype="Item", filters=item,
                                        fieldname="quality_inspection_template") or {}).get("quality_inspection_template")
        doc = {"doctype": "Quality Inspection", "name": name,
               "inspection_type": "Incoming" if incoming else "Outgoing", "custom_category": q["구분"],
               "reference_type": ref_type, "reference_name": ref_name, "item_code": item,
               "batch_no": lot if item in self.batch_items else None, "sample_size": 1,
               "report_date": q["판정일시"][:10], "inspected_by": self.user, "custom_inspector": q["검사자"],
               "custom_requested_at": q["의뢰일시"] or None, "custom_started_at": q["시작일시"] or None,
               "custom_decided_at": q["판정일시"] or None, "custom_erp_entry_at": q["ERP입력일시"] or None,
               "custom_supplier": q["공급사"] or None, "quality_inspection_template": tmpl[item],
               "manual_inspection": 1, "status": "Accepted" if q["판정"] == "합격" else "Rejected",
               "remarks": q["불합격사유"] or None, "readings": readings}
        self.insert(doc)

    def op_QI_ONLY(self, q, date):
        self.make_qi(q)

    # ---------------- 생산 ----------------
    def op_WO(self, r, date):
        """작업지시 생성. 생성 시점에 아는 것(계획)만 넣는다.
        실제 시작·종료일, 수율, 완제품 lot은 생산 완료 때 채운다(미래 정보가 미리 들어가지 않게)."""
        name = r["작업지시번호"]
        if self.done("Work Order", name):
            return
        sku = r["SKU"]
        carry = name in self.carry
        fin_date = self.fin[name]["일자"] if name in self.fin else "9999"
        nominal = int(-(-f(r["배치량_L"]) * 264 // 1000))  # 1,000 L = 264병 기준 계획 수량
        qty = int(f(r["생산병수"])) if fin_date <= self.until else max(nominal, int(f(r["생산병수"])))
        doc = {"doctype": "Work Order", "name": name, "production_item": sku, "bom_no": f"BOM-{sku}-001",
               "qty": qty, "wip_warehouse": WIP, "fg_warehouse": wh("WH-60"),
               "planned_start_date": f"{r['계획시작일']} 08:00:00", "expected_delivery_date": r["계획종료일"],
               "custom_planned_end": r["계획종료일"], "custom_batch_size_l": f(r["배치량_L"]),
               "custom_mix_tank": r["배합탱크"], "custom_wo_type": r["구분"],
               "custom_linked_so": r["연결수주"] or None,
               "use_multi_level_bom": 0, "operations": self.wo_operations(name, r)}
        if carry:
            doc.update({"skip_transfer": 1, "from_wip_warehouse": 1,
                        "custom_migration_note": "ERP 도입(2026-01-01) 전 2025년에 원재료 투입. 투입분은 재공 창고 기초재고로 이관."})
        self.insert(doc)

    STD_HOURS = [("칭량", "칭량", 1.0), ("배합", "배합 탱크", 9.0), ("숙성", "배합 탱크", 24.0),
                 ("여과", "여과 라인", 3.0), ("충전·포장", "충전 라인(자동)", 3.0)]

    def wo_operations(self, w, r):
        """레시피 공정 5개 + 실제 쓴 설비(작업카드 기록)."""
        used = {x["공정"]: x["설비"] for x in self.jc.get(w, [])}
        scale = f(r["배치량_L"]) / 1000.0
        ops = []
        for i, (op, wtype, hrs) in enumerate(self.STD_HOURS, 1):
            ws = used.get(op)
            if op == "충전·포장" and ws == "FI-M1":
                wtype = "충전 라인(수동)"
            ops.append({"operation": op, "bom": f"BOM-{r['SKU']}-001", "workstation_type": wtype,
                        "workstation": ws, "time_in_mins": round(hrs * 60 * max(scale, 0.2), 1),
                        "sequence_id": i})
        return ops

    def mv_issue(self, g, date):
        w = g["ref"]
        n = self.cache.setdefault("_issue_n", defaultdict(int))
        n[w] += 1
        se_name = f"SE-ISS-{w[3:]}-{n[w]:02d}"
        if self.done("Stock Entry", se_name):
            return
        carry = w in self.carry
        purpose = "Material Transfer" if carry else "Material Transfer for Manufacture"
        r = self.wo[w]
        doc = {"doctype": "Stock Entry", "name": se_name, "stock_entry_type": purpose, "purpose": purpose,
               "posting_date": date, "posting_time": self.t, "set_posting_time": 1,
               "remarks": f"{g['kind']} {w} ({g['rows'][0]['도착창고']})", "items": self.se_items(g)}
        if not carry:
            # 작업지시의 첫 투입만 '생산 수량'을 잡고, 이후 투입(충전 포장재 등)은 추가 투입(0)으로 기록
            first = n[w] == 1
            doc.update({"work_order": w, "from_bom": 1 if first else 0, "bom_no": f"BOM-{r['SKU']}-001",
                        "fg_completed_qty": int(f(r["생산병수"])) if first else 0})
        self.insert(doc)

    def job_cards(self, w):
        erp = self.erp
        jcs = erp.get_list("Job Card", filters=[["work_order", "=", w]],
                           fields=["name", "operation", "docstatus", "sequence_id"], order_by="sequence_id asc, name asc")
        rows = {x["공정"]: x for x in self.jc.get(w, [])}
        qty = int(f(self.wo[w]["생산병수"]))
        for j in jcs:
            if j["docstatus"] != 0:
                continue
            x = rows.get(j["operation"])
            if not x:
                continue
            t0, t1 = x["시작일시"] + ":00", x["종료일시"] + ":00"
            mins = (dt.datetime.fromisoformat(t1) - dt.datetime.fromisoformat(t0)).total_seconds() / 60
            doc = erp.get("Job Card", j["name"])
            doc.update({"workstation": x["설비"], "custom_filter_lot": x["사용필터lot"] or None,
                        "custom_crew": x["작업자"], "actual_start_date": t0, "actual_end_date": t1,
                        "time_logs": [{"from_time": t0, "to_time": t1, "time_in_mins": mins, "completed_qty": qty}]})
            try:
                erp.update("Job Card", j["name"], doc)
                erp.submit(erp.get("Job Card", j["name"]))
            except ERPError:
                self.log(f"  작업카드 실패: {w} {j['operation']} {j['name']}")
                raise

    def mv_finish(self, g, date):
        w = g["ref"]
        se_name = f"SE-MFG-{w[3:]}"
        if self.done("Stock Entry", se_name):
            return
        r = self.wo[w]
        sku = r["SKU"]
        fin = self.fin[w]
        lot = fin["원재료lot"]
        self.ensure_batch(lot)
        self.job_cards(w)
        items = []
        for (item, lot_), q in self.wip[w].items():
            if q <= EPS:
                continue
            row = {"item_code": item, "qty": r3(q), "s_warehouse": WIP, "uom": self.stock_uom[item],
                   "conversion_factor": 1}
            if lot_:
                row.update({"batch_no": lot_, "use_serial_batch_fields": 1})
            items.append(row)
        qty = int(f(fin["수량"]))
        items.append({"item_code": sku, "qty": qty, "t_warehouse": wh("WH-60"), "uom": "병", "conversion_factor": 1,
                      "is_finished_item": 1, "batch_no": lot, "use_serial_batch_fields": 1})
        self.insert({"doctype": "Stock Entry", "name": se_name, "stock_entry_type": "Manufacture",
                     "purpose": "Manufacture", "work_order": w, "from_bom": 1, "bom_no": f"BOM-{sku}-001",
                     "fg_completed_qty": qty, "use_multi_level_bom": 0, "from_warehouse": WIP,
                     "to_warehouse": wh("WH-60"),
                     "posting_date": date, "posting_time": self.t, "set_posting_time": 1,
                     "remarks": f"생산 완료 {w} ({g['rows'][0]['출발창고']}) 완제품 lot {lot}", "items": items})
        first_issue = min([x["일자"] for x in self.se_rows[w]] or [date])
        self.erp.set_value("Work Order", w, {"custom_fg_lot": lot, "custom_actual_start": first_issue,
                                             "custom_actual_end": date, "custom_yield_pct": f(r["수율_퍼센트"])})

    # ---------------- 판매 ----------------
    def op_SO(self, rows, date):
        name = rows[0]["수주번호"]
        if self.done("Sales Order", name):
            return
        r0 = rows[0]
        items = [{"item_code": r["SKU"], "qty": int(f(r["수량_병"])), "rate": f(r["단가_원"]), "uom": "병",
                  "delivery_date": r["납기요청일"], "customer_item_code": r["고객품번"], "warehouse": wh("WH-70")}
                 for r in rows]
        self.insert({"doctype": "Sales Order", "name": name, "customer": r0["고객"], "order_type": "Sales",
                     "transaction_date": r0["수주일"], "delivery_date": min(r["납기요청일"] for r in rows),
                     "currency": "KRW", "selling_price_list": "Standard Selling",
                     "custom_urgent": 1 if r0["긴급"] == "예" else 0,
                     "custom_note": "; ".join(sorted({r["비고"] for r in rows if r["비고"]})) or None,
                     "items": items})

    def mv_delivery(self, g, date):
        name = g["ref"]
        if self.done("Delivery Note", name):
            return
        rows = self.dn[name]
        items = []
        for r in rows:
            s = self.so[r["수주번호"]]
            rate = next(f(x["단가_원"]) for x in s if x["SKU"] == r["SKU"])
            items.append({"item_code": r["SKU"], "qty": int(f(r["수량_병"])), "rate": rate, "uom": "병",
                          "warehouse": wh("WH-70"), "batch_no": r["완제품lot"], "use_serial_batch_fields": 1,
                          "against_sales_order": r["수주번호"],
                          "so_detail": self.child("Sales Order", r["수주번호"], r["SKU"]),
                          "customer_item_code": r["고객품번"],
                          "custom_remaining_shelf_life_days": int(f(r["출하시잔여유효기간_일"])),
                          "custom_on_time": r["납기준수"]})
        self.insert({"doctype": "Delivery Note", "name": name, "customer": rows[0]["고객"],
                     "posting_date": rows[0]["실제출하일"], "posting_time": self.t, "set_posting_time": 1,
                     "currency": "KRW", "selling_price_list": "Standard Selling",
                     "custom_erp_entry_date": rows[0]["ERP입력일"], "items": items})

    # ---------------- 품질·설비·실사 ----------------
    def op_NCR(self, r, date):
        name = r["번호"]
        if self.done("Non Conformance", name):
            return
        proc = {"IQC 불합격": "SOP-02 입고·IQC", "출하검사 불합격": "SOP-04 출하검사와 출하",
                "고객 클레임": "SOP-05 고객 클레임 대응"}[r["구분"]]
        self.insert({"doctype": "Non Conformance", "name": name, "subject": f"[{r['구분']}] {r['품목']} {r['관련lot']}",
                     "procedure": proc, "status": "Resolved" if r["종결일"] else "Open",
                     "details": r["현상"], "corrective_action": r["조치"],
                     "custom_category": r["구분"], "custom_occurred_on": r["발생일"],
                     "custom_lot": r["관련lot"] or None, "custom_item": r["품목"] or None,
                     "custom_customer": r["고객"] or None, "custom_cause": r["원인"],
                     "custom_closed_on": r["종결일"] or None}, submit=False)

    def op_DT(self, r, date):
        name = f"DT-26-{r['_i']:03d}"
        if self.done("Downtime Entry", name):
            return
        emp = self.cache.get("_emp")
        if not emp:
            emp = self.erp.get_list("Employee", filters=[["first_name", "=", "정비팀"]])[0]["name"]
            self.cache["_emp"] = emp
        self.insert({"doctype": "Downtime Entry", "name": name, "workstation": r["설비"],
                     "from_time": f"{r['시작일']} 08:00:00", "to_time": f"{r['종료일']} 18:00:00",
                     "operator": emp,
                     "stop_reason": "Unplanned machine maintenance" if "교체" in r["사유"] and "정기" not in r["사유"] else "Other",
                     "remarks": r["사유"]}, submit=False)

    def op_RECON(self, rows, date):
        name = "SR-26-1215"
        if self.done("Stock Reconciliation", name):
            return
        items = []
        for r in rows:
            lot = r["lot"]
            item = r["품목"]
            data = self.erp.call("erpnext.stock.doctype.batch.batch.get_batch_qty", batch_no=lot, item_code=item, for_stock_levels=1) or []
            whs = [d for d in data if f(d.get("qty")) > EPS]
            if not whs:
                self.log(f"  실사: {lot} 재고 없음 → 건너뜀")
                continue
            w_ = whs[0]["warehouse"]
            cur = f(whs[0]["qty"])
            items.append({"item_code": item, "warehouse": w_, "batch_no": lot, "use_serial_batch_fields": 1,
                          "qty": r3(max(cur + f(r["차이"]), 0))})
        self.insert({"doctype": "Stock Reconciliation", "name": name, "purpose": "Stock Reconciliation",
                     "posting_date": rows[0]["실사일"], "posting_time": "23:00:00", "set_posting_time": 1,
                     "expense_account": f"Stock Adjustment - {ABBR}",
                     "remarks": "12월 재고 실사: " + "; ".join(f"{r['lot']} {r['비고']}" for r in rows),
                     "items": items})
