# 구조 (structure.md)

버전 0.2 · 2026-11-01

## 1. 전체 흐름
```
ERPNext ──API(읽기)──▶ connector ──▶ sync ──▶ store(SQLite: objects / links / aliases / facts)
   │                                   ▲              │
   └──웹훅(문서 변경)──▶ webhook 수신 ─┘              ▼
ontology/ontology.yaml ──▶ engine(정의 해석) ──▶ functions(추적·판정)
                                                       │
                              Claude API (tool use) ◀──┘
                                       │
                        Streamlit UI: 챗봇 · 탐색기 · 비교 · 그래프 · 온톨로지 편집
```

## 2. 폴더
```
app/
  config.py          설정(.env 읽기: ERP 주소·키, Anthropic 키, 모델)
  erp/
    client.py        ERPNext REST 클라이언트(읽기 전용)
    webhook.py       웹훅 수신(FastAPI) → sync 호출
  ontology/
    schema.py        ontology.yaml 읽기·검증
    editor.py        정의 수정·버전 저장·되돌리기
    store.py         SQLite 저장소(objects, links, aliases, facts, sync_state)
    sync.py          전체 적재 / 변경분 적재 / 문서 1건 갱신
    docs_ingest.py   메일·회의록·결정 기록 → 이벤트 객체 + 사실 추출
  functions/
    trace.py         trace_back(lot), trace_forward(lot), common_factors(lots)
    rules.py         규칙 판정: shippable, requal_needed, suspect_lots, iqc 경계·이상치
    planning.py      shortage_forecast, impacted_orders
    actions.py       보류 이동·NCR 초안(승인 후 실행)
  agent/
    tools.py         Claude에 주는 도구 정의(온톨로지 도구 / ERP 원시 조회 도구)
    chat.py          대화 루프, 근거 표시
    compare.py       비교 모드 실행·기록
  ui/
    app.py           Streamlit 진입점
    graph.py         설계도·데이터 그래프
    edit.py          온톨로지 편집 화면
ontology/
  ontology.yaml      온톨로지 정의 (작성: 이시형)
docs/                명세·평가
erp_seed/            가상 회사 데이터 적재 스크립트(nr_load.py 등)
```

## 3. 실행 단위
| 프로세스 | 역할 | 포트 |
| --- | --- | --- |
| ERPNext (Docker) | ERP | 8080 |
| webhook (uvicorn) | 웹훅 수신 → 동기화 | 8001 |
| ui (streamlit) | 챗봇·탐색기·비교 | 8501 |

## 4. 데이터 흐름 예: "이 lot 출하해도 돼?"
1. 사용자가 질문 → Claude가 `find("PL-260918-K05-01")` 호출
2. `shippable(lot, customer)` 호출 → 잔여 유효기간, 출하검사 결과, 투입 원재료 lot의 부적합 여부, 의심 lot 규칙을 확인
3. 결과와 근거(QI-, NCR-, RL- 번호)를 받아 Claude가 답변
4. 사용자가 ERPNext에서 NCR을 등록 → 웹훅 → sync가 NCR 객체와 링크 갱신 → 같은 질문의 답이 바뀜
