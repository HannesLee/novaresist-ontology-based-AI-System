"""내보내기 (F16): 엑셀·파워포인트·워드. 표는 셀 데이터, 차트는 각 프로그램에서 고칠 수 있는 차트로.

요청 본문
  {"title": "...", "blocks": [{"type": "text", "md": "..."},
                              {"type": "table", "title": "...", "columns": [...], "rows": [{...}], "chart": {...}}],
   "sources": ["근거 id", ...], "note": "..."}
  또는 {"card": "<작업대 카드 id>"} / {"answer": {...챗봇 결과...}, "question": "..."}
"""
import datetime as dt
import io
import re

from app.functions.core import today

MIME = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "csv": "text/csv; charset=utf-8"}


# ---------------- 입력 정리 ----------------
def normalize(rt, body):
    if body.get("card"):
        from app.board import board as B
        c = B.card_data(rt, body["card"], limit=100000)
        blocks = [{"type": "table", "title": c["title"], "columns": c["columns"], "rows": c["rows"], "chart": c.get("chart")}]
        if c.get("note"):
            blocks.insert(0, {"type": "text", "md": c["note"]})
        src = [f"작업대 카드 {c['id']}"] + ([f"요청: {c['request']}"] if c.get("request") else [])
        return {"title": c["title"], "blocks": blocks, "sources": src}
    if body.get("answer"):
        a = body["answer"]
        blocks = [{"type": "text", "md": f"**질문** {body.get('question', '')}"}] if body.get("question") else []
        blocks += md_blocks(a.get("answer", ""))
        return {"title": body.get("title") or (body.get("question") or "온트윈 답변")[:40],
                "blocks": blocks, "sources": a.get("evidence", [])}
    return body


def md_blocks(md):
    """마크다운의 표는 table 블록으로, 나머지는 text 블록으로."""
    out, buf, tbl = [], [], []
    for line in md.splitlines() + [""]:
        if line.strip().startswith("|"):
            if buf:
                out.append({"type": "text", "md": "\n".join(buf)})
                buf = []
            tbl.append(line)
            continue
        if tbl:
            out.append(md_table(tbl))
            tbl = []
        buf.append(line)
    if buf and "".join(buf).strip():
        out.append({"type": "text", "md": "\n".join(buf)})
    return out


def md_table(lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    cols = rows[0]
    return {"type": "table", "title": "", "columns": cols,
            "rows": [dict(zip(cols, [strip_md(x) for x in r])) for r in rows[1:]]}


def strip_md(s):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(s)).replace("`", "")


def runs(text):
    """'**굵게** 보통' → [(글, 굵게?)]"""
    parts = re.split(r"(\*\*.+?\*\*)", text)
    return [(p[2:-2], True) if p.startswith("**") and p.endswith("**") else (p.replace("`", ""), False) for p in parts if p]


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def chart_data(t):
    ch = t.get("chart") or {}
    x, ys = ch.get("x"), ch.get("y") or []
    if isinstance(ys, str):
        ys = [ys]
    if not x or not ys or x not in t["columns"]:
        return None
    ys = [y for y in ys if y in t["columns"]]
    rows = t["rows"][:40]
    cats = [str(r.get(x)) for r in rows]
    series = []
    for y in ys:
        vals = []
        for r in rows:
            try:
                vals.append(float(r.get(y) or 0))
            except (TypeError, ValueError):
                vals.append(0.0)
        series.append((y, vals))
    return {"type": ch.get("type", "bar"), "title": ch.get("title") or t.get("title", ""), "x": x,
            "cats": cats, "series": series} if series else None


# ---------------- 엑셀 ----------------
def to_xlsx(doc):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    wb.remove(wb.active)
    head = PatternFill("solid", fgColor="1F3A5F")
    n = 0
    texts = []
    for b in doc["blocks"]:
        if b["type"] == "text":
            texts.append(b["md"])
            continue
        n += 1
        name = re.sub(r"[\[\]:*?/\\]", "", b.get("title") or f"표{n}")[:28] or f"표{n}"
        ws = wb.create_sheet(name if name not in wb.sheetnames else f"{name[:25]}_{n}")
        ws.append(b["columns"])
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = head
            c.alignment = Alignment(horizontal="center")
        for r in b["rows"]:
            ws.append([cell(r.get(c)) for c in b["columns"]])
        for i, c in enumerate(b["columns"], 1):
            w = max([len(str(c))] + [len(str(r.get(c) or "")) for r in b["rows"][:200]])
            ws.column_dimensions[get_column_letter(i)].width = min(max(8, w * 1.3), 50)
        ws.freeze_panes = "A2"
        cd = chart_data(b)
        if cd:
            xi = b["columns"].index(cd["x"]) + 1
            nrow = min(len(b["rows"]), 40) + 1
            ch = {"bar": BarChart, "line": LineChart, "pie": PieChart}.get(cd["type"], BarChart)()
            ch.title = cd["title"]
            for y, _ in cd["series"][:1 if cd["type"] == "pie" else 6]:
                yi = b["columns"].index(y) + 1
                ch.add_data(Reference(ws, min_col=yi, min_row=1, max_row=nrow), titles_from_data=True)
            ch.set_categories(Reference(ws, min_col=xi, min_row=2, max_row=nrow))
            ch.width, ch.height = 22, 11
            ws.add_chart(ch, f"{get_column_letter(len(b['columns']) + 2)}2")
    info = wb.create_sheet("출처")
    info.append(["제목", doc.get("title", "")])
    info.append(["만든 시각", dt.datetime.now().strftime("%Y-%m-%d %H:%M")])
    info.append(["기준일", str(today())])
    info.append(["만든 곳", "온트윈 (ERPNext + 온톨로지)"])
    for t in texts:
        for line in t.splitlines():
            if line.strip():
                info.append(["내용", strip_md(line)])
    for s in doc.get("sources") or []:
        info.append(["근거", s])
    info.column_dimensions["A"].width = 12
    info.column_dimensions["B"].width = 100
    if not [s for s in wb.sheetnames if s != "출처"]:
        wb.move_sheet("출처", 0)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------- 파워포인트 ----------------
def to_pptx(doc):
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.util import Emu, Pt
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    W, H = prs.slide_width, prs.slide_height
    navy = RGBColor(0x1F, 0x3A, 0x5F)

    def title_slide(text, sub):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        tb = s.shapes.add_textbox(Emu(600000), Emu(2300000), W - Emu(1200000), Emu(1200000)).text_frame
        tb.word_wrap = True
        tb.text = text
        tb.paragraphs[0].runs[0].font.size = Pt(34)
        tb.paragraphs[0].runs[0].font.bold = True
        tb.paragraphs[0].runs[0].font.color.rgb = navy
        p = tb.add_paragraph()
        p.text = sub
        p.runs[0].font.size = Pt(14)
        p.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    def slide(title):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        tb = s.shapes.add_textbox(Emu(450000), Emu(250000), W - Emu(900000), Emu(700000)).text_frame
        tb.text = title
        r = tb.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.color.rgb = Pt(24), True, navy
        return s

    title_slide(doc.get("title", "온트윈"), f"온트윈 · 기준일 {today()}")
    for b in doc["blocks"]:
        if b["type"] == "text":
            lines = [l for l in b["md"].splitlines() if l.strip()]
            for i in range(0, len(lines), 14):
                s = slide(doc.get("title", "") if i == 0 else f"{doc.get('title', '')} (계속)")
                tf = s.shapes.add_textbox(Emu(500000), Emu(1050000), W - Emu(1000000), H - Emu(1400000)).text_frame
                tf.word_wrap = True
                first = True
                for line in lines[i:i + 14]:
                    p = tf.paragraphs[0] if first else tf.add_paragraph()
                    first = False
                    lvl = 1 if re.match(r"^\s{2,}[-*]", line) else 0
                    txt = re.sub(r"^\s*(#+|[-*]|\d+\.)\s*", "", line)
                    for t, bold in runs(txt):
                        r = p.add_run()
                        r.text = t
                        r.font.size = Pt(16 if lvl == 0 else 14)
                        r.font.bold = bold or line.lstrip().startswith("#")
                    p.level = lvl
            continue
        cols, rows = b["columns"], b["rows"]
        per = 12
        for i in range(0, max(len(rows), 1), per):
            s = slide((b.get("title") or doc.get("title", "")) + (" (계속)" if i else ""))
            chunk = rows[i:i + per]
            shape = s.shapes.add_table(len(chunk) + 1, len(cols), Emu(450000), Emu(1050000), W - Emu(900000),
                                       Emu(370000) * (len(chunk) + 1))
            t = shape.table
            for j, c in enumerate(cols):
                t.cell(0, j).text = str(c)
            for ri, r in enumerate(chunk, 1):
                for j, c in enumerate(cols):
                    t.cell(ri, j).text = str(cell(r.get(c)))
            for ri in range(len(chunk) + 1):
                for j in range(len(cols)):
                    for p in t.cell(ri, j).text_frame.paragraphs:
                        for rr in p.runs:
                            rr.font.size = Pt(11 if len(cols) <= 6 else 9)
        cd = chart_data(b)
        if cd:
            s = slide(cd["title"] or "차트")
            data = CategoryChartData()
            data.categories = cd["cats"]
            for name, vals in cd["series"][:1 if cd["type"] == "pie" else 6]:
                data.add_series(name, vals)
            kind = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS,
                    "pie": XL_CHART_TYPE.PIE}.get(cd["type"], XL_CHART_TYPE.COLUMN_CLUSTERED)
            gf = s.shapes.add_chart(kind, Emu(600000), Emu(1100000), W - Emu(1200000), H - Emu(1500000), data)
            gf.chart.has_legend = len(cd["series"]) > 1 or cd["type"] == "pie"
            if gf.chart.has_legend:
                gf.chart.legend.position = XL_LEGEND_POSITION.BOTTOM
                gf.chart.legend.include_in_layout = False
    if doc.get("sources"):
        s = slide("근거")
        tf = s.shapes.add_textbox(Emu(500000), Emu(1050000), W - Emu(1000000), H - Emu(1400000)).text_frame
        tf.word_wrap = True
        tf.text = ", ".join(doc["sources"])
        tf.paragraphs[0].runs[0].font.size = Pt(14)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------------- 워드 ----------------
def to_docx(doc):
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.shared import Pt
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "맑은 고딕"
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    st.font.size = Pt(10.5)
    d.add_heading(doc.get("title", "온트윈"), level=0)
    d.add_paragraph(f"온트윈 · 기준일 {today()} · 만든 시각 {dt.datetime.now():%Y-%m-%d %H:%M}")
    for b in doc["blocks"]:
        if b["type"] == "text":
            for line in b["md"].splitlines():
                if not line.strip():
                    continue
                m = re.match(r"^(#+)\s*(.*)", line)
                if m:
                    d.add_heading(strip_md(m.group(2)), level=min(len(m.group(1)), 3))
                    continue
                bullet = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", line)
                if bullet:
                    style = "List Number" if bullet.group(2)[0].isdigit() else ("List Bullet 2" if len(bullet.group(1)) >= 2 else "List Bullet")
                    p = d.add_paragraph(style=style)
                    text = bullet.group(3)
                else:
                    p = d.add_paragraph()
                    text = line
                for t, bold in runs(text):
                    p.add_run(t).bold = bold
            continue
        if b.get("title"):
            d.add_heading(b["title"], level=2)
        cols = b["columns"]
        t = d.add_table(rows=1, cols=len(cols))
        t.style = "Light Grid Accent 1"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for j, c in enumerate(cols):
            t.rows[0].cells[j].text = str(c)
        for r in b["rows"][:500]:
            cs = t.add_row().cells
            for j, c in enumerate(cols):
                cs[j].text = str(cell(r.get(c)))
        cd = chart_data(b)
        if cd:
            img = chart_png(cd)
            if img:
                d.add_paragraph()
                d.add_picture(io.BytesIO(img), width=Pt(440))
                d.add_paragraph(f"그림: {cd['title']} (원 데이터는 위 표)").italic = True
    if doc.get("sources"):
        d.add_heading("근거", level=2)
        d.add_paragraph(", ".join(doc["sources"]))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def chart_png(cd):
    """워드용 차트 그림. 한글 글꼴이 없으면 그림 없이 표만 넣는다."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        fonts = [f.name for f in font_manager.fontManager.ttflist]
        kor = next((f for f in ("Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "AppleGothic")
                    if f in fonts), None)
        if not kor:
            return None
        plt.rcParams["font.family"] = kor
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
        if cd["type"] == "pie":
            ax.pie(cd["series"][0][1], labels=cd["cats"], autopct="%1.0f%%")
        else:
            n = len(cd["series"])
            w = 0.8 / n
            for i, (name, vals) in enumerate(cd["series"]):
                xs = [k + i * w for k in range(len(vals))]
                (ax.plot if cd["type"] == "line" else ax.bar)(xs, vals, label=name, **({} if cd["type"] == "line" else {"width": w}))
            ax.set_xticks([k + 0.4 - w / 2 for k in range(len(cd["cats"]))])
            ax.set_xticklabels(cd["cats"], rotation=45, ha="right", fontsize=8)
            if n > 1:
                ax.legend()
        ax.set_title(cd["title"])
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None


def to_csv(doc):
    import csv
    t = next((b for b in doc["blocks"] if b["type"] == "table"), None)
    buf = io.StringIO()
    if t:
        w = csv.DictWriter(buf, fieldnames=t["columns"], extrasaction="ignore")
        w.writeheader()
        w.writerows(t["rows"])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export(rt, fmt, body):
    doc = normalize(rt, body)
    fn = {"xlsx": to_xlsx, "pptx": to_pptx, "docx": to_docx, "csv": to_csv}[fmt]
    safe = re.sub(r"[\\/:*?\"<>|]", "", doc.get("title", "온트윈"))[:40] or "온트윈"
    return fn(doc), f"{safe}_{dt.date.today():%Y%m%d}.{fmt}", MIME[fmt]
