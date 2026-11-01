"""4단계: 마무리 — 검증(원본 CSV와 건수·재고 비교) + 문서번호 자동 채번 복구."""
from collections import defaultdict

import nr_setup
from nr_tx import EPS, Loader


def run(erp, data_dir, log=print, restore_naming=True):
    user = erp.call("frappe.auth.get_logged_user")
    L = Loader(erp, data_dir, user, log=lambda *a: None)
    import sys
    until = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] in ("finish", "all") else None
    L.build(until=until)
    E = L.e
    log("[검증] 문서 건수 (원본 → ERPNext)")
    from collections import Counter
    c = Counter()
    for _, kind, d in L.ops:
        if kind == "MOVE":
            c[{"입고": "Purchase Receipt", "출하": "Delivery Note", "IQC 합격": "Quality Inspection",
               "IQC 불합격": "Quality Inspection", "출하검사": "Quality Inspection"}.get(d["kind"], "-")] += 1
        else:
            c[{"MR": "Material Request", "PO": "Purchase Order", "SO": "Sales Order", "WO": "Work Order",
               "GR_DUP": "Purchase Receipt", "QI_ONLY": "Quality Inspection", "NCR": "Non Conformance",
               "DT": "Downtime Entry"}.get(kind, "-")] += 1
    expect = {k: c[k] for k in ["Material Request", "Purchase Order", "Purchase Receipt", "Quality Inspection",
                                 "Work Order", "Sales Order", "Delivery Note", "Non Conformance", "Downtime Entry"]}
    expect["NR Sales Forecast"] = sum(1 for r in E["sales_forecast"] if r["작성일"] <= L.until)
    expect["NR Production Plan"] = sum(1 for r in E["production_plan"] if r["계획월"] <= L.until[:7])
    log(f"  기준일 {L.until}")
    bad = 0
    for dt_, n in expect.items():
        got = erp.call("frappe.client.get_count", doctype=dt_)
        ok = got == n
        bad += 0 if ok else 1
        log(f"  {'OK ' if ok else '차이'} {dt_}: {n} → {got}")
    for dt_ in ("Purchase Order", "Sales Order"):
        n = erp.call("frappe.client.get_count", doctype=dt_, filters={"docstatus": 1, "status": "Draft"})
        if n:
            bad += 1
            log(f"  차이 {dt_}: 제출됐는데 상태가 Draft인 문서 {n}건")
    jc = erp.call("frappe.client.get_count", doctype="Job Card", filters={"docstatus": 1})
    log(f"  참고 Job Card(제출): {jc} (원본 작업 기록 {len(E['job_card'])}행, 2025 완료분 제외)")

    log("[검증] 기준일 재고 (lot·창고별, 원본 이력으로 계산한 값과 비교)")
    expected = defaultdict(float)
    for (item, w, lot), q in L.led.items():
        if abs(q) > EPS:
            expected[(item, w, lot)] += q
    # 12월 실사 차이 반영 (기준일이 실사일 이후일 때만)
    for r in (E["stock_reconciliation"] if E["stock_reconciliation"] and E["stock_reconciliation"][0]["실사일"] <= L.until else []):
        for k in list(expected):
            if k[2] == r["lot"]:
                expected[k] += float(r["차이"])
                break
    got = defaultdict(float)
    items = sorted({k[0] for k in expected} | set(L.raw) | set(L.fg))
    for item in items:
        if item in L.batch_items:
            for d in erp.call("erpnext.stock.doctype.batch.batch.get_batch_qty", item_code=item, for_stock_levels=1) or []:
                if abs(float(d.get("qty") or 0)) > EPS:
                    got[(item, d["warehouse"], d["batch_no"])] += float(d["qty"])
        else:
            for d in erp.get_list("Bin", filters=[["item_code", "=", item]], fields=["warehouse", "actual_qty"]):
                if abs(float(d["actual_qty"])) > EPS:
                    got[(item, d["warehouse"], None)] += float(d["actual_qty"])
    diffs = []
    for k in set(expected) | set(got):
        a, b = expected.get(k, 0), got.get(k, 0)
        tol = 1.0 if L.stock_uom[k[0]] in ("EA", "병") else 0.01
        if abs(a - b) > tol:
            diffs.append((k, a, b))
    log(f"  비교 {len(set(expected) | set(got))}건, 차이 {len(diffs)}건")
    for k, a, b in sorted(diffs, key=lambda x: str(x[0]))[:20]:
        log(f"    {k}: 원본 {a:.3f} / ERP {b:.3f}")
    if restore_naming:
        log("[마무리] 새 문서는 다시 자동 채번")
        nr_setup.set_prompt_naming(erp, False, log)
    log("[완료] " + ("모두 일치" if not bad and not diffs else f"차이 {bad + len(diffs)}건 — 위 목록 확인"))
