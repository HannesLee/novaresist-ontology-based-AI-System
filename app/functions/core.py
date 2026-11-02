"""함수 층: AI와 화면이 부르는 질문 도구.

숫자는 모두 여기서 계산한다. AI는 이 결과만 인용한다.
결과에는 늘 '근거'(객체 id·ERP 문서번호)를 담는다.
"""
import datetime as dt
import math
import re
import statistics
from collections import Counter, defaultdict

from app import config
from app.ontology.store import norm

BIG = 1e8  # ERP가 빈 상·하한을 ±1e9로 채운다


def today():
    return dt.date.fromisoformat(config.AS_OF) if config.AS_OF else dt.date.today()


def d(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def wh(w):
    """'WH-20 - NR' → 'WH-20'"""
    return str(w or "").split(" - ")[0]


WH_STATE = {"WH-10": "IQC 전", "WH-30A": "IQC 전", "WH-20": "합격", "WH-21": "합격", "WH-30B": "합격",
            "WH-50": "합격", "WH-40": "보류", "WH-60": "출하검사 대기", "WH-70": "출하 가능", "WH-WIP": "공정 투입"}


class Onto:
    def __init__(self, store, schema_dict, erp=None, docs=None, graph=None):
        self.s = store
        self.d = schema_dict
        self.erp = erp
        self.docs = docs
        self.g = graph
        self._cache = {}

    def clear(self):
        self._cache = {}

    # ===================== 그래프 DB =====================
    def gq(self, cypher, params=None, who="함수"):
        """그래프 DB(Cypher) 질의. 실행 기록은 증거 화면에 남는다."""
        if not self.g:
            raise RuntimeError("그래프 DB 없음")
        return self.g.query(cypher, params or {}, limit=5000, who=who)

    def graph_query(self, cypher, params=None):
        """AI가 직접 쓰는 읽기 전용 Cypher 질의 (최대 200행)."""
        try:
            rows = self.g.query(cypher, params or {}, limit=200, who="Claude")
        except Exception as e:
            return {"오류": str(e)[:600], "도움말": "라벨·관계 이름은 시스템 프롬프트의 그래프 스키마를 쓰세요. 공백은 _ 입니다."}
        return {"행 수": len(rows), "결과": rows}

    # ===================== 기본 =====================
    def type_name(self, t):
        return self.d["objects"].get(t, {}).get("name", t)

    def resolve_type(self, t):
        """'원재료 lot', '자재 lot', 'raw_lot' → 'raw_lot'"""
        if not t:
            return None
        if t in self.d["objects"]:
            return t
        n = norm(t)
        for k, o in self.d["objects"].items():
            if n in [norm(o["name"])] + [norm(a) for a in o.get("aliases", [])]:
                return k
        return None

    def find(self, text, type=None, limit=10):
        """이름·코드·별칭으로 객체를 찾는다. 정확히 같은 이름 → 포함하는 이름 순."""
        t = self.resolve_type(type) if type else None
        n = norm(text)
        q = "SELECT DISTINCT type, id FROM aliases WHERE norm=?" + (" AND type=?" if t else "")
        hits = self.s.db.execute(q, (n, t) if t else (n,)).fetchall()
        if not hits and len(n) >= 2:
            q = "SELECT DISTINCT type, id FROM aliases WHERE norm LIKE ?" + (" AND type=?" if t else "") + " LIMIT ?"
            hits = self.s.db.execute(q, (f"%{n}%", t, limit * 3) if t else (f"%{n}%", limit * 3)).fetchall()
        out = []
        for ty, i in hits[:limit]:
            o = self.s.obj(ty, i)
            if o:
                out.append({"type": ty, "종류": self.type_name(ty), "id": i, "이름": o["title"]})
        if not out and not t:  # 객체 종류 이름 자체를 물은 경우
            k = self.resolve_type(text)
            if k:
                return [{"type": k, "종류": self.type_name(k), "id": None,
                         "이름": f"{self.type_name(k)} 전체 {len(self.s.objs(k))}개"}]
        return out

    def _resolve(self, ref, type=None):
        """id 또는 이름 → (type, id). 못 찾으면 (None, None)"""
        if isinstance(ref, (tuple, list)) and len(ref) == 2:
            return tuple(ref)
        t = self.resolve_type(type) if type else None
        if t and self.s.obj(t, ref):
            return t, ref
        r = self.find(ref, t, limit=1)
        return (r[0]["type"], r[0]["id"]) if r and r[0]["id"] else (None, None)

    def get(self, ref, type=None, with_links=True):
        """객체 하나: 속성 + 계산 속성 + 연결 요약 + 관련 문서."""
        t, i = self._resolve(ref, type)
        if not t:
            return {"오류": f"'{ref}'를 찾지 못했습니다", "후보": self.find(str(ref))}
        o = self.s.obj(t, i)
        spec = self.d["objects"][t]
        out = {"종류": spec["name"], "type": t, "id": i, "이름": o["title"], "ERP 상태": o["status"],
               "ERP 문서": f"{o['src_doctype']} {o['src_name']}", "속성": o["props"]}
        comp = {}
        for name, fn in (spec.get("computed") or {}).items():
            f = COMPUTED.get(fn)
            try:
                comp[name] = f(self, t, i, o) if f else "미구현"
            except Exception as e:  # 계산 실패가 전체 답을 막지 않게
                comp[name] = f"계산 실패: {e}"
        if comp:
            out["계산 속성"] = comp
        if with_links:
            out["연결"] = self.link_summary(t, i)
        if self.docs:
            out["관련 문서"] = self.docs.mentions(t, i, o["title"])[:10]
        return out

    def link_summary(self, t, i, per_rel=12):
        out = {}
        for l in self.s.links_from(t, i):
            out.setdefault(f"{l['rel']} →", []).append(self._ref(l["dst_type"], l["dst_id"], l["props"]))
        for l in self.s.links_to(t, i):
            out.setdefault(f"← {l['rel']} ({self.type_name(l['src_type'])})", []).append(
                self._ref(l["src_type"], l["src_id"], l["props"]))
        for k, v in out.items():
            if len(v) > per_rel:
                out[k] = v[:per_rel] + [f"… 외 {len(v) - per_rel}개"]
        return out

    def _ref(self, t, i, props=None):
        o = self.s.obj(t, i)
        r = {"id": i, "type": t}
        if o and o["title"] != i:
            r["이름"] = o["title"]
        if props:
            r.update({k: v for k, v in props.items() if v not in (None, "")})
        return r

    def list_objects(self, type, where=None, limit=50):
        """한 종류의 객체 목록. where: {속성: 값} (값이 같거나 포함)"""
        t = self.resolve_type(type)
        if not t:
            return {"오류": f"객체 종류 '{type}' 없음", "종류 목록": [o["name"] for o in self.d["objects"].values()]}
        rows = []
        for o in self.s.objs(t):
            ok = True
            for k, v in (where or {}).items():
                x = o["props"].get(k, o["title"] if k in ("이름", "id") else None)
                if x is None or (str(v) not in str(x)):
                    ok = False
                    break
            if ok:
                rows.append({"id": o["id"], "이름": o["title"], "상태": o["status"], **o["props"]})
        return {"종류": self.type_name(t), "전체": len(rows), "목록": rows[:limit]}

    # ===================== 실시간 재고 =====================
    def lot_stock(self, lot_id, item=None):
        """lot의 지금 위치·수량 (ERP에서 바로 읽는다)."""
        if not self.erp:
            return []
        if not item:
            for t in ("raw_lot", "fg_lot"):
                ls = self.s.links_from(t, lot_id, "종류")
                if ls:
                    item = ls[0]["dst_id"]
                    break
        if not item:
            return []
        k = ("item_batches", item)
        if k not in self._cache:
            self._cache[k] = self.erp.call("erpnext.stock.doctype.batch.batch.get_batch_qty",
                                           item_code=item, for_stock_levels=1) or []
        return [{"창고": wh(x["warehouse"]), "상태": WH_STATE.get(wh(x["warehouse"]), ""), "수량": round(x["qty"], 3)}
                for x in self._cache[k] if x["batch_no"] == lot_id and abs(x["qty"]) > 1e-6]

    def bins(self):
        if "bins" not in self._cache:
            self._cache["bins"] = self.erp.get_all("Bin", fields=["item_code", "warehouse", "actual_qty"]) if self.erp else []
        return self._cache["bins"]

    # ===================== IQC 측정값 =====================
    def _iqc_rows(self):
        """IQC 측정값 표: lot, 원재료, 공급사, 입고일, 항목, 값, 하한, 상한, 여유(%)"""
        if "iqc" in self._cache:
            return self._cache["iqc"]
        rows = []
        for ins in self.s.objs("inspection"):
            if ins["props"].get("구분") != "입고":
                continue
            lots = [l["dst_id"] for l in self.s.links_from("inspection", ins["id"], "대상") if l["dst_type"] == "raw_lot"]
            if not lots:
                continue
            lot = lots[0]
            mat = (self.s.links_from("raw_lot", lot, "종류") or [{}])[0].get("dst_id")
            sup = (self.s.links_from("inspection", ins["id"], "공급사") or self.s.links_from("raw_lot", lot, "제조사") or [{}])[0].get("dst_id")
            for m in ins["props"].get("측정값") or []:
                v, lo, hi = num(m["값"]), num(m["하한"]), num(m["상한"])
                lo = None if lo is None or lo < -BIG else lo
                hi = None if hi is None or hi > BIG else hi
                rows.append({"검사": ins["id"], "lot": lot, "원재료": mat, "공급사": sup,
                             "판정일": str(ins["props"].get("판정 일시") or "")[:10], "검사 판정": ins["props"].get("판정"),
                             "항목": m["항목"], "값": v, "하한": lo, "상한": hi, "여유(%)": margin(v, lo, hi, m["항목"])})
        # 이상치: 비교군(같은 원재료·공급사·항목 5 lot 이상, 없으면 같은 분류·항목) 평균 ± 2σ 밖이면서
        # 나쁜 쪽(상한 항목은 높게, 하한 항목은 낮게, 양쪽 항목은 중심에서 멀게)으로 규격 폭의 10% 이상 벗어난 값
        cat = {m["id"]: m["props"].get("분류") for m in self.s.objs("material")}
        g1, g2 = defaultdict(list), defaultdict(list)
        for r in rows:
            if r["값"] is not None:
                g1[(r["원재료"], r["공급사"], r["항목"])].append(r)
                g2[(cat.get(r["원재료"]), r["항목"])].append(r)
        sig = self.d.get("iqc", {}).get("outlier_sigma", 2)
        for r in rows:
            if r["값"] is None:
                continue
            grp = g1[(r["원재료"], r["공급사"], r["항목"])]
            basis = "같은 원재료·공급사"
            if len(grp) < 6:
                grp, basis = g2[(cat.get(r["원재료"]), r["항목"])], f"같은 분류({cat.get(r['원재료'])})"
            others = [x["값"] for x in grp if x is not r]
            if len(others) < 5:
                continue
            mu, sd = statistics.mean(others), statistics.pstdev(others)
            lo, hi, v = r["하한"], r["상한"], r["값"]
            if lo is not None and hi is not None:
                bad, scale = abs(v - (lo + hi) / 2) - abs(mu - (lo + hi) / 2), (hi - lo) / 2
            elif hi is not None:
                bad, scale = v - mu, hi
            elif lo is not None:
                bad, scale = mu - v, 100 - lo
            else:
                continue
            z = (v - mu) / sd if sd > 1e-9 else 0.0
            r["평균(비교군)"] = round(mu, 4)
            r["비교군"] = f"{basis} {len(others)} lot"
            r["z"] = round(z, 1)
            r["_out"] = abs(z) > sig and bad > 0.1 * scale
        warn = self.d.get("iqc", {}).get("margin_warning_pct", 20)
        for r in rows:
            flags = []
            if r["여유(%)"] is not None and r["여유(%)"] < 0:
                flags.append("규격 밖")
            elif r["여유(%)"] is not None and r["여유(%)"] < warn:
                flags.append("경계")
            if r.pop("_out", False):
                flags.append("이상치")
            r["표시"] = ",".join(flags)
        self._cache["iqc"] = rows
        return rows

    def iqc_of_lot(self, lot, only_flagged=False):
        rows = [r for r in self._iqc_rows() if r["lot"] == lot]
        if only_flagged:
            rows = [r for r in rows if r["표시"]]
        return rows

    def measurement_trend(self, material, supplier=None, item=None, date_from=None, date_to=None):
        """원재료(·공급사)의 IQC 항목별 lot 추이와 경계·이상치."""
        _, mat = self._resolve(material, "material")
        sup = self._resolve(supplier, "supplier")[1] if supplier else None
        if not mat:
            return {"오류": f"원재료 '{material}' 없음"}
        rows = [r for r in self._iqc_rows() if r["원재료"] == mat and (not sup or r["공급사"] == sup)
                and (not date_from or r["판정일"] >= date_from) and (not date_to or r["판정일"] <= date_to)]
        if item:
            rows = [r for r in rows if norm(item) in norm(r["항목"])]
            return {"원재료": mat, "공급사": sup, "항목": item, "lot 수": len({r['lot'] for r in rows}),
                    "추이": [{k: r.get(k) for k in ("lot", "공급사", "판정일", "값", "상한", "하한", "여유(%)", "평균(비교군)", "z", "표시")}
                           for r in sorted(rows, key=lambda r: r["판정일"])]}
        flagged = [r for r in rows if r["표시"]]
        summ = defaultdict(lambda: {"측정 lot": 0, "평균": [], "표시 lot": []})
        for r in rows:
            s = summ[r["항목"]]
            s["측정 lot"] += 1
            if r["값"] is not None:
                s["평균"].append(r["값"])
            if r["표시"]:
                s["표시 lot"].append(f"{r['lot']}({r['값']}, {r['표시']})")
        items = {k: {"측정 lot": v["측정 lot"], "평균": round(statistics.mean(v["평균"]), 4) if v["평균"] else None,
                     "경계·이상치": v["표시 lot"]} for k, v in summ.items()}
        return {"원재료": mat, "공급사": sup, "검사 lot 수": len({r['lot'] for r in rows}),
                "경계·이상치 측정": len(flagged), "항목별": items,
                "참고": "레진 금속 26종은 5 lot 중 1 lot만 측정. 측정하지 않은 lot은 '미측정'"}

    # ===================== 추적 =====================
    def trace_back(self, fg_lot):
        """완제품 lot → 작업지시, 설비, 필터, 투입 원재료 lot(공급사·입고·IQC), 출하·클레임."""
        t, lot = self._resolve(fg_lot, "fg_lot")
        if t != "fg_lot":
            return {"오류": f"완제품 lot '{fg_lot}' 없음"}
        o = self.s.obj("fg_lot", lot)
        out = {"완제품 lot": lot, "제품": (self.s.links_from("fg_lot", lot, "종류") or [{}])[0].get("dst_id"),
               "생산일": o["props"].get("생산일"), "유효기간": o["props"].get("유효기간")}
        G = "trace_back"
        wos = self.gq("MATCH (w:work_order)-[:생산]->(f:fg_lot {id:$lot}) RETURN w.id AS wo", {"lot": lot}, G)
        if not wos:
            out["작업지시"] = "없음(2025년 생산분 기초재고 이관 lot)"
        for w in wos[:1]:
            wo = self.s.obj("work_order", w["wo"])
            out["작업지시"] = {"id": wo["id"], **{k: wo["props"].get(k) for k in
                                                ("배치량(L)", "구분", "실제 시작일", "실제 종료일", "수율(%)", "배합 탱크")}}
            out["공정 설비"] = self.gq("MATCH (w:work_order {id:$w})-[e:공정_설비]->(q:equipment) "
                                    "RETURN e.공정 AS 공정, q.id AS 설비", {"w": wo["id"]}, G)
            out["필터 lot"] = [r["id"] for r in self.gq(
                "MATCH (w:work_order {id:$w})-[:필터_사용]->(x:filter_lot) RETURN x.id AS id", {"w": wo["id"]}, G)]
            ins = self.gq("MATCH (w:work_order {id:$w})-[t:투입]->(r:raw_lot) RETURN r.id AS lot, t.수량 AS qty "
                          "ORDER BY r.id", {"w": wo["id"]}, G)
            out["투입 원재료 lot"] = [self._raw_lot_card(r["lot"], r["qty"]) for r in ins]
        out["출하"] = self.gq("MATCH (d:delivery)-[:출하_lot]->(f:fg_lot {id:$lot}) OPTIONAL MATCH (d)-[:받는_곳]->(c:customer) "
                            "RETURN d.id AS 출하, c.id AS 고객, d.출하일 AS 출하일, d.수량_병 AS `수량(병)` ORDER BY 출하일",
                            {"lot": lot}, G)
        out["부적합·클레임"] = [self._ref("ncr", l["src_id"]) for l in self.s.links_to("fg_lot", lot, "대상")]
        oqc = [l["src_id"] for l in self.s.links_to("fg_lot", lot, "대상") if l["src_type"] == "inspection"]
        if oqc:
            ins = self.s.obj("inspection", oqc[0])
            out["출하검사"] = {"검사": oqc[0], "판정": ins["props"].get("판정"),
                           "측정값": {m["항목"]: m["값"] for m in ins["props"].get("측정값") or []}}
        out["현재 재고"] = self.lot_stock(lot)
        if self.docs:
            out["관련 문서"] = self.docs.mentions("fg_lot", lot, lot)[:5]
        return out

    def _raw_lot_card(self, rl, qty=None):
        o = self.s.obj("raw_lot", rl) or {"props": {}}
        mat = (self.s.links_from("raw_lot", rl, "종류") or [{}])[0].get("dst_id")
        sup = (self.s.links_from("raw_lot", rl, "제조사") or [{}])[0].get("dst_id")
        rec = self.s.links_to("raw_lot", rl, "생성")
        flagged = self.iqc_of_lot(rl, only_flagged=True)
        measured = {r["항목"] for r in self.iqc_of_lot(rl)}
        card = {"lot": rl, "원재료": mat, "공급사": sup, "공급사 lot": o["props"].get("공급사 lot"),
                "제조일": o["props"].get("제조일"), "입고": rec[0]["src_id"] if rec else "기초재고",
                "IQC 경계·이상치": [f"{r['항목']} {r['값']} ({r['표시']}, 상한 {r['상한']}, {r.get('비교군')} 평균 {r.get('평균(비교군)')})"
                                for r in flagged],
                "금속 측정": "측정" if any(m.startswith("금속") for m in measured) else "미측정"}
        if qty is not None:
            card["투입량"] = qty
        ncr = [l["src_id"] for l in self.s.links_to("raw_lot", rl, "대상") if l["src_type"] == "ncr"]
        if ncr:
            card["부적합"] = ncr
        return card

    def _delivery_brief(self, did):
        o = self.s.obj("delivery", did)
        cu = (self.s.links_from("delivery", did, "받는 곳") or [{}])[0].get("dst_id")
        return {"고객": cu, "출하일": o["props"].get("출하일"), "수량(병)": o["props"].get("수량(병)")}

    def trace_forward(self, raw_lots=None, material=None, supplier=None, mfg_from=None, mfg_to=None):
        """원재료 lot(또는 조건) → 들어간 작업지시·완제품 lot → 지금 위치와 출하 고객."""
        lots = self._select_raw_lots(raw_lots, material, supplier, mfg_from, mfg_to)
        if isinstance(lots, dict):
            return lots
        G = "trace_forward"
        hits = self.gq("MATCH (r:raw_lot)<-[:투입]-(w:work_order)-[:생산]->(f:fg_lot) WHERE r.id IN $lots "
                       "OPTIONAL MATCH (f)-[:종류]->(p:product) "
                       "RETURN f.id AS fg, w.id AS wo, p.id AS prod, collect(DISTINCT r.id) AS raws ORDER BY fg",
                       {"lots": lots}, G) if lots else []
        ships = self.gq("MATCH (d:delivery)-[:출하_lot]->(f:fg_lot) WHERE f.id IN $fgs "
                        "OPTIONAL MATCH (d)-[:받는_곳]->(c:customer) "
                        "RETURN f.id AS fg, d.id AS 출하, c.id AS 고객, d.출하일 AS 출하일, d.수량_병 AS `수량(병)` ORDER BY 출하일",
                        {"fgs": [h["fg"] for h in hits]}, G) if hits else []
        rows = []
        for h in hits:
            rows.append({"완제품 lot": h["fg"], "제품": h["prod"], "작업지시": h["wo"], "투입 원재료 lot": h["raws"],
                         "현재 재고": self.lot_stock(h["fg"], h["prod"]),
                         "출하": [{k: v for k, v in x.items() if k != "fg"} for x in ships if x["fg"] == h["fg"]]})
        customers = Counter(s["고객"] for r in rows for s in r["출하"])
        return {"대상 원재료 lot": lots, "영향 완제품 lot 수": len(rows),
                "재고 남은 lot": [r["완제품 lot"] for r in rows if r["현재 재고"]],
                "출하된 고객별 출하 건수": dict(customers), "완제품 lot": rows}

    def _select_raw_lots(self, raw_lots, material, supplier, mfg_from, mfg_to):
        if raw_lots:
            ids = raw_lots if isinstance(raw_lots, list) else [raw_lots]
            out = []
            for x in ids:
                t, i = self._resolve(x, "raw_lot")
                if t == "raw_lot":
                    out.append(i)
            return out or {"오류": f"원재료 lot {raw_lots} 없음"}
        mat = self._resolve(material, "material")[1] if material else None
        sup = self._resolve(supplier, "supplier")[1] if supplier else None
        if material and not mat:
            return {"오류": f"원재료 '{material}' 없음"}
        if supplier and not sup:
            return {"오류": f"공급사 '{supplier}' 없음"}
        out = []
        for o in self.s.objs("raw_lot"):
            if mat and (self.s.links_from("raw_lot", o["id"], "종류") or [{}])[0].get("dst_id") != mat:
                continue
            if sup and (self.s.links_from("raw_lot", o["id"], "제조사") or [{}])[0].get("dst_id") != sup:
                continue
            md = str(o["props"].get("제조일") or "")
            if (mfg_from and md < mfg_from) or (mfg_to and md > mfg_to):
                continue
            out.append(o["id"])
        return sorted(out)

    def suspect_lots(self, material=None, supplier=None, mfg_from=None, mfg_to=None, raw_lots=None):
        """조건(원재료·공급사·제조일 범위)에 맞는 의심 원재료 lot과 그 영향 (R08)."""
        lots = self._select_raw_lots(raw_lots, material, supplier, mfg_from, mfg_to)
        if isinstance(lots, dict):
            return lots
        cards = []
        for rl in lots:
            c = self._raw_lot_card(rl)
            c["현재 재고"] = self.lot_stock(rl, c["원재료"])
            cards.append(c)
        fwd = self.trace_forward(raw_lots=lots) if lots else {"완제품 lot": []}
        return {"규칙": "R08: 의심 원재료 lot이 들어간 완제품 lot은 출하 보류 후보",
                "의심 원재료 lot": cards,
                "원재료 lot 재고 남은 것": [c["lot"] for c in cards if c["현재 재고"]],
                "영향 완제품 lot": [{"lot": r["완제품 lot"], "제품": r["제품"], "현재 재고": r["현재 재고"],
                                  "출하": [f"{s['고객']} {s['출하일']} {s['수량(병)']}병" for s in r["출하"]]}
                                 for r in fwd["완제품 lot"]],
                "출하 보류 후보(재고 있음)": fwd.get("재고 남은 lot", []),
                "이미 출하된 고객": fwd.get("출하된 고객별 출하 건수", {})}

    def common_factors(self, fg_lots, compare=None):
        """문제 lot들의 공통 요인 vs 비교군(기본: 같은 제품의 나머지 lot).

        요인: 원재료 lot, 원재료@공급사, 설비, 필터 lot, IQC 경계·이상치 항목.
        """
        target = []
        for x in fg_lots if isinstance(fg_lots, list) else [fg_lots]:
            t, i = self._resolve(x, "fg_lot")
            if t == "fg_lot":
                target.append(i)
        if not target:
            return {"오류": "완제품 lot을 찾지 못했습니다"}
        prods = {(self.s.links_from("fg_lot", l, "종류") or [{}])[0].get("dst_id") for l in target}
        if compare:
            comp = [self._resolve(x, "fg_lot")[1] for x in compare]
        else:
            comp = [o["id"] for o in self.s.objs("fg_lot")
                    if (self.s.links_from("fg_lot", o["id"], "종류") or [{}])[0].get("dst_id") in prods and o["id"] not in target]
        comp = [c for c in comp if c and self.s.links_to("fg_lot", c, "생산")]

        def factors(lot):
            f = set()
            for w in self.s.links_to("fg_lot", lot, "생산"):
                wo = w["src_id"]
                for l in self.s.links_from("work_order", wo, "공정 설비"):
                    f.add(("설비", f"{l['props'].get('공정')}:{l['dst_id']}"))
                for l in self.s.links_from("work_order", wo, "필터 사용"):
                    f.add(("필터 lot", l["dst_id"]))
                for l in self.s.links_from("work_order", wo, "투입"):
                    rl = l["dst_id"]
                    mat = (self.s.links_from("raw_lot", rl, "종류") or [{}])[0].get("dst_id")
                    sup = (self.s.links_from("raw_lot", rl, "제조사") or [{}])[0].get("dst_id")
                    f.add(("원재료 lot", rl))
                    f.add(("원재료@공급사", f"{mat}@{sup}"))
                    for r in self.iqc_of_lot(rl, only_flagged=True):
                        f.add(("IQC 경계·이상치", f"{mat}@{sup} {r['항목']} {r['표시']}"))
            return f

        tf = {l: factors(l) for l in target}
        cf = {l: factors(l) for l in comp}
        cnt_t = Counter(x for s in tf.values() for x in s)
        cnt_c = Counter(x for s in cf.values() for x in s)
        rows = []
        for k, n in cnt_t.items():
            share_t = n / len(target)
            share_c = cnt_c.get(k, 0) / len(comp) if comp else 0
            if share_t >= 0.5:
                rows.append({"요인 종류": k[0], "요인": k[1], "문제 lot 중": f"{n}/{len(target)}",
                             "비교군 중": f"{cnt_c.get(k, 0)}/{len(comp)}", "차이": round(share_t - share_c, 2)})
        rows.sort(key=lambda r: (-r["차이"], r["요인 종류"]))
        return {"문제 lot": target, "비교군": f"같은 제품({', '.join(sorted(p for p in prods if p))})의 나머지 lot {len(comp)}개"
                if not compare else f"지정 {len(comp)}개",
                "공통 요인(차이 큰 순)": rows[:25],
                "해석 주의": "차이가 크다고 원인이라는 뜻은 아니다. 원재료 lot 단위 요인은 측정값·문서로 확인 필요"}

    # ===================== 판정 =====================
    def shippable(self, fg_lot, customer):
        """완제품 lot을 이 고객에게 보낼 수 있나 (R01 유효기간, 출하검사, 위치, 승인, 의심·부적합)."""
        _, lot = self._resolve(fg_lot, "fg_lot")
        _, cu = self._resolve(customer, "customer")
        if not lot or not cu:
            return {"오류": f"lot '{fg_lot}' 또는 고객 '{customer}'를 찾지 못했습니다"}
        o = self.s.obj("fg_lot", lot)
        c = self.s.obj("customer", cu)
        prod = (self.s.links_from("fg_lot", lot, "종류") or [{}])[0].get("dst_id")
        reasons, checks = [], []
        need = self.rule_param("R01_ship_shelf_life", c)
        if need is None:
            need = int(c["props"].get("출하 가능 잔여 유효기간(일)") or 0)
        exp = d(o["props"].get("유효기간"))
        left = (exp - today()).days if exp else None
        checks.append(f"잔여 유효기간 {left}일 / {c['title']} 기준 {need}일 (R01, 정의 파일 v{self.d['meta']['version']})")
        if left is None or left < need:
            reasons.append(f"잔여 유효기간 부족: {left}일 < {need}일 (R01)")
        oqc = [l["src_id"] for l in self.s.links_to("fg_lot", lot, "대상") if l["src_type"] == "inspection"]
        if not oqc:
            reasons.append("출하검사 기록 없음")
        else:
            ins = self.s.obj("inspection", oqc[0])
            checks.append(f"출하검사 {oqc[0]}: {ins['props'].get('판정')}")
            if ins["props"].get("판정") != "Accepted":
                reasons.append(f"출하검사 불합격 ({oqc[0]}) (R05)")
        stock = self.lot_stock(lot, prod)
        checks.append("현재 재고: " + (", ".join(f"{s['창고']}({s['상태']}) {s['수량']}" for s in stock) or "없음"))
        if not any(s["창고"] == "WH-70" for s in stock):
            reasons.append("출하 창고(WH-70)에 재고 없음")
        ap = [a for a in self.s.objs("approval")
              if self._one("approval", a["id"], "고객") == cu and self._one("approval", a["id"], "제품") == prod]
        if not ap:
            reasons.append(f"{c['title']}의 {prod} 승인 기록 없음")
        else:
            pairs = {p.strip() for p in str(ap[0]["props"].get("승인된 원재료@공급사") or "").split(",")}
            tb = self.trace_back(lot)
            for rl in tb.get("투입 원재료 lot", []):
                if rl["원재료"] and rl["원재료"].startswith("PK"):
                    continue
                pair = f"{rl['원재료']}@{rl['공급사']}"
                if rl["공급사"] and pair not in pairs:
                    reasons.append(f"미승인 원재료@공급사 투입: {pair} (lot {rl['lot']}) (R02)")
                if rl.get("부적합"):
                    reasons.append(f"부적합 이력 원재료 lot 투입: {rl['lot']} {rl['부적합']}")
            checks.append(f"고객 승인 {ap[0]['id']} 대비 투입 원재료 확인")
        ncr = [l["src_id"] for l in self.s.links_to("fg_lot", lot, "대상") if l["src_type"] == "ncr"]
        if ncr:
            reasons.append(f"이 lot에 부적합·클레임: {ncr}")
        return {"lot": lot, "고객": cu, "판정": "출하 가능" if not reasons else "출하 불가",
                "불가 사유": reasons, "확인 항목": checks, "기준일": str(today())}

    def rule_param(self, rule_id, customer_obj):
        """규칙 숫자(정의 파일)를 고객 이름으로 찾는다. 화면에서 고친 숫자가 바로 판정에 쓰인다."""
        r = next((x for x in self.d.get("rules", []) if x["id"] == rule_id), None)
        if not r or not r.get("params"):
            return None
        short = customer_obj["title"].split("(")[0].strip()
        for k in (customer_obj["id"], short, customer_obj["title"]):
            if k in r["params"]:
                return int(r["params"][k])
        return None

    def _one(self, t, i, rel):
        ls = self.s.links_from(t, i, rel)
        return ls[0]["dst_id"] if ls else None

    def requal_needed(self, material, supplier):
        """원재료를 새 공급사로 바꾸면 재승인이 필요한 고객·제품과 기간 (R02)."""
        _, mat = self._resolve(material, "material")
        _, sup = self._resolve(supplier, "supplier")
        if not mat or not sup:
            return {"오류": f"원재료 '{material}' 또는 공급사 '{supplier}'를 찾지 못했습니다"}
        users = {l["src_id"] for l in self.s.links_to("material", mat, "레시피")}
        out, ok = [], []
        for a in self.s.objs("approval"):
            prod, cu = self._one("approval", a["id"], "제품"), self._one("approval", a["id"], "고객")
            if prod not in users:
                continue
            pairs = {p.strip() for p in str(a["props"].get("승인된 원재료@공급사") or "").split(",")}
            c = self.s.obj("customer", cu)
            if f"{mat}@{sup}" in pairs:
                ok.append(f"{c['title']} {prod}")
            else:
                out.append({"고객": c["title"], "제품": prod, "고객 품번": a["props"].get("고객 품번"),
                            "재승인 기간(일)": self.rule_param("R02_requalification", c) or c["props"].get("원재료 변경 시 재승인(일)"),
                            "현재 승인 공급사": [p.split("@")[1] for p in pairs if p.startswith(mat + "@")]})
        days = max([r["재승인 기간(일)"] or 0 for r in out], default=0)
        return {"원재료": mat, "새 공급사": sup, "이 원재료를 쓰는 제품": sorted(users),
                "재승인 필요": out, "이미 승인됨": ok, "가장 긴 재승인 기간(일)": days, "규칙": "R02"}

    # ===================== 계획 =====================
    def _bom_per_bottle(self):
        if "bom" not in self._cache:
            per = defaultdict(dict)
            for l in self.s.db.execute("SELECT src_id, dst_id, props FROM links WHERE rel='레시피'"):
                import json as _j
                per[l[0]][l[1]] = (_j.loads(l[2]).get("1000L당 투입량") or 0) / 264.0
            self._cache["bom"] = per
        return self._cache["bom"]

    def material_stock(self, mat):
        """원재료 가용 재고 = 합격 창고 + IQC 전(곧 합격) 수량. 보류 제외."""
        acc = qc = hold = 0.0
        for b in self.bins():
            if b["item_code"] != mat:
                continue
            w = wh(b["warehouse"])
            st = WH_STATE.get(w, "")
            if st == "합격":
                acc += b["actual_qty"]
            elif st == "IQC 전":
                qc += b["actual_qty"]
            elif st == "보류":
                hold += b["actual_qty"]
        return {"합격": round(acc, 3), "IQC 전": round(qc, 3), "보류": round(hold, 3)}

    def open_pos(self, mat):
        rows = []
        for p in self.s.objs("purchase"):
            if self._one("purchase", p["id"], "주문") != mat or p["status"] != "확정":
                continue
            got = sum((self.s.obj("receipt", l["src_id"]) or {"props": {}})["props"].get("수량(재고 단위)") or 0
                      for l in self.s.links_to("purchase", p["id"], "이행")
                      if (self.s.obj("receipt", l["src_id"]) or {}).get("status") == "확정")
            left = (p["props"].get("수량") or 0) - got
            if left > 1e-6 and p["props"].get("ERP 상태") not in ("Closed", "Completed"):
                rows.append({"발주": p["id"], "공급사": self._one("purchase", p["id"], "발주처"), "미입고": round(left, 3),
                             "회신 납기": p["props"].get("공급사 회신 납기"), "납기 요청일": p["props"].get("납기 요청일")})
        return rows

    def shortage_forecast(self, material, months=3):
        """원재료 재고 + 미입고 발주 - 확정 생산계획 사용량 → 월별 예상 재고, 부족 시점 (R04)."""
        _, mat = self._resolve(material, "material")
        if not mat:
            return {"오류": f"원재료 '{material}' 없음"}
        m = self.s.obj("material", mat)
        stock = self.material_stock(mat)
        pos = self.open_pos(mat)
        bom = self._bom_per_bottle()
        latest = {}
        for p in self.s.objs("plan"):
            if p["props"].get("종류") != "NR Production Plan":
                continue
            prod = self._one("plan", p["id"], "제품")
            k = (prod, p["props"].get("계획월"))
            if k not in latest or str(p["props"].get("S&OP 버전")) > str(latest[k]["props"].get("S&OP 버전")):
                latest[k] = p
        t0 = today()
        months_list = []
        y, mo = t0.year, t0.month
        for _ in range(months):
            months_list.append(f"{y}-{mo:02d}")
            mo += 1
            if mo > 12:
                y, mo = y + 1, 1
        use = {mm: 0.0 for mm in months_list}
        for (prod, mm), p in latest.items():
            if mm in use and mat in bom.get(prod, {}):
                use[mm] += bom[prod][mat] * (p["props"].get("수량(병)") or 0)
        def eta(p):
            return str(p["회신 납기"] or p["납기 요청일"] or "")[:7] or months_list[0]

        bal = stock["합격"] + stock["IQC 전"]
        rows, short, counted = [], None, set()
        for mm in months_list:
            arr = 0.0
            for p in pos:
                if p["발주"] not in counted and eta(p) <= mm:  # 지난 납기 미입고는 이번 달 입고로 본다
                    arr += p["미입고"]
                    counted.add(p["발주"])
            bal += arr - use[mm]
            rows.append({"월": mm, "입고 예정": round(arr, 2), "계획 사용량": round(use[mm], 2), "월말 예상 재고": round(bal, 2)})
            if bal < 0 and not short:
                short = mm
        avg = statistics.mean([r["계획 사용량"] for r in rows]) if rows else 0
        policy = m["props"].get("안전재고 정책(개월)") or 0
        cover = round((stock["합격"] + stock["IQC 전"]) / avg, 1) if avg else None
        return {"원재료": mat, "이름": m["title"], "단위": m["props"].get("단위"), "현재 재고": stock,
                "미입고 발주": pos, "월별": rows, "부족 예상 월": short or "없음(기간 내)",
                "현재 재고로 버티는 개월": cover, "안전재고 정책(개월)": policy,
                "안전재고 부족(R04)": bool(cover is not None and cover < policy),
                "가정": "확정 생산계획(최신 S&OP) × 레시피(1,000 L=264병). 입고는 회신 납기(없으면 납기 요청일) 월에 들어온다고 봄"}

    def impacted_orders(self, material=None, delay_days=None, equipment=None, date_from=None, date_to=None):
        """원재료 지연 또는 설비 중단으로 늦어질 작업지시·수주."""
        out = []
        t0 = today()
        if material:
            _, mat = self._resolve(material, "material")
            if not mat:
                return {"오류": f"원재료 '{material}' 없음"}
            fc = self.shortage_forecast(mat, months=3)
            users = {l["src_id"] for l in self.s.links_to("material", mat, "레시피")}
            for w in self.s.objs("work_order"):
                if self._one("work_order", w["id"], "제품") in users and w["props"].get("상태") in ("Not Started", "Draft", "In Process") \
                        and not self.s.links_from("work_order", w["id"], "투입"):
                    out.append({"작업지시": w["id"], "제품": self._one("work_order", w["id"], "제품"),
                                "계획 시작일": w["props"].get("계획 시작일"),
                                "연결 수주": [l["dst_id"] for l in self.s.links_from("work_order", w["id"], "연결 수주")]})
            sos = []
            for so in self.s.objs("sales_order"):
                prod = self._one("sales_order", so["id"], "제품")
                left = self._so_open(so)
                if prod in users and left > 0:
                    sos.append({"수주": so["id"], "고객": self._one("sales_order", so["id"], "주문자"),
                                "미출하(병)": left, "납기 요청일": so["props"].get("납기 요청일")})
            sos.sort(key=lambda r: str(r["납기 요청일"]))
            return {"원재료": mat, "부족 예상": fc["부족 예상 월"], "현재 재고로 버티는 개월": fc["현재 재고로 버티는 개월"],
                    "이 원재료가 필요한 미착수 작업지시": out, "영향 가능 미출하 수주": sos[:30],
                    "가정": f"지연 {delay_days}일" if delay_days else "지연 일수 미지정"}
        if equipment:
            _, eq = self._resolve(equipment, "equipment")
            if not eq:
                return {"오류": f"설비 '{equipment}' 없음"}
            for w in self.s.objs("work_order"):
                ops = [l for l in self.s.links_from("work_order", w["id"], "공정 설비") if l["dst_id"] == eq]
                ps = str(w["props"].get("계획 시작일") or "")[:10]
                if (ops or w["props"].get("배합 탱크") == eq) and w["props"].get("상태") not in ("Completed", "Stopped", "Closed") \
                        and (not date_to or ps <= date_to) and (not date_from or str(w["props"].get("계획 종료일") or ps) >= date_from):
                    out.append({"작업지시": w["id"], "제품": self._one("work_order", w["id"], "제품"), "계획 시작일": ps,
                                "상태": w["props"].get("상태"),
                                "연결 수주": [l["dst_id"] for l in self.s.links_from("work_order", w["id"], "연결 수주")]})
            return {"설비": eq, "기간": f"{date_from}~{date_to}", "영향 작업지시": out}
        return {"오류": "material 또는 equipment 중 하나를 주세요"}

    def _so_open(self, so):
        shipped = sum((self.s.obj("delivery", l["src_id"]) or {"props": {}})["props"].get("수량(병)") or 0
                      for l in self.s.links_to("sales_order", so["id"], "이행"))
        return round((so["props"].get("수량(병)") or 0) - shipped, 3) if so["status"] == "확정" and \
            so["props"].get("ERP 상태") not in ("Closed", "Completed", "Cancelled") else 0

    # ===================== 문서 =====================
    def search_docs(self, query, limit=8):
        return self.docs.search(query, limit) if self.docs else []

    def read_doc(self, path):
        return self.docs.read(path) if self.docs else {"오류": "문서 없음"}


def margin(v, lo, hi, item=""):
    """규격 대비 여유(%). 0 미만이면 규격 밖."""
    if v is None:
        return None
    if lo is not None and hi is not None:
        half = (hi - lo) / 2
        mid = (hi + lo) / 2
        return round((half - abs(v - mid)) / half * 100, 1) if half > 0 else None
    if hi is not None:
        return round((hi - v) / hi * 100, 1) if hi > 0 else None
    if lo is not None:  # 순도: 하한~100 사이 여유
        rng = 100 - lo
        return round((v - lo) / rng * 100, 1) if rng > 0 else None
    return None


# ===================== 계산 속성 =====================
def _sup_pos(o, sid):
    return [p for p in o.s.objs("purchase") if o._one("purchase", p["id"], "발주처") == sid]


def _po_delay(o, p, base):
    recs = [o.s.obj("receipt", l["src_id"]) for l in o.s.links_to("purchase", p["id"], "이행")]
    recs = [r for r in recs if r and r["status"] == "확정"]
    if not recs or not p["props"].get(base):
        return None
    last = max(d(r["props"].get("입고일")) for r in recs)
    return (last - d(p["props"][base])).days


def c_supplier_channel(o, t, i, obj):
    ag = o._one("supplier", i, "경유")
    return f"에이전시 경유({ag})" if ag else "직거래"


def c_on_time(o, t, i, obj):
    ds = [x for x in (_po_delay(o, p, "납기 요청일") for p in _sup_pos(o, i)) if x is not None]
    return f"{sum(1 for x in ds if x <= 0) / len(ds) * 100:.0f}% ({len(ds)}건)" if ds else "입고 기록 없음"


def c_avg_delay(o, t, i, obj):
    ds = [x for x in (_po_delay(o, p, "공급사 회신 납기") for p in _sup_pos(o, i)) if x is not None]
    return round(statistics.mean(ds), 1) if ds else None


def c_sup_ncr(o, t, i, obj):
    n = 0
    for rl in o.s.objs("raw_lot"):
        if o._one("raw_lot", rl["id"], "제조사") == i:
            n += sum(1 for l in o.s.links_to("raw_lot", rl["id"], "대상") if l["src_type"] == "ncr")
    return n


def c_sup_iqc_warning(o, t, i, obj):
    rows = sorted([r for r in o._iqc_rows() if r["공급사"] == i], key=lambda r: r["판정일"])
    by_lot = {}
    for r in rows:
        by_lot.setdefault(r["lot"], []).append(r)
    lots = list(by_lot)[-3:]
    flagged = [l for l in lots if any(r["표시"] for r in by_lot[l])]
    return {"최근 3 lot 중 경계·이상치": f"{len(flagged)}/{len(lots)}",
            "경고(R12)": len(lots) == 3 and len(flagged) == 3, "lot": flagged}


def c_mat_avail(o, t, i, obj):
    return o.material_stock(i)


def c_ss_months(o, t, i, obj):
    f = o.shortage_forecast(i, months=3)
    return f["현재 재고로 버티는 개월"]


def c_open_po(o, t, i, obj):
    return round(sum(p["미입고"] for p in o.open_pos(i)), 3)


def c_req_to_order(o, t, i, obj):
    a, b = d(obj["props"].get("요청일")), d(obj["props"].get("발주일"))
    return (b - a).days if a and b else None


def c_approval_days(o, t, i, obj):
    a, b = d(obj["props"].get("품의 상신일")), d(obj["props"].get("품의 승인일"))
    return (b - a).days if a and b else None


def c_received(o, t, i, obj):
    return round(sum((o.s.obj("receipt", l["src_id"]) or {"props": {}})["props"].get("수량(재고 단위)") or 0
                     for l in o.s.links_to("purchase", i, "이행")
                     if (o.s.obj("receipt", l["src_id"]) or {}).get("status") == "확정"), 3)


def c_open(o, t, i, obj):
    return round((obj["props"].get("수량") or 0) - c_received(o, t, i, obj), 3)


def c_delay(o, t, i, obj):
    x = _po_delay(o, obj, "납기 요청일")
    if x is None and d(obj["props"].get("납기 요청일")) and d(obj["props"]["납기 요청일"]) < today():
        return f"미입고, {(today() - d(obj['props']['납기 요청일'])).days}일 경과"
    return x


def c_delay_conf(o, t, i, obj):
    return _po_delay(o, obj, "공급사 회신 납기")


def c_entry_delay(o, t, i, obj):
    a, b = d(obj["props"].get("입고일")), d(obj["props"].get("ERP 입력일"))
    return (b - a).days if a and b else None


def c_lot_location(o, t, i, obj):
    return o.lot_stock(i) or "재고 없음"


def c_lot_status(o, t, i, obj):
    st = o.lot_stock(i)
    if st:
        return ", ".join(sorted({s["상태"] for s in st}))
    used = o.s.links_to("raw_lot", i, "투입") if t == "raw_lot" else []
    return "소진(공정 투입 완료)" if used else "재고 없음"


def c_days_to_expiry(o, t, i, obj):
    e = d(obj["props"].get("유효기간"))
    return (e - today()).days if e else None


def c_iqc_flags(o, t, i, obj):
    rows = o.iqc_of_lot(i)
    if not rows:
        return "IQC 기록 없음"
    fl = [f"{r['항목']} {r['값']} ({r['표시']})" for r in rows if r["표시"]]
    return fl or "없음"


def c_wo_ops(o, t, i, obj):
    return [{"공정": l["props"].get("공정"), "설비": l["dst_id"]} for l in o.s.links_from("work_order", i, "공정 설비")]


def c_filter_use(which):
    def f(o, t, i, obj):
        wos = [l["src_id"] for l in o.s.links_to("filter_lot", i, "필터 사용")]
        dates = sorted(str(o.s.obj("work_order", w)["props"].get("실제 시작일") or "") for w in wos)
        dates = [x for x in dates if x]
        if which == "first":
            return dates[0] if dates else None
        if which == "last":
            return dates[-1] if dates else None
        if which == "count":
            return len(wos)
        return [l["dst_id"] for l in o.s.links_from("filter_lot", i, "장착")]
    return f


def c_fg_shippable(o, t, i, obj):
    return {c["title"]: o.shippable(i, c["id"])["판정"] for c in o.s.objs("customer")}


def c_ins_lead(o, t, i, obj):
    a, b = d(obj["props"].get("의뢰 일시")), d(obj["props"].get("판정 일시"))
    return (b - a).days if a and b else None


def c_ins_margin(o, t, i, obj):
    out = {}
    for m in obj["props"].get("측정값") or []:
        lo, hi = num(m["하한"]), num(m["상한"])
        out[m["항목"]] = margin(num(m["값"]), None if lo is None or lo < -BIG else lo, None if hi is None or hi > BIG else hi)
    return out


def c_so_delivered(o, t, i, obj):
    return sum((o.s.obj("delivery", l["src_id"]) or {"props": {}})["props"].get("수량(병)") or 0
               for l in o.s.links_to("sales_order", i, "이행"))


def c_so_open(o, t, i, obj):
    return o._so_open(obj)


def c_so_delay(o, t, i, obj):
    due = d(obj["props"].get("납기 요청일"))
    ds = [d((o.s.obj("delivery", l["src_id"]) or {"props": {}})["props"].get("출하일")) for l in o.s.links_to("sales_order", i, "이행")]
    ds = [x for x in ds if x]
    if not due:
        return None
    if c_so_open(o, t, i, obj) > 0:
        return f"미출하 {c_so_open(o, t, i, obj)}병, 납기까지 {(due - today()).days}일"
    return (max(ds) - due).days if ds else None


COMPUTED = {
    "supplier_channel": c_supplier_channel, "supplier_on_time_rate": c_on_time, "supplier_avg_delay": c_avg_delay,
    "supplier_ncr_count": c_sup_ncr, "supplier_iqc_warning": c_sup_iqc_warning,
    "material_available_qty": c_mat_avail, "safety_stock_months": c_ss_months, "material_open_po_qty": c_open_po,
    "purchase_request_to_order_days": c_req_to_order, "approval_lead_days": c_approval_days,
    "purchase_received_qty": c_received, "purchase_open_qty": c_open, "purchase_delay_days": c_delay,
    "purchase_delay_vs_confirmed": c_delay_conf, "entry_delay_days": c_entry_delay,
    "lot_location": c_lot_location, "lot_status": c_lot_status, "days_to_expiry": c_days_to_expiry,
    "iqc_flags": c_iqc_flags, "wo_operations": c_wo_ops,
    "filter_first_use": c_filter_use("first"), "filter_last_use": c_filter_use("last"),
    "filter_lines": c_filter_use("lines"), "filter_batch_count": c_filter_use("count"),
    "fg_shippable_customers": c_fg_shippable, "inspection_lead_days": c_ins_lead, "measurement_margin": c_ins_margin,
    "so_delivered_qty": c_so_delivered, "so_open_qty": c_so_open, "so_delay_days": c_so_delay,
}
