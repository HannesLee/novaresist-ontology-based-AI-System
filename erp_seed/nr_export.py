"""ERPNext에서 데이터 내보내기 — A안(ERP만)·B안·C안의 공통 입력.

고객사 ERP에서 데이터를 받는 상황을 그대로 재현한다: 화면(DocType)별로 표 하나씩 CSV로 내보낸다.
사용법:  python3 nr_export.py            → export_YYYYMMDD/ 폴더 + zip (Windows 다운로드 폴더에도 복사)
"""
import csv
import datetime as dt
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_client import ERP  # noqa: E402
from nr_load import load_env  # noqa: E402

# (부모 화면, [하위 표 화면들])
DOCTYPES = [
    # 기준정보
    ("Company", []), ("Warehouse", []), ("Item Group", []), ("UOM", []),
    ("Item", ["UOM Conversion Detail", "Item Supplier", "Item Customer Detail", "Item Default"]),
    ("Supplier", []), ("Supplier Group", []), ("Customer", []), ("Customer Group", []),
    ("Employee", []), ("Workstation", []), ("Workstation Type", []), ("Operation", []),
    ("BOM", ["BOM Item", "BOM Operation"]),
    ("Quality Inspection Template", ["Item Quality Inspection Parameter"]),
    ("Quality Inspection Parameter", []), ("Quality Procedure", []),
    ("NR Customer Approval", []),
    # 계획
    ("NR Sales Forecast", []), ("NR Production Plan", []),
    # 구매
    ("Material Request", ["Material Request Item"]),
    ("Purchase Order", ["Purchase Order Item"]),
    ("Purchase Receipt", ["Purchase Receipt Item"]),
    # 품질
    ("Quality Inspection", ["Quality Inspection Reading"]),
    ("Non Conformance", []),
    # 생산
    ("Work Order", ["Work Order Item", "Work Order Operation"]),
    ("Job Card", ["Job Card Time Log"]),
    ("Downtime Entry", []),
    # 재고
    ("Batch", []),
    ("Stock Entry", ["Stock Entry Detail"]),
    ("Stock Reconciliation", ["Stock Reconciliation Item"]),
    ("Serial and Batch Bundle", ["Serial and Batch Entry"]),
    ("Stock Ledger Entry", []),
    # 판매
    ("Sales Order", ["Sales Order Item"]),
    ("Delivery Note", ["Delivery Note Item"]),
]

# 내보내지 않는 시스템 열
# creation·modified 등은 데이터를 ERP에 넣은 시각이라 업무 의미가 없어 뺀다
DROP = {"_user_tags", "_comments", "_assign", "_liked_by", "_seen", "lft", "rgt", "old_parent",
        "creation", "modified", "owner", "modified_by", "lr_date"}
PAGE = 2000


def fetch(erp, doctype, parent=None):
    rows, start = [], 0
    while True:
        args = {"doctype": doctype, "fields": ["*"], "limit_start": start, "limit_page_length": PAGE,
                "order_by": "name asc"}
        if parent:
            args["parent"] = parent
        batch = erp.call_post("frappe.client.get_list", **args) or []
        if doctype == "Job Card":  # 작업카드 posting_date는 데이터를 넣은 날이라 뺀다
            for r in batch:
                r.pop("posting_date", None)
        if doctype == "Job Card Time Log":  # ERPNext가 자동으로 붙이는 빈 시간 기록 행은 뺀다
            batch_all = batch
            batch = [r for r in batch if r.get("from_time")]
            if len(batch_all) < PAGE:
                return rows + batch
            rows += batch
            start += PAGE
            continue
        rows += batch
        if len(batch) < PAGE:
            return rows
        start += PAGE


def write(path, rows):
    if not rows:
        return 0
    cols = []
    for r in rows:
        for k in r:
            if k not in cols and k not in DROP:
                cols.append(k)
    # 모든 행이 비어 있는 열은 뺀다
    cols = [c for c in cols if any(r.get(c) not in (None, "", 0, 0.0) for r in rows)
            or c in ("name", "docstatus", "parent")]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})
    return len(rows)


def main():
    env = load_env()
    erp = ERP(env["NR_URL"], env["NR_KEY"], env["NR_SECRET"])
    stamp = dt.date.today().strftime("%Y%m%d")
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, f"erp_export_{stamp}")
    os.makedirs(out, exist_ok=True)
    total = 0
    with open(os.path.join(out, "_목록.csv"), "w", encoding="utf-8-sig", newline="") as idx:
        iw = csv.writer(idx)
        iw.writerow(["파일", "ERPNext 화면", "상위 화면", "행 수"])
        for parent, children in DOCTYPES:
            n = write(os.path.join(out, parent.replace(" ", "_") + ".csv"), fetch(erp, parent))
            iw.writerow([parent.replace(" ", "_") + ".csv", parent, "", n])
            print(f"  {parent}: {n}")
            total += n
            for ch in children:
                m = write(os.path.join(out, ch.replace(" ", "_") + ".csv"), fetch(erp, ch, parent=parent))
                iw.writerow([ch.replace(" ", "_") + ".csv", ch, parent, m])
                print(f"    └ {ch}: {m}")
                total += m
    z = shutil.make_archive(out, "zip", here, os.path.basename(out))
    print(f"\n내보내기 완료: {total:,}행 → {z}")
    for d in glob.glob("/mnt/c/Users/*/Downloads"):
        try:
            shutil.copy(z, d)
            print(f"Windows 다운로드 폴더에도 복사: {d}")
            break
        except OSError:
            pass


if __name__ == "__main__":
    main()
