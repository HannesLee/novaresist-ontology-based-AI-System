"""ERP 밖 문서(메일·회의록·결정 기록·SOP·규칙집).

- 기준일 이후 날짜의 문서는 숨긴다(미래 정보가 섞이지 않게).
- mentions(): 객체 id·별칭이 나오는 문서를 찾는다 → 객체에 문서를 붙이는 연결.
"""
import csv
import hashlib
import io
import pathlib
import re

from app.ontology.store import norm

DATE = re.compile(r"(20\d\d-\d\d-\d\d)")


class Docs:
    def __init__(self, root, store, today_fn):
        self.root = pathlib.Path(root)
        self.store = store
        self.today = today_fn
        self._docs = None

    def all(self):
        if self._docs is None:
            docs = []
            for p in sorted(self.root.rglob("*.md")):
                txt = p.read_text(encoding="utf-8")
                m = DATE.search(p.name) or re.search(r"보낸 날짜:\s*(20\d\d-\d\d-\d\d)", txt) or \
                    re.search(r"(?:일시|날짜|개정):\s*(20\d\d-\d\d-\d\d)", txt)
                title = txt.splitlines()[0].lstrip("# ").strip() if txt else p.stem
                kind = p.parent.name if p.parent != self.root else "기타"
                docs.append({"path": str(p.relative_to(self.root)), "종류": kind, "날짜": m.group(1) if m else "",
                             "제목": title, "text": txt})
            for p in self.root.glob("*.csv"):
                for i, row in enumerate(csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig")))):
                    txt = " / ".join(f"{k}: {v}" for k, v in row.items())
                    docs.append({"path": f"{p.name}#{i + 1}", "종류": p.stem, "날짜": row.get("날짜", ""),
                                 "제목": (row.get("결정") or txt)[:60], "text": txt})
            self._docs = docs
        t = str(self.today())
        return [d for d in self._docs if not d["날짜"] or d["날짜"] <= t]

    def brief(self, d):
        return {"문서": d["path"], "종류": d["종류"], "날짜": d["날짜"], "제목": d["제목"]}

    def mentions(self, type_, id_, title=""):
        names = {id_}
        for (a,) in self.store.db.execute("SELECT alias FROM aliases WHERE type=? AND id=?", (type_, id_)):
            if len(norm(a)) >= 3 or re.match(r"^[A-D]사$", a):
                names.add(a)
        hits = []
        for d in self.all():
            if any(n and n in d["text"] for n in names):
                hits.append(self.brief(d))
        return sorted(hits, key=lambda x: x["날짜"], reverse=True)

    def search(self, query, limit=8):
        words = [w for w in re.split(r"[\s,]+", query) if len(w) >= 2]
        scored = []
        for d in self.all():
            s = sum(d["text"].count(w) for w in words)
            if s:
                scored.append((s, d))
        scored.sort(key=lambda x: (-x[0], x[1]["날짜"]))
        return [dict(self.brief(d), 미리보기=d["text"][:300]) for _, d in scored[:limit]]

    def read(self, path):
        for d in self.all():
            if d["path"] == path:
                return dict(self.brief(d), 본문=d["text"])
        return {"오류": f"문서 '{path}' 없음(또는 기준일 이후 문서)"}


    # ---------------- 문서 → 결정·사건 객체 + 언급 연결 ----------------
    def events(self, objects, aliases, skip_types=("plan", "event")):
        """문서마다 event 객체 하나. 문서에 나오는 객체 id·이름으로 '언급' 연결을 만든다."""
        index = {}
        for t, i, a in aliases:
            if t in skip_types:
                continue
            a = str(a).strip()
            if len(a) < 3 and not re.fullmatch(r"[A-D]사", a):
                continue
            index.setdefault(a, set()).add((t, i))
        # 여러 객체에 걸리는 이름(예: 출하 문서번호 → 출하 줄 여러 개)은 줄 단위 객체를 빼고 남긴다
        index = {a: v for a, v in index.items() if len(v) <= 6}
        names = sorted(index, key=len, reverse=True)
        objs, links, als = [], [], []
        for d in self.all():
            eid = d["path"]
            kind = {"메일": "메일", "회의록": "회의록", "결정_기록": "결정", "SOP": "SOP", "규칙": "규칙"}.get(d["종류"], d["종류"])
            props = {"날짜": d["날짜"], "종류": kind, "출처": d["path"], "내용": d["text"][:1200]}
            if d["종류"] == "결정_기록":
                for part in d["text"].split(" / "):
                    if ": " in part:
                        k, v = part.split(": ", 1)
                        if k in ("결정", "이유", "결정자", "관련 자료"):
                            props[k] = v
            objs.append({"type": "event", "id": eid, "title": d["제목"], "props": props, "src_doctype": "문서",
                         "src_name": d["path"], "status": "", "hash": hashlib.md5((d["제목"] + d["날짜"] + d["text"]).encode()).hexdigest()})
            als.append(("event", eid, d["제목"]))
            text = d["text"]
            hit = set()
            for a in names:
                if a in text:
                    hit |= index[a]
            for t, i in sorted(hit):
                links.append({"src_type": "event", "src_id": eid, "rel": "언급", "dst_type": t, "dst_id": i, "props": {}})
        return objs, links, als
