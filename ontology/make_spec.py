"""ontology.yaml → docs/ontology_spec.md (문장형 명세).

정의 파일이 바뀌면 이 스크립트를 다시 돌려 명세 문서를 맞춘다.
    python ontology/make_spec.py
"""
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
d = yaml.safe_load(open(ROOT / "ontology/ontology.yaml", encoding="utf-8"))
O = d["objects"]
out = []
w = out.append


def nm(k):
    if isinstance(k, list):
        return "·".join(nm(x) for x in k)
    return O[k]["name"] if k in O else ("모든 객체" if k == "*" else k)


CARD = {"1": "반드시 하나", "0..1": "없거나 하나", "N..1": "여럿이 하나에", "1..5": "1~5개",
        "N..M": "여럿과 여럿", "N": "여럿"}

w(f"# 노바레지스트 온톨로지 명세 v{d['meta']['version']}\n")
w("설계: 이시형 · 이 문서는 `ontology/ontology.yaml`에서 자동으로 만든다(`python ontology/make_spec.py`). "
  "정의를 바꾸려면 yaml을 고치거나 프로그램의 편집 화면을 쓴다.\n")

w("## 0. 원칙\n")
for p in d["meta"]["principles"]:
    w(f"- {p}")
w("\n## 1. 같은 대상을 알아보는 규칙\n")
for p in d["identity"]:
    w(f"- {p}")

w("\n## 2. 객체 목록\n")
w("| # | 객체 | 현업에서 부르는 말 | ERP 출처 |")
w("| --- | --- | --- | --- |")
for i, (k, o) in enumerate(O.items(), 1):
    src = o["source"]
    s = src.get("doctype") or ", ".join(src.get("doctypes", [])) or src.get("derived_from") or "문서: " + ", ".join(src.get("documents", []))
    w(f"| {i} | {o['name']} (`{k}`) | {', '.join(o.get('aliases', []))} | {s} |")

w("\n## 3. 객체 정의\n")
for i, (k, o) in enumerate(O.items(), 1):
    w(f"### 3-{i}. {o['name']}\n")
    if o.get("description"):
        w(o["description"] + "\n")
    if o.get("properties"):
        w("- 속성: " + ", ".join(o["properties"].keys()))
    if o.get("measurements"):
        w("- 측정값: 항목마다 값·하한·상한·판정을 가진다(검사 1건에 여러 측정값).")
    if o.get("computed"):
        w("- 계산 속성(물어볼 때 계산): " + ", ".join(o["computed"].keys()))
    for l in o.get("links", []):
        w(f"- {o['name']}은(는) {nm(l['to'])}와(과) **{l['rel']}** 관계다 ({CARD.get(str(l.get('card')), l.get('card'))}).")
    if o.get("fact_types"):
        w("- 꺼내는 사실: " + ", ".join(o["fact_types"]) + f". 형식: {o['fact_format']}")
    w("")

q = d["iqc"]
w("## 4. 원재료 입고 검사(IQC)\n")
w("- 검사 항목: " + ", ".join(q["items"]))
w("- 금속 26종: " + ", ".join(q["metals"]))
w("\n| 분류 | 순도(%) 이상 | 수분(ppm) 이하 | 금속(원소별 ppb) 이하 | 분자량 편차 | 분산도 | 금속 측정 주기 |")
w("| --- | --- | --- | --- | --- | --- | --- |")
for cat, s in q["spec"].items():
    if isinstance(s, str):
        w(f"| {cat} | {s} | | | | | |")
        continue
    w(f"| {cat} | {s['순도_min']} | {s['수분_max_ppm']} | {s['금속_max_ppb']} | "
      f"{'±' + str(s['분자량편차_pct']) + '%' if '분자량편차_pct' in s else '-'} | {s.get('분산도_max', '-')} | {s['금속_주기']} |")
w(f"\n- 규격 대비 여유가 {q['margin_warning_pct']}%보다 작으면 '합격·경계'로 본다.")
w(f"- 같은 원재료·공급사 최근 lot 평균 ± {q['outlier_sigma']}σ 밖이면 '합격·이상치'로 본다.")
w(f"- {q['unmeasured']}.")

w("\n## 5. 규칙\n")
w("| ID | 조건 | 판단 | 다음 행동 | 숫자 |")
w("| --- | --- | --- | --- | --- |")
for r in d["rules"]:
    p = ", ".join(f"{a} {b}" for a, b in r.get("params", {}).items())
    w(f"| {r['id']} | {r['when']} | {r['then']} | {r['next']} | {p} |")

w("\n## 6. 함수 (AI가 부르는 질문 도구)\n")
w("| 함수 | 입력 | 출력 |")
w("| --- | --- | --- |")
for k, f in d["functions"].items():
    w(f"| `{k}` | {f['in']} | {f['out']} |")

w("\n## 7. 액션 (ERP 반영, 사람 승인 필수)\n")
a = dict(d["actions"])
pol = a.pop("policy")
for k, v in a.items():
    w(f"- `{k}`: {v['what']}")
w(f"- {pol}")

w("\n## 8. 갱신\n")
for p in d["sync"]:
    w(f"- {p}")
w("\n## 9. 수정과 버전\n")
for p in d["editing"]:
    w(f"- {p}")
w("\n## 10. 데이터 품질\n")
for p in d["data_quality"]:
    w(f"- {p['id']}: {p['when']} → '{p['flag']}'" + (f", 제안: {p['suggest']}" if p.get("suggest") else ""))

(ROOT / "docs/ontology_spec.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("docs/ontology_spec.md 작성")
