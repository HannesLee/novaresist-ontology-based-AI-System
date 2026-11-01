"""ontology.yaml 읽기·해석·검증.

정의 파일의 경로 문자열을 ERP 화면 정의(meta)와 맞춰 '어떻게 읽을지'로 바꾼다.

경로 종류
  field          이 문서의 필드                         예) supplier
  child          이 문서의 하위 표 필드                  예) Purchase Order Item.rate
  forward        이 문서(또는 하위 표)가 가리키는 문서    예) Material Request.transaction_date
  reverse        이 문서를 가리키는 문서                 예) Job Card.workstation (Job Card.work_order → Work Order)
  reverse_child  이 문서를 가리키는 문서의 하위 표        예) Stock Entry Detail.batch_no, BOM Item.item_code
"""
import re

import yaml

# 하위 표 → 상위 문서 (화면 정의에서 못 찾을 때 쓰는 기본값)
CHILD_PARENT = {
    "Stock Entry Detail": "Stock Entry", "BOM Item": "BOM", "Quality Inspection Reading": "Quality Inspection",
    "Item Supplier": "Item", "Item Customer Detail": "Item", "Purchase Order Item": "Purchase Order",
    "Purchase Receipt Item": "Purchase Receipt", "Sales Order Item": "Sales Order",
    "Delivery Note Item": "Delivery Note", "Material Request Item": "Material Request",
    "Job Card Time Log": "Job Card",
}
STD_FIELDS = {"name", "docstatus", "idx", "creation", "modified", "owner", "parent", "parenttype", "parentfield"}
COND = re.compile(r"^\s*([\w.]+)\s*(=|!=|in)\s*(.+?)\s*$")


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_cond(s):
    """'필드 op 값' → (필드, op, 값). 값: 목록, '@객체', 빈 문자열('') 또는 글자."""
    m = COND.match(s)
    if not m:
        raise ValueError(f"조건 문법 오류: {s}")
    f, op, v = m.groups()
    if v.startswith("[") and v.endswith("]"):
        v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
    elif v in ("''", '""'):
        v = ""
    return f, op, v


def targets(to):
    return to if isinstance(to, list) else [to]


class Schema:
    def __init__(self, d, erp=None):
        self.d = d
        self.objects = d["objects"]
        self.erp = erp
        self.meta = {}
        self.plans = {}       # (source doctype, path) → plan
        self.problems = []

    # ---------- ERP 화면 정의 ----------
    def m(self, dt):
        if dt not in self.meta:
            self.meta[dt] = self.erp.meta(dt)
        return self.meta[dt]

    def fields(self, dt):
        return {f["fieldname"] for f in self.m(dt)["fields"]} | STD_FIELDS

    def tables(self, dt):
        return {f["options"]: f["fieldname"] for f in self.m(dt)["fields"] if f["fieldtype"] in ("Table", "Table MultiSelect")}

    def links_of(self, dt, target):
        return [f["fieldname"] for f in self.m(dt)["fields"]
                if f["fieldtype"] in ("Link", "Dynamic Link") and f["options"] == target]

    def parent_of(self, child):
        return CHILD_PARENT.get(child)

    # ---------- 객체의 출처 ----------
    def sources(self, key):
        s = self.objects[key]["source"]
        if "doctype" in s:
            return [s["doctype"]]
        if "doctypes" in s:
            return list(s["doctypes"])
        if "derived_from" in s:
            return [s["derived_from"].split(".")[0]]
        return []

    # ---------- 경로 해석 ----------
    def plan(self, src, path, rows_dt=None):
        """src 문서 기준 경로를 해석한다. rows_dt: 줄 단위 객체(수주·출하)의 하위 표."""
        k = (src, path, rows_dt)
        if k in self.plans:
            return self.plans[k]
        p = self._plan(src, path, rows_dt)
        self.plans[k] = p
        return p

    def _plan(self, src, path, rows_dt):
        if "." not in path:
            if path.startswith("_") or path in self.fields(src) or (rows_dt and path in self.fields(rows_dt)):
                return {"kind": "field", "field": path}
            return {"kind": "missing", "why": f"{src}에 필드 '{path}' 없음"}
        a, f = path.split(".", 1)
        if a == "parent":
            return {"kind": "parent", "field": f}
        if rows_dt and a == rows_dt:
            return self._chk({"kind": "row", "dt": a, "field": f}, a, f)
        if a == src:
            return self._chk({"kind": "field", "field": f}, src, f)
        tables = self.tables(src)
        if a in tables:
            return self._chk({"kind": "child", "dt": a, "field": f}, a, f)
        # 이 문서(또는 하위 표)가 가리키는 문서
        for holder in [src] + list(tables):
            lf = self.links_of(holder, a)
            if lf:
                return self._chk({"kind": "forward", "dt": a, "via_dt": holder, "via_field": lf[0], "field": f}, a, f)
        # 이 문서를 가리키는 문서 (하위 표면 그 상위 문서가 가리키는지 먼저 본다)
        par = self.parent_of(a) if self.m(a).get("istable") else None
        if par:
            lf = self.links_of(par, src)
            if lf:
                return self._chk({"kind": "reverse_child", "dt": a, "parent_dt": par, "link": lf[0], "field": f}, a, f)
        lf = self.links_of(a, src)
        if lf and not par:
            return self._chk({"kind": "reverse", "dt": a, "link": lf[0], "field": f}, a, f)
        return {"kind": "missing", "why": f"{src}에서 '{a}'로 가는 길을 못 찾음"}

    def _chk(self, p, dt, f):
        if f not in self.fields(dt):
            return {"kind": "missing", "why": f"{dt}에 필드 '{f}' 없음"}
        return p

    # ---------- 읽어야 할 ERP 화면 ----------
    def fetch_list(self):
        """[(doctype, parent doctype 또는 None)] — 객체를 만드는 데 필요한 모든 화면."""
        need = {}
        for key, o in self.objects.items():
            src = self.sources(key)
            if not src:
                continue
            rows_dt = o["source"].get("rows")
            for s in src:
                need.setdefault(s, None)
                if rows_dt:
                    need[rows_dt] = s
                for path in self._paths(o):
                    p = self.plan(s, path, rows_dt)
                    if p["kind"] == "child":
                        need[p["dt"]] = s
                    elif p["kind"] == "forward":
                        need.setdefault(p["dt"], None)
                        if p["via_dt"] != s:
                            need[p["via_dt"]] = s
                    elif p["kind"] == "reverse":
                        need.setdefault(p["dt"], None)
                    elif p["kind"] == "reverse_child":
                        need.setdefault(p["parent_dt"], None)
                        need[p["dt"]] = p["parent_dt"]
            meas = o.get("measurements")
            if meas:
                need[meas["child"]] = src[0]
        return [(dt, par) for dt, par in need.items()]

    def _paths(self, o):
        out = list((o.get("properties") or {}).values()) + list(o.get("name_fields") or [])
        if o.get("title"):
            out.append(o["title"])
        for l in o.get("links") or []:
            out.append(l["via"])
            if l.get("fallback"):
                out.append(l["fallback"])
        derived = o["source"].get("derived_from")
        if derived:
            out.append(derived)
        return [p for p in out if isinstance(p, str)]

    # ---------- 검증 ----------
    def validate(self):
        """정의 파일의 모든 경로가 ERP에 실제로 있는지 확인한다."""
        probs = []
        for key, o in self.objects.items():
            src = self.sources(key)
            if not src:
                continue
            rows_dt = o["source"].get("rows")
            for s in src:
                for path in self._paths(o):
                    p = self.plan(s, path, rows_dt)
                    if p["kind"] == "missing" and not (len(src) > 1):
                        probs.append(f"{key}: {path} → {p['why']}")
                for l in o.get("links") or []:
                    for t in targets(l["to"]):
                        if t != "*" and t not in self.objects:
                            probs.append(f"{key}.{l['rel']}: 대상 객체 '{t}' 정의 없음")
                    for prop in (l.get("props") or {}).values():
                        pass
            if len(src) > 1:  # 여러 화면 출처: 어느 한 화면에라도 있으면 된다
                for path in self._paths(o):
                    if all(self.plan(s, path, rows_dt)["kind"] == "missing" for s in src):
                        probs.append(f"{key}: {path} → 어느 출처 화면에도 없음")
        self.problems = probs
        return probs
