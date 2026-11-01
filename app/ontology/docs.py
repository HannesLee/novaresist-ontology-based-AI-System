"""ERP 밖 문서(메일·회의록·결정 기록·SOP·규칙집).

- 기준일 이후 날짜의 문서는 숨긴다(미래 정보가 섞이지 않게).
- mentions(): 객체 id·별칭이 나오는 문서를 찾는다 → 객체에 문서를 붙이는 연결.
"""
import csv
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
