"""그래프 DB (LadybugDB — Kùzu 계열 내장형 그래프 DB, 질의 언어 Cypher).

온톨로지 정의(ontology.yaml)에서 그래프 스키마를 만든다.
  객체 종류  → 노드 표   (예: raw_lot, supplier)    열 = id, 이름, 상태 + 정의된 속성
  연결       → 관계 표   (예: 투입, 제조사)          같은 이름의 연결은 여러 FROM→TO 쌍을 가진 한 표
  측정값     → measurement 노드 + 측정값 관계        (검사 1건 → 항목별 측정값)
ERP가 바뀌어 객체를 다시 만들 때마다 새 그래프를 통째로 적재하고 바꿔 끼운다(몇 초).
"""
import csv
import json
import pathlib
import re
import shutil
import tempfile
import threading
import time

import real_ladybug as lb

WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|COPY|ALTER|INSTALL|LOAD|ATTACH|EXPORT|IMPORT|CALL\s+\w+\s*\(\s*\)\s*SET)\b", re.I)


def ident(s):
    """Cypher 이름: 공백·기호 → _  (예: '공정 설비' → 공정_설비, '수량(병)' → 수량_병)"""
    s = re.sub(r"[()（）]", "_", str(s))
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    if s and s[0].isdigit():
        s = "n" + s
    return s or "x"


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


class GraphDB:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = None
        self.conn = None
        self.schema_text = ""
        self.stats = {}
        self.log = []          # 최근 실행한 질의 (증거 화면용)
        cur = self.root / "CURRENT"
        if cur.exists():
            try:
                self._open(self.root / cur.read_text().strip())
                self.schema_text = (self.root / "SCHEMA.txt").read_text(encoding="utf-8")
                self.stats = json.loads((self.root / "STATS.json").read_text(encoding="utf-8"))
            except Exception:
                self.db = None

    def _open(self, path):
        self.db = lb.Database(str(path), read_only=False)
        self.conn = lb.Connection(self.db)

    # ---------------- 적재 ----------------
    def load(self, schema_dict, objects, links):
        """객체·연결 목록 → 새 그래프 DB. 끝나면 바꿔 끼운다."""
        t0 = time.time()
        objs = schema_dict["objects"]
        by_type = {}
        for o in objects:
            by_type.setdefault(o["type"], []).append(o)
        # 노드 표 정의: 정의된 속성 + 실제 값으로 형식 결정
        node_cols = {}
        for t, spec in objs.items():
            names = list((spec.get("properties") or {}).keys())
            for o in by_type.get(t, []):
                for k, v in o["props"].items():
                    if k not in names and not isinstance(v, (list, dict)):
                        names.append(k)
            cols = []
            for n in names:
                vals = [o["props"].get(n) for o in by_type.get(t, []) if o["props"].get(n) not in (None, "")]
                if any(isinstance(v, (list, dict)) for v in vals):
                    continue
                typ = "DOUBLE" if vals and all(_num(v) is not None for v in vals) else "STRING"
                cn = ident(n)
                if cn in ("id", "이름", "상태", "원본") or cn in [x[1] for x in cols]:
                    cn = "속성_" + cn
                cols.append((n, cn, typ))
            node_cols[t] = cols
        meas_types = [t for t, s in objs.items() if s.get("measurements")]
        # 관계 표 정의: 연결 이름별로 (FROM, TO) 쌍과 속성
        rel_pairs, rel_props = {}, {}
        for l in links:
            r = ident(l["rel"])
            rel_pairs.setdefault(r, set()).add((l["src_type"], l["dst_type"]))
            for k, v in (l.get("props") or {}).items():
                cur = rel_props.setdefault(r, {})
                if v not in (None, ""):
                    cur[k] = "DOUBLE" if (_num(v) is not None and cur.get(k) != "STRING") else "STRING"
                else:
                    cur.setdefault(k, "STRING")
        for t, spec in objs.items():  # 데이터가 아직 없는 연결도 스키마에는 만든다
            for l in spec.get("links") or []:
                for to in (l["to"] if isinstance(l["to"], list) else [l["to"]]):
                    if to != "*" and to in objs:
                        rel_pairs.setdefault(ident(l["rel"]), set()).add((t, to))

        new = self.root / f"g{int(time.time() * 1000)}"
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="graphcsv_"))
        db = lb.Database(str(new))
        c = lb.Connection(db)
        try:
            for t in objs:
                cols = "".join(f", {cn} {typ}" for _, cn, typ in node_cols[t])
                c.execute(f"CREATE NODE TABLE {t}(id STRING, 이름 STRING, 상태 STRING, 원본 STRING{cols}, PRIMARY KEY(id))")
            if meas_types:
                c.execute("CREATE NODE TABLE measurement(id STRING, 항목 STRING, 값 DOUBLE, 하한 DOUBLE, 상한 DOUBLE, 판정 STRING, PRIMARY KEY(id))")
            for r, pairs in rel_pairs.items():
                pp = ", ".join(f"FROM {a} TO {b}" for a, b in sorted(pairs))
                props = "".join(f", {ident(k)} {typ}" for k, typ in (rel_props.get(r) or {}).items())
                c.execute(f"CREATE REL TABLE {r}({pp}{props})")
            if meas_types:
                c.execute("CREATE REL TABLE 측정값(" + ", ".join(f"FROM {t} TO measurement" for t in meas_types) + ")")
            # 노드 적재
            for t in objs:
                rows = by_type.get(t, [])
                if not rows:
                    continue
                p = tmp / f"n_{t}.csv"
                with open(p, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["id", "이름", "상태", "원본"] + [cn for _, cn, _ in node_cols[t]])
                    for o in rows:
                        vals = []
                        for n, _, typ in node_cols[t]:
                            v = o["props"].get(n)
                            vals.append("" if v is None else (v if typ == "DOUBLE" else _s(v)))
                        w.writerow([o["id"], _s(o["title"]), o.get("status") or "",
                                    f"{o.get('src_doctype') or ''} {o.get('src_name') or ''}".strip()] + vals)
                c.execute(f"COPY {t} FROM '{p}' (HEADER=true, AUTO_DETECT=false, QUOTE='\"', ESCAPE='\"', DELIM=',')")
            # 측정값
            if meas_types:
                p = tmp / "n_measurement.csv"
                pe = {t: tmp / f"e_meas_{t}.csv" for t in meas_types}
                with open(p, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["id", "항목", "값", "하한", "상한", "판정"])
                    fe = {t: open(pe[t], "w", newline="", encoding="utf-8") for t in meas_types}
                    we = {t: csv.writer(fe[t]) for t in meas_types}
                    for t in meas_types:
                        we[t].writerow(["from", "to"])
                    for t in meas_types:
                        for o in by_type.get(t, []):
                            for m in o["props"].get("측정값") or []:
                                mid = f"{o['id']}:{m.get('항목')}"
                                lo, hi = _f(m.get("하한")), _f(m.get("상한"))
                                lo = "" if lo is None or lo < -1e8 else lo
                                hi = "" if hi is None or hi > 1e8 else hi
                                w.writerow([mid, m.get("항목"), _f(m.get("값")) if _f(m.get("값")) is not None else "", lo, hi, m.get("판정") or ""])
                                we[t].writerow([o["id"], mid])
                    for x in fe.values():
                        x.close()
                c.execute(f"COPY measurement FROM '{p}' (HEADER=true, AUTO_DETECT=false, QUOTE='\"', ESCAPE='\"', DELIM=',')")
                for t in meas_types:
                    c.execute(f"COPY 측정값 FROM '{pe[t]}' (HEADER=true, AUTO_DETECT=false, QUOTE='\"', ESCAPE='\"', DELIM=',', from='{t}', to='measurement')")
            # 관계 적재
            groups = {}
            for l in links:
                groups.setdefault((ident(l["rel"]), l["src_type"], l["dst_type"]), []).append(l)
            for (r, a, b), ls in groups.items():
                keys = list((rel_props.get(r) or {}).keys())
                p = tmp / f"e_{r}_{a}_{b}.csv"
                with open(p, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["from", "to"] + [ident(k) for k in keys])
                    for l in ls:
                        w.writerow([l["src_id"], l["dst_id"]] + ["" if (l.get("props") or {}).get(k) is None
                                                                 else _s(l["props"][k]) for k in keys])
                opt = f", from='{a}', to='{b}'" if len(rel_pairs[r]) > 1 else ""
                c.execute(f"COPY {r} FROM '{p}' (HEADER=true, AUTO_DETECT=false, QUOTE='\"', ESCAPE='\"', DELIM=','{opt})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        del c
        del db
        text = self._describe(schema_dict, node_cols, rel_pairs, rel_props, bool(meas_types))
        with self.lock:
            old = self.db
            self.conn = None
            self.db = None
            del old
            self._open(new)
            (self.root / "CURRENT").write_text(new.name)
            (self.root / "SCHEMA.txt").write_text(text, encoding="utf-8")
            self.schema_text = text
            self.stats = self._count()
            self.stats["적재(초)"] = round(time.time() - t0, 2)
            (self.root / "STATS.json").write_text(json.dumps(self.stats, ensure_ascii=False), encoding="utf-8")
        for d in self.root.glob("g*"):  # 지난 그래프 정리
            if d.name != new.name:
                shutil.rmtree(d, ignore_errors=True)
        return self.stats

    def _describe(self, d, node_cols, rel_pairs, rel_props, meas):
        lines = ["노드 표 (라벨: 현업 이름 — 열)"]
        for t, spec in d["objects"].items():
            cols = ", ".join(["id", "이름", "상태"] + [cn for _, cn, _ in node_cols[t]])
            lines.append(f"- {t}: {spec['name']} — {cols}")
        if meas:
            lines.append("- measurement: 검사 측정값 — id, 항목(예: '금속 Zn', '수분', '순도'), 값, 하한, 상한, 판정")
        lines.append("관계 표 (이름: FROM→TO 쌍 [속성])")
        for r, pairs in sorted(rel_pairs.items()):
            props = ", ".join(ident(k) for k in (rel_props.get(r) or {}))
            lines.append(f"- {r}: " + ", ".join(f"{a}→{b}" for a, b in sorted(pairs)) + (f" [{props}]" if props else ""))
        if meas:
            lines.append("- 측정값: inspection→measurement")
        return "\n".join(lines)

    def _count(self):
        out = {"노드": 0, "관계": 0}
        try:
            out["노드"] = int(self.conn.execute("MATCH (n) RETURN count(n)").get_as_df().iloc[0, 0])
            out["관계"] = int(self.conn.execute("MATCH ()-[r]->() RETURN count(r)").get_as_df().iloc[0, 0])
        except Exception:
            pass
        return out

    # ---------------- 질의 ----------------
    def query(self, cypher, params=None, limit=200, who="함수"):
        """읽기 전용 Cypher. 결과 [dict]."""
        if WRITE.search(cypher):
            raise ValueError("읽기 전용입니다(CREATE·SET·DELETE 등은 쓸 수 없음)")
        t0 = time.time()
        with self.lock:
            if self.conn is None:
                raise RuntimeError("그래프 DB가 아직 준비되지 않았습니다")
            r = self.conn.execute(cypher, params or {})
            df = r.get_as_df()
        rows = json.loads(df.head(limit).to_json(orient="records", force_ascii=False))
        self.log.append({"at": time.strftime("%H:%M:%S"), "who": who, "cypher": cypher, "params": params or {},
                         "rows": len(df), "ms": int((time.time() - t0) * 1000)})
        self.log = self.log[-300:]
        return rows

    def scalar(self, cypher, params=None):
        rows = self.query(cypher, params, limit=1)
        return list(rows[0].values())[0] if rows else None


def _s(v):
    """CSV 한 줄에 들어가게: 줄바꿈 → 공백"""
    return str(v).replace("\r", " ").replace("\n", " ")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
