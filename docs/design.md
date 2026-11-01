# 설계 (design.md)

버전 0.1 · 2026-11-01

## 1. 온톨로지 정의 파일 형식
`ontology/ontology.yaml` 하나로 객체·링크·규칙을 정의한다. 엔진은 이 파일만 보고 ERP 데이터를 객체로 만든다.
→ 온톨로지를 바꾸고 싶으면 코드가 아니라 이 파일을 고친다.

```yaml
objects:
  raw_lot:                       # 객체 id
    name: 원재료 lot              # 현업 이름
    aliases: [자재 lot, RL]       # 현업에서 섞어 쓰는 말
    source: {doctype: Batch, filter: "item_group in 원재료"}   # ERP 출처
    key: name
    properties:
      supplier_lot: custom_supplier_lot
      expiry: expiry_date
    computed:                    # 계산 속성(함수 층)
      status: lot_status         # IQC 전 / 합격 / 보류 / 소진
links:
  - {from: raw_lot, rel: 입고, to: receipt, via: "Purchase Receipt Item.batch_no"}
rules:
  - id: ship_shelf_life
    text: 완제품 잔여 유효기간이 고객 기준(A·B 120일, C·D 90일) 이상이어야 출하
    applies_to: [fg_lot, customer]
```

## 2. 저장소 스키마 (SQLite)
| 테이블 | 열 |
| --- | --- |
| objects | type, id, name, props(JSON), source_doctype, source_name, updated_at |
| links | src_type, src_id, rel, dst_type, dst_id, props(JSON) |
| aliases | type, id, alias |
| facts | subject_type, subject_id, predicate, value, since, source(문서), confidence |
| sync_state | doctype, last_modified |

`facts`는 문서에서 꺼낸 사실(예: BP-KR01 / 원료 공급처 변경 / 2026-04 / 메일 10-20).

## 3. 동기화
- 전체 적재: 정의 파일의 모든 source doctype을 읽어 객체·링크를 만든다.
- 변경분: doctype별 `modified > last_modified`만 다시 읽는다.
- 웹훅: ERPNext Webhook(on_submit, on_update_after_submit, on_cancel) → `POST /webhook` → 문서 1건과 그 문서가 바꾸는 링크만 갱신.
- lot 재고 위치·상태는 ERP의 lot 수량 API로 질문 시점에 계산(항상 최신).

## 4. 함수
| 함수 | 입력 | 출력 |
| --- | --- | --- |
| find(text) | 이름·코드·별칭 | 후보 객체 |
| get(type, id) | 객체 | 속성 + 링크 요약 + 관련 사실·문서 |
| trace_back(fg_lot) | 완제품 lot | 작업지시, 공정 설비, 필터 lot, 투입 원재료 lot(공급사·입고·IQC 값), 관련 문서 |
| trace_forward(raw_lot \| 조건) | 원재료 lot 또는 (원재료·공급사·제조일 범위) | 완제품 lot, 현재 위치, 출하·고객 |
| common_factors(fg_lots) | 완제품 lot 목록 | 공통 요인과 비교군 대비 비율 |
| shippable(fg_lot, customer) | lot, 고객 | 가능/불가 + 사유(유효기간·출하검사·투입 원재료 부적합·의심 규칙) |
| requal_needed(material, supplier) | 원재료, 새 공급사 | 재승인 필요한 고객·제품, 기간 |
| suspect_lots(조건) | 원재료·공급사·제조일 범위 | 의심 원재료 lot, 영향 완제품 lot |

## 5. AI 에이전트
- 모델: Claude (API). 시스템 프롬프트: 역할, 기준일, "숫자는 도구 결과만 인용", 답변 형식(결론·근거·불확실성).
- 도구 묶음 두 가지:
  - **온톨로지 모드**: 위 함수들
  - **일반 모드(비교용)**: `erp_list(doctype, filters, fields)`, `erp_get(doctype, name)` — ERP 원시 조회만
- 답변 하단에 근거 목록(도구 호출 결과에 나온 문서번호)을 자동 표시.

## 6. 화면 (Streamlit)
1. 챗봇: 질문 입력 → 답변 + 근거 + 사용한 도구 펼쳐 보기
2. 탐색기: 객체 검색 → 속성·링크, lot 이력 그래프
3. 비교: 질문 1개 → 일반 Claude / 본 시스템 나란히, 소요 시간·도구 호출 수 기록

## 7. 평가 설계
- 질문 6개(힌트 없는 형태 포함), 두 모드 각 2회 실행. 채점 기준은 실행 전에 고정.
- 시연 영상: (1) 클레임 원인 추적 비교 (2) ERP 변경 → 답 변경 (3) 결과표.
