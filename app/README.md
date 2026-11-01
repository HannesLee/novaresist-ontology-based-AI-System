# 프로그램 코드

| 폴더 | 역할 |
| --- | --- |
| `erp/` | ERPNext REST 클라이언트 |
| `ontology/` | 정의 파일 해석(schema), 객체·연결 만들기(engine), 저장소(store), 동기화(sync), 문서 연결(docs), 정의 수정·버전(editor) |
| `functions/` | 질문 함수: find/get, 역추적·순추적, 공통 요인, IQC 추이·이상치, 출하 판정, 재승인, 부족 예측, 영향 수주, 의심 lot / 계산 속성 |
| `agent/` | Claude 도구 정의(온톨로지 모드 / ERP만 모드)와 대화 루프 |
| `board/` | 작업대: 데이터 카드, 생성 코드 격리 실행 |
| `export/` | 엑셀·파워포인트·워드·CSV 내보내기 |
| `web/` | FastAPI 서버(화면·API·웹훅·ERP 중계)와 화면 파일 |

명령: `python3 -m app check | sync | poll | stats | serve`
