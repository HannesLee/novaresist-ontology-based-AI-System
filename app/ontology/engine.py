"""정의 파일(Schema) + ERP 원본(raw) → 객체·연결·별칭.

ERP 원본이 바뀌면 build()를 다시 부른다. 수천 건 기준 몇 초면 끝나서 매번 통째로 다시 만든다.
"""
import hashlib
import json
from collections import defaultdict

from app.ontology.schema import parse_cond, targets


class Raw:
    """ERP 원본 행을 doctype별로 들고 있고, 이름·상위 문서·연결 필드로 찾게 해 준다."""

    def __init__(self, rows_by_dt):
        self.rows = rows_by_dt
        self.by_name = {dt: {r["name"]: r for r in rows} for dt, rows in rows_by_dt.items()}
        self._children = {}
        self._rev = {}

    def get(self, dt, name):
        return self.by_name.get(dt, {}).get(name)

    def children(self, dt, parent):
        if dt not in self._children:
            idx = defaultdict(list)
            for r in self.rows.get(dt, []):
                idx[r.get("parent")].append(r)
            for v in idx.values():
                v.sort(key=lambda r: r.get("idx") or 0)
            self._children[dt] = idx
        return self._children[dt].get(parent, [])

    def referring(self, dt, field, value):
        k = (dt, field)
        if k not in self._rev:
            idx = defaultdict(list)
            for r in self.rows.get(dt, []):
                idx[r.get(field)].append(r)
            self._rev[k] = idx
        return self._rev[k].get(value, [])


def empty(v):
    return v is None or v == "" or v == []


class Engine:
    def __init__(self, schema, raw):
        self.s = schema
        self.raw = raw
        self.ids = {}          # type → {id: object}
        self.missing_computed = set()

    # ---------- 경로 값 ----------
    def values(self, src, path, doc, row=None, rows_dt=None):
        """경로 값 목록 [(값, 그 값이 나온 행, 상위 문서)]"""
        p = self.s.plan(src, path, rows_dt)
        k = p["kind"]
        if k == "field":
            f = p["field"]
            if f == "_doctype":
                return [(src, doc, doc)]
            if row is not None and f in row and rows_dt and f not in doc:
                return [(row.get(f), row, doc)]
            return [(doc.get(f), doc, doc)]
        if k == "row":
            return [(row.get(p["field"]), row, doc)] if row is not None else \
                [(r.get(p["field"]), r, doc) for r in self.raw.children(p["dt"], doc["name"])]
        if k == "parent":
            return [(doc.get(p["field"]), doc, doc)]
        if k == "child":
            return [(r.get(p["field"]), r, doc) for r in self.raw.children(p["dt"], doc["name"])]
        if k == "forward":
            holders = [doc] if p["via_dt"] == src else self.raw.children(p["via_dt"], doc["name"])
            out, seen = [], set()
            for h in holders:
                n = h.get(p["via_field"])
                t = self.raw.get(p["dt"], n) if n else None
                if t and n not in seen:
                    seen.add(n)
                    out.append((t.get(p["field"]), t, t))
            return out
        if k == "reverse":
            return [(r.get(p["field"]), r, r) for r in self.raw.referring(p["dt"], p["link"], doc["name"])]
        if k == "reverse_child":
            out = []
            for par in self.raw.referring(p["parent_dt"], p["link"], doc["name"]):
                if par.get("docstatus") == 2:
                    continue
                out += [(r.get(p["field"]), r, par) for r in self.raw.children(p["dt"], par["name"])]
            return out
        return []

    def first(self, src, path, doc, row=None, rows_dt=None):
        vals = [v for v, _, _ in self.values(src, path, doc, row, rows_dt) if not empty(v)]
        if not vals:
            return None
        uniq = list(dict.fromkeys(json.dumps(v, default=str) for v in vals))
        return vals[0] if len(uniq) == 1 else [json.loads(u) for u in uniq]

    # ---------- 조건 ----------
    def match(self, cond, row, parent):
        f, op, v = parse_cond(cond)
        if f.startswith("parent."):
            x = (parent or {}).get(f[7:])
        else:
            x = row.get(f)
        x = "" if x is None else x
        if op == "=":
            return str(x) == str(v)
        if op == "!=":
            return str(x) != str(v)
        if op == "in":
            if isinstance(v, str) and v.startswith("@"):
                return x in self.objects_of(v[1:])
            return x in v
        return False

    # ---------- 객체 만들기 ----------
    def objects_of(self, key):
        if key not in self.ids:
            self.ids[key] = {}  # 순환 방지
            self.ids[key] = self._build_type(key)
        return self.ids[key]

    def _key(self, tmpl, doc, row):
        if ":" not in tmpl:
            return doc.get(tmpl) if tmpl in doc else tmpl
        parts = []
        for f in tmpl.split(":"):
            src = row if (row is not None and f in row and f not in ("name",)) else doc
            parts.append(str(src.get(f)))
        return ":".join(parts)

    def _build_type(self, key):
        o = self.s.objects[key]
        src = o["source"]
        out = {}
        if "documents" in src:
            return out  # 문서 사건은 docs_ingest가 만든다
        if "derived_from" in src:
            dt, f = src["derived_from"].split(".")
            groups = defaultdict(list)
            for r in self.raw.rows.get(dt, []):
                if r.get(f) and r.get("docstatus") != 2:
                    groups[r[f]].append(r)
            for v, rs in groups.items():
                out[v] = {"type": key, "id": v, "title": v, "props": {}, "src_doctype": dt, "src_name": v,
                          "status": "", "_rows": rs, "_src": dt}
            return out
        rows_dt = src.get("rows")
        flt = src.get("filter")
        for dt in self.s.sources(key):
            for doc in self.raw.rows.get(dt, []):
                if flt and not self.match(flt, doc, None):
                    continue
                units = [(doc, r) for r in self.raw.children(rows_dt, doc["name"])] if rows_dt else [(doc, None)]
                for d, r in units:
                    oid = self._key(o.get("key", "name"), d, r)
                    props = {}
                    for pname, path in (o.get("properties") or {}).items():
                        if self.s.plan(dt, path, rows_dt)["kind"] == "missing":
                            continue
                        props[pname] = self.first(dt, path, d, r, rows_dt)
                    meas = o.get("measurements")
                    if meas:
                        props["측정값"] = [{k: m.get(f) for k, f in meas["fields"].items()}
                                         for m in self.raw.children(meas["child"], d["name"])]
                    title = self.first(dt, o["title"], d, r, rows_dt) if o.get("title") else oid
                    status = {0: "초안", 1: "확정", 2: "취소"}.get(d.get("docstatus"), "")
                    out[oid] = {"type": key, "id": oid, "title": str(title or oid), "props": props,
                                "src_doctype": dt, "src_name": d["name"], "status": status,
                                "_doc": d, "_row": r, "_src": dt}
        return out

    # ---------- 연결 ----------
    def _target(self, types, value, row, doc):
        """값이 가리키는 대상 객체 (type, id) 목록."""
        out = []
        for t in types:
            ids = self.objects_of(t)
            if value in ids:
                out.append((t, value))
                continue
            tkey = self.s.objects[t].get("key", "name")
            if ":" in str(tkey):  # 줄 단위 객체(수주 줄): '문서번호:품목'
                second = tkey.split(":")[1]
                for cand in (row, doc):
                    if cand and cand.get(second) and f"{value}:{cand[second]}" in ids:
                        out.append((t, f"{value}:{cand[second]}"))
                        break
                else:
                    out += [(t, i) for i in ids if str(i).startswith(f"{value}:")]
        return out

    def build_links(self, key):
        o = self.s.objects[key]
        links = []
        rows_dt = o["source"].get("rows")
        for obj in self.objects_of(key).values():
            for l in o.get("links") or []:
                types = [t for t in targets(l["to"]) if t != "*"]
                if not types:
                    continue
                vals = self._link_values(obj, l, rows_dt)
                if not vals and l.get("fallback"):
                    vals = self._link_values(obj, {**l, "via": l["fallback"], "where": None}, rows_dt)
                agg = {}
                for v, r, par in vals:
                    for item in self._parse(l, v):
                        for t, tid in self._target(types, item, r, obj.get("_doc")):
                            props = {}
                            for pn, pf in (l.get("props") or {}).items():
                                x = r.get(pf) if r is not None and pf in r else (par or {}).get(pf)
                                props[pn] = x
                            if l.get("parse"):
                                props["조합"] = ", ".join(x.strip() for x in str(v).split(",") if item in x.split("@"))
                            k = (t, tid)
                            if k in agg:
                                for pn, x in props.items():
                                    if isinstance(x, (int, float)) and isinstance(agg[k].get(pn), (int, float)):
                                        agg[k][pn] += x
                            else:
                                agg[k] = props
                for (t, tid), props in agg.items():
                    links.append({"src_type": key, "src_id": obj["id"], "rel": l["rel"], "dst_type": t,
                                  "dst_id": tid, "props": props})
        return links

    def _link_values(self, obj, l, rows_dt):
        if "_rows" in obj:  # 파생 객체(필터 lot): 근거 행에서 바로 읽는다
            f = l["via"].split(".")[-1]
            return [(r.get(f), r, r) for r in obj["_rows"] if not empty(r.get(f))]
        vals = self.values(obj["_src"], l["via"], obj["_doc"], obj.get("_row"), rows_dt)
        if l.get("where"):
            vals = [x for x in vals if all(self.match(c, x[1], x[2]) for c in l["where"])]
        return [x for x in vals if not empty(x[0])]

    @staticmethod
    def _parse(l, v):
        if isinstance(v, list):
            return v
        if l.get("parse") in ("pair_material", "pair_supplier"):
            i = 0 if l["parse"] == "pair_material" else 1
            return list(dict.fromkeys(p.strip().split("@")[i] for p in str(v).split(",") if "@" in p))
        return [v]

    # ---------- 전체 ----------
    def build(self):
        objects, links, aliases = [], [], []
        for key in self.s.objects:
            self.objects_of(key)
        for key, o in self.s.objects.items():
            links += self.build_links(key)
            rows_dt = o["source"].get("rows")
            for obj in self.objects_of(key).values():
                names = {obj["id"], obj["title"]}
                for path in o.get("name_fields") or []:
                    if "_doc" in obj:
                        for v, _, _ in self.values(obj["_src"], path, obj["_doc"], obj.get("_row"), rows_dt):
                            if not empty(v):
                                names.add(str(v))
                for n in list(names):  # '한빛폴리텍(가상)' → '한빛폴리텍'도 별칭
                    if "(" in n and not n.startswith("("):
                        names.add(n.split("(")[0].strip())
                for n in names:
                    aliases.append((key, obj["id"], n))
                clean = {k: v for k, v in obj.items() if not k.startswith("_")}
                clean["hash"] = hashlib.md5(json.dumps([clean["title"], clean["props"], clean["status"]],
                                                       ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
                objects.append(clean)
        return objects, links, aliases
