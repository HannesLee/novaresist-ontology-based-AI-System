# 노바레지스트 → ERPNext 데이터 적재기

가상 회사 노바레지스트의 기준정보와 2026년 1년치 거래를 ERPNext v16에 넣는다.
파이썬 기본 라이브러리만 쓰므로 추가로 설치할 것은 없다.

## 데이터 (`data/`)

| 폴더 | 내용 |
| --- | --- |
| `data/master/` | 기준정보 CSV: 품목·공급사·에이전시·고객·고객 승인·창고·설비·레시피(BOM)·검사 기준 |
| `data/erp/` | 거래 CSV: 구매요청·발주·입고·검사(측정값)·작업지시·작업 기록·재고 이동·수주·출하·부적합·정비·계획 |
| `data/docs/` | ERP 밖 문서: 메일, 회의록, 결정 기록, SOP, 운영 규칙집 (온톨로지의 '결정·사건' 원천, ERP에는 넣지 않음) |

전부 가상 데이터다. 데이터 생성에 쓴 정답 기록(숨긴 원인 등)은 평가용이라 올리지 않는다.

IQC 측정 항목(v2): 순도, 수분, 금속 26종(Ag~Zr), 분자량 편차, 분산도. 레진 금속은 5 lot 중 1 lot, 나머지 분류는 매 lot 측정한다.

## 실행 (WSL Ubuntu)

```
python3 nr_load.py check     # 접속 확인 (처음이면 API Key/Secret을 물어보고 .env에 저장)
python3 nr_load.py all       # 설정 → 기준정보 → 기초재고·거래 → 검증 (20~40분)
```

단계별로 나눠서 실행할 수도 있다: `setup`, `master`, `tx`, `finish`.
`tx 2026-03-31`처럼 날짜를 주면 그날까지만 넣는다.
중간에 멈추면 같은 명령을 다시 실행한다. 이미 들어간 문서는 건너뛴다.

## 오늘 날짜까지만 들어간다

ERPNext는 미래 날짜의 입고(Purchase Receipt)를 막는다. 그래서 `tx`는 기본적으로 **실행한 날까지**의 거래만 넣는다.
이후 거래(10월 22일~12월 31일)는 날짜가 지난 뒤 `python3 nr_load.py tx`를 다시 실행하면 그날까지 이어서 들어간다.
진행 중인 작업지시·미입고 발주·미출하 수주는 ERPNext에서도 '진행 중'으로 보인다.

검증 결과(테스트 서버, 2026-10-21 기준): 문서 건수 11종 모두 일치, lot·창고별 재고 275건 차이 0건, 약 35분 소요.

## 무엇이 어디로 들어가나

| 원본 | ERPNext |
| --- | --- |
| item_raw / item_fg / item_supplier | Item (공급사 품명 = Supplier Items, 고객 품번 = Customer Items, 생산 약칭 = 추가 필드) |
| supplier / agency | Supplier (에이전시도 공급사로, 공급 분류 '에이전시') |
| customer / customer_approval | Customer / 추가 화면 NR Customer Approval |
| warehouse | Warehouse WH-10~WH-70 + 재공 창고 WH-WIP |
| workstation / operation / bom | Workstation, Operation, BOM(1,000 L = 264병 기준, 공정 5개) |
| qc_template | Quality Inspection Template / Parameter |
| stock_opening_2026 | Stock Reconciliation SR-OPEN-2026 (Opening Stock) |
| material_request / purchase_order | Material Request / Purchase Order (품의번호·상신일·승인일·에이전시·회신 납기 = 추가 필드) |
| purchase_receipt | Purchase Receipt (lot = Batch, 공급사 lot = Batch 추가 필드) |
| quality_inspection(+reading) | Quality Inspection (IQC는 입고와 연결, 출하검사는 창고 이동과 연결) |
| stock_move (IQC·출하검사 이동) | Stock Entry: Material Transfer (SE-IQC-…, SE-OQC-…) |
| work_order / job_card | Work Order + Job Card(설비·시간·필터 lot·작업조) |
| stock_move (생산 투입·충전) | Stock Entry: Material Transfer for Manufacture (SE-ISS-…) |
| stock_entry_manufacture (제조 완료) | Stock Entry: Manufacture (SE-MFG-…) |
| sales_order / delivery_note | Sales Order / Delivery Note (lot·잔여 유효기간·납기 준수) |
| non_conformance | Non Conformance (SOP를 Quality Procedure로 연결) |
| downtime | Downtime Entry |
| stock_reconciliation | Stock Reconciliation SR-26-1215 |
| sales_forecast / production_plan | 추가 화면 NR Sales Forecast / NR Production Plan |

## ERP 도입 시점(2026-01-01) 이관 원칙

- 2025년에 낸 구매요청·발주·수주 중 2026년에 입고·출하된 것은 원래 날짜로 만든다(회계연도 2025 추가).
- 2025년에 생산까지 끝난 작업지시 WO-25-0067은 만들지 않고, 완제품 lot만 기초재고로 옮긴다.
- 2025년에 원재료를 넣고 2026년에 끝난 WO-25-0073·0075는 투입 원재료를 재공 창고 기초재고로 옮긴다.
- 포장재는 lot 관리 대상이 아니라서 수량만 관리한다. 낱개 단위의 소수점 기초재고는 올림했다.
- 솔벤트를 L로 입고한 7건은 밀도로 kg 환산한다.
- 2025년에 다 쓰고 기록이 없는 lot은 lot 번호의 입고일 + 품목 유효기간으로 유효기간을 추정했다.
