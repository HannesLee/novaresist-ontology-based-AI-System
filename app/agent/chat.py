"""대화 루프: Claude가 도구를 부르고, 결과를 근거로 답한다."""
import re
import time

import anthropic

from app import config
from app.agent import tools as T
from app.functions.core import today

ID = re.compile(r"\b(?:PO|MR|GR|QI|WO|SO|DN|NCR|AP|SE|SR)-\d\d-\d{3,4}(?::\S+)?|\b(?:RL|PL)-\d{6}-[A-Z0-9]+-\d\d|"
                r"\bBP-[A-Z]{2}\d\d|\bAG-0\d|\bCU-[A-D]\b|\b(?:RS|PG|SV|AD|PK)-[A-Z]?\d\d|\bPR-[A-Z]{1,2}\d\d|\bMF-[A-Z0-9]+")


def _batchim(w):
    c = str(w).strip()[-1:]
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28 != 0
    return bool(re.match(r"[bcdfgjklmnpqrstvxz0-9]", c, re.I))


def _josa(w, pair):
    a, b = {"을(를)": ("을", "를"), "이(가)": ("이", "가"), "은(는)": ("은", "는"), "와(과)": ("과", "와")}.get(pair, (pair, pair))
    return a if _batchim(w) else b


def _tail(target, phrase):
    """'공급사' + '을(를) 경유한다' → '[공급사]를 경유한다'"""
    m = re.match(r"^(을\(를\)|이\(가\)|은\(는\)|와\(과\))(.*)$", phrase or "")
    return f"[{target}]{_josa(target, m.group(1))}{m.group(2)}" if m else f"[{target}]{phrase}"


def system_prompt(rt, mode, context=None):
    d = rt["schema"]
    base = f"""너는 '온트윈' — 가상 반도체 PR 소재사 노바레지스트(NovaResist)의 업무 판단 도우미다.
기준일: {today()} (이 날짜 이후 정보는 없다고 본다)
사용자: 구매·품질·생산·영업 담당자

규칙
- 숫자·날짜·lot 번호는 도구 결과에 나온 것만 쓴다. 추측한 값은 '추정'이라고 밝힌다.
- 판단에는 근거 문서번호·객체 id를 붙인다.
- 답 형식: **결론** (한두 문장) → **근거** (항목별, id 포함) → **확인 필요·다음 행동**
- 한국어, 짧고 정확하게. 표가 낫다면 마크다운 표.
- 사용자가 표·자료·보고서·엑셀·PPT를 만들어 달라고 하면 make_table 도구로 만든다(화면에 내보내기 버튼이 붙는다).
"""
    if mode == "ontology":
        objs = "\n".join(f"- {o['name']} ({k}): {', '.join(o.get('aliases', []))}" for k, o in d["objects"].items())
        rules = "\n".join(f"- {r['id']}: {r['when']} → {r['then']} ({r['next']})" for r in d["rules"])
        card = {"1": "꼭 1개", "N..1": "꼭 1개", "0..1": "없거나 1개"}
        rels = []
        for k, o in d["objects"].items():
            for l in o.get("links") or []:
                tos = l["to"] if isinstance(l["to"], list) else [l["to"]]
                tn = "·".join(d["objects"][t]["name"] if t in d["objects"] else "모든 객체" for t in tos)
                rels.append(f"- {o['name']}{_josa(o['name'], '은(는)')} {_tail(tn, l.get('phrase') or ('—' + l['rel'] + '→'))}  "
                            f"(그래프 관계: {k}-[:{l['rel'].replace(' ', '_')}]->{'|'.join(tos)}, {o['name']} 1개당 {card.get(str(l.get('card')), '여러 개')})")
        rels = "\n".join(rels)
        base += f"""
너는 회사 온톨로지(객체·연결·규칙)를 도구로 쓴다. 온톨로지는 그래프 DB에 들어 있다.
- 먼저 find/get으로 대상을 확정한다.
- 정해진 업무 판단(추적, 출하 판정, 재승인, 부족 예측)은 함수를 쓴다(함수도 내부에서 그래프 DB를 질의한다).
- 함수로 안 되는 여러 단계 연결·집계는 graph_query(Cypher)로 직접 찾는다.
객체 종류(이름: 현업 별칭)
{objs}

관계문 (온톨로지의 뼈대)
{rels}

규칙
{rules}

그래프 스키마 (그래프 DB, Cypher)
{rt["graph"].schema_text if rt.get("graph") else "(없음)"}
"""
    else:
        base += """
너는 ERPNext를 직접 조회하는 도구만 가진다. erp_doctypes로 화면 구성을 보고 erp_list/erp_get으로 찾아라.
"""
    if context:
        base += f"\n지금 사용자가 보고 있는 ERP 화면: {context}. '이 건', '이거'는 이 문서를 뜻한다.\n"
    return base


def ask(rt, question, mode="ontology", history=None, context=None, docs=True, model=None, max_rounds=30, on_step=None):
    """질문 하나 → {'answer', 'steps', 'evidence', 'usage', 'seconds'}"""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    tools = T.ONTO_TOOLS if mode == "ontology" else T.ERP_TOOLS + (T.DOC_TOOLS if docs else [])
    sys = [{"type": "text", "text": system_prompt(rt, mode, context), "cache_control": {"type": "ephemeral"}}]
    msgs = list(history or []) + [{"role": "user", "content": question}]
    steps, seen_text, usage = [], [], {"input": 0, "output": 0, "cache_read": 0}
    t0 = time.time()
    rt["onto"].clear()
    answer = ""
    tables = []
    for rnd in range(max_rounds):
        last_round = rnd == max_rounds - 1
        # 대화가 길어질수록 같은 앞부분을 매번 다시 보낸다 → 마지막 메시지에 캐시 표시를 옮겨 붙여 다시 읽는 비용을 줄인다
        for m in msgs:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict):
                        b.pop("cache_control", None)
        if isinstance(msgs[-1].get("content"), list) and msgs[-1]["content"]:
            msgs[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        # 마지막 라운드: 도구 없이 지금까지 모은 결과로 답하게 한다(빈손으로 끝나지 않게)
        kw = {"tools": tools} if not last_round else {"tools": tools, "tool_choice": {"type": "none"}}
        r = client.messages.create(model=model or config.CLAUDE_MODEL, max_tokens=8000, system=sys,
                                   messages=msgs, **kw)
        usage["input"] += r.usage.input_tokens
        usage["output"] += r.usage.output_tokens
        usage["cache_read"] += getattr(r.usage, "cache_read_input_tokens", 0) or 0
        usage["cache_write"] = usage.get("cache_write", 0) + (getattr(r.usage, "cache_creation_input_tokens", 0) or 0)
        msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]})
        if r.stop_reason != "tool_use":
            answer = "".join(b.text for b in r.content if b.type == "text")
            if r.stop_reason == "max_tokens" and not answer.strip():
                msgs.pop()  # 잘린 답(미완성 도구 호출 포함)은 버리고, 직전 사용자 메시지에 요청을 덧붙인다
                note = {"type": "text", "text": "출력 한도에 걸렸다. 도구 없이 지금까지 결과로 결론·근거를 간결하게 답하라."}
                if isinstance(msgs[-1]["content"], list):
                    msgs[-1]["content"].append(note)
                else:
                    msgs[-1]["content"] = [{"type": "text", "text": msgs[-1]["content"]}, note]
                continue
            break
        results = []
        for b in r.content:
            if b.type != "tool_use":
                continue
            t1 = time.time()
            g = rt.get("graph")
            mark = len(g.log) if g else 0
            try:
                out = T.run(rt, mode, b.name, b.input)
            except Exception as e:
                out = {"오류": str(e)[:500]}
            txt = T.dumps(out)
            seen_text.append(txt)
            step = {"tool": b.name, "input": b.input, "output": txt[:3000], "ms": int((time.time() - t1) * 1000),
                    "cypher": [x["cypher"] for x in (g.log[mark:] if g else [])][:12]}
            steps.append(step)
            if on_step:
                on_step(step)
            if b.name == "make_table" and isinstance(out, dict) and out.get("card_id"):
                tables.append(out["card_id"])
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": txt})
        msgs.append({"role": "user", "content": results})
    else:
        answer = "(도구 호출 횟수 한도에 도달했습니다. 질문을 좁혀 주세요.)"
    found = set(ID.findall("\n".join(seen_text)))
    evidence = sorted({x for x in ID.findall(answer) if x in found})
    unverified = sorted({x for x in ID.findall(answer) if x not in found})
    return {"answer": answer, "steps": steps, "tables": tables, "model": model or config.CLAUDE_MODEL, "onto_version": str(rt["schema"]["meta"]["version"]), "evidence": evidence, "unverified": unverified, "usage": usage,
            "seconds": round(time.time() - t0, 1), "mode": mode,
            "history": msgs[:1 + len(history or [])] + [{"role": "assistant", "content": answer}]}
