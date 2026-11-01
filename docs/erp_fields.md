# ERPNext 필드 참고표

`ontology.yaml`에서 속성·링크를 정할 때 쓰는 ERP 필드 목록이다. 기준일 2026-10-21 데이터의 예시값을 함께 적었다.
`custom_`으로 시작하는 필드는 노바레지스트용으로 추가한 필드다.

## Supplier  (30행)

| 필드 | 예시 |
| --- | --- |
| `name` | AG-01 |
| `supplier_name` | 상하이 링크 트레이딩(가상) |
| `supplier_type` | Company |
| `supplier_group` | 에이전시 |
| `custom_bp_category` | 레진 |
| `custom_agency` | AG-01 |
| `custom_incoterms` | FOB |
| `custom_payment_terms_text` | 선급 30% |
| `custom_rating` | C |
| `custom_std_lead_time` | 100 |
| `custom_customs_days` | 9 |
| `country` | China |
| `hold_type` | All |
| `language` | en |

## Item  (78행)

| 필드 | 예시 |
| --- | --- |
| `name` | AD-01 |
| `item_code` | AD-01 |
| `item_name` | 퀜처 아민-1 |
| `custom_production_alias` | Q1 |
| `item_group` | 첨가제 |
| `custom_sub_category` | 퀜처 |
| `custom_storage_condition` | 상온 |
| `custom_hazardous` | 1 |
| `custom_density` | 0.97 |
| `custom_qc_warehouse` | WH-10 - NR |
| `custom_pass_warehouse` | WH-21 - NR |
| `custom_solid_pct` | 8.0 |
| `custom_annual_plan_bottles` | 1167 |
| `stock_uom` | Kg |
| `is_stock_item` | 1 |
| `is_sales_item` | 1 |
| `is_purchase_item` | 1 |
| `standard_rate` | 1800000.0 |
| `description` | BP-JP09(주) YK-Q1 3200000원/kg |
| `valuation_rate` | 3200000.0 |
| `end_of_life` | 2099-12-31 |
| `default_material_request_type` | Purchase |
| `has_batch_no` | 1 |
| `has_expiry_date` | 1 |
| `shelf_life_in_days` | 450 |
| `use_serial_no_wise_valuation` | 1 |
| `variant_based_on` | Item Attribute |
| `custom_safety_stock_months` | 2.0 |
| `lead_time_days` | 70 |
| `last_purchase_rate` | 3200000.0 |
| `grant_commission` | 1 |
| `include_item_in_manufacturing` | 1 |
| `default_bom` | BOM-PR-AD01-001 |
| `customer_code` | B-PR-AD01-05 |
| `quality_inspection_template` | IQC-첨가제 |

## Item Supplier  (61행)

| 필드 | 예시 |
| --- | --- |
| `name` | gfgpfn1oc7 |
| `parent` | RS-01 |
| `supplier` | BP-JP01 |
| `supplier_part_no` | SKR-110 |

## Item Customer Detail  (24행)

| 필드 | 예시 |
| --- | --- |
| `name` | gft8r4irkm |
| `parent` | PR-I01 |
| `customer_name` | CU-D |
| `ref_code` | D-IL-I01-01 |

## Customer  (4행)

| 필드 | 예시 |
| --- | --- |
| `name` | CU-A |
| `customer_name` | A사(가상, 메모리) |
| `customer_type` | Company |
| `customer_group` | 메모리 |
| `custom_requal_days` | 180 |
| `custom_min_shelf_life_days` | 120 |
| `custom_sales_share` | 45% |
| `territory` | All Territories |
| `language` | en |

## NR Customer Approval  (24행)

| 필드 | 예시 |
| --- | --- |
| `name` | gha2s35bpd |
| `customer` | CU-A |
| `item` | PR-K01 |
| `customer_item_code` | A-K01-01 |
| `approval_date` | 2024-03-17 |
| `approved_materials` | RS-01@BP-JP01, PG-01@BP-JP05, AD-01@BP-JP09, AD-06@BP-JP11,  |

## Warehouse  (15행)

| 필드 | 예시 |
| --- | --- |
| `name` | All Warehouses - NR |
| `warehouse_name` | All Warehouses |
| `parent_warehouse` | All Warehouses - NR |
| `is_group` | 1 |
| `address_line_1` | 입고대기 창고 / 레진·PAG·첨가제 IQC 전 격리 |
| `address_line_2` | 냉장 구역 + 상온 구역 / 재고 상태: IQC 전 |
| `warehouse_type` | Transit |

## Workstation  (19행)

| 필드 | 예시 |
| --- | --- |
| `name` | FI-A1 |
| `workstation_name` | FI-A1 |
| `workstation_type` | 충전 라인(자동) |
| `custom_capacity` | 120.0 |
| `custom_pm_cycle_days` | 180 |
| `production_capacity` | 3 |
| `status` | Off |
| `description` | 병/시간 |

## BOM  (24행)

| 필드 | 예시 |
| --- | --- |
| `name` | BOM-PR-AD01-001 |
| `item` | PR-AD01 |
| `quantity` | 264.0 |
| `uom` | 병 |
| `cost_allocation_per` | 100.0 |
| `cost_allocation` | 121873056.0 |
| `with_operations` | 1 |
| `transfer_material_against` | Work Order |
| `is_active` | 1 |
| `is_default` | 1 |
| `set_rate_of_sub_assembly_item_based_on_bom` | 1 |
| `raw_material_cost` | 121873056.0 |
| `base_raw_material_cost` | 121873056.0 |
| `total_cost` | 121873056.0 |
| `base_total_cost` | 121873056.0 |
| `rm_cost_as_per` | Valuation Rate |
| `buying_price_list` | Standard Buying |
| `plc_conversion_rate` | 1.0 |
| `currency` | KRW |
| `conversion_rate` | 1.0 |
| `item_name` | NR-A 510 |
| `description` | NR-A 510 (ArF 건식, 1갤런 병) |
| `route` | bom-pr-ad01-001 |

## BOM Item  (286행)

| 필드 | 예시 |
| --- | --- |
| `name` | ggc0egn73e |
| `parent` | BOM-PR-I01-001 |
| `item_code` | SV-03 |
| `item_name` | 에틸락테이트(EL) |
| `is_stock_item` | 1 |
| `description` | BP-KR05(주) SH-EL UP 7400원/kg |
| `qty` | 521.36 |
| `uom` | Kg |
| `stock_qty` | 521.36 |
| `stock_uom` | Kg |
| `conversion_factor` | 1.0 |
| `rate` | 7400.0 |
| `base_rate` | 7400.0 |
| `amount` | 3858064.0 |
| `base_amount` | 3858064.0 |
| `qty_consumed_per_unit` | 1.974848485 |
| `include_item_in_manufacturing` | 1 |

## Material Request  (356행)

| 필드 | 예시 |
| --- | --- |
| `name` | MR-25-0006 |
| `title` | Purchase Request for KrF 레진 PHS-B |
| `material_request_type` | Purchase |
| `custom_request_dept` | 구매팀 |
| `custom_request_reason` | MRP |
| `transaction_date` | 2025-10-01 |
| `schedule_date` | 2025-12-24 |
| `buying_price_list` | Standard Buying |
| `status` | Ordered |
| `per_ordered` | 100.0 |
| `letter_head` | Company Letterhead - Grey |

## Material Request Item  (356행)

| 필드 | 예시 |
| --- | --- |
| `name` | gl6ijedh2p |
| `parent` | MR-25-0016 |
| `item_code` | RS-12 |
| `item_name` | ArF 액침 레진 IM-C |
| `schedule_date` | 2026-01-23 |
| `description` | BP-CN01(주) JR-9120 1050000원/kg; BP-JP03(미승인 후보) TK-IM9 11045 |
| `item_group` | 레진 |
| `qty` | 75.0 |
| `stock_uom` | Kg |
| `warehouse` | WH-10 - NR |
| `uom` | Kg |
| `conversion_factor` | 1.0 |
| `stock_qty` | 75.0 |
| `projected_qty` | 175.0 |
| `actual_qty` | 450.0 |
| `ordered_qty` | 75.0 |
| `rate` | 760000.0 |
| `amount` | 57000000.0 |
| `expense_account` | Cost of Goods Sold - NR |
| `cost_center` | Main - NR |
| `lead_time_date` | 2026-01-09 |

## Purchase Order  (356행)

| 필드 | 예시 |
| --- | --- |
| `name` | PO-25-0006 |
| `supplier` | BP-JP02 |
| `custom_approval_no` | AP-25-0006 |
| `custom_approval_submitted` | 2025-10-10 |
| `custom_approval_date` | 2025-10-13 |
| `custom_approver` | 구매팀장 |
| `custom_agency` | AG-01 |
| `supplier_name` | 미도리 케미칼(가상) |
| `transaction_date` | 2025-10-15 |
| `transaction_time` | 13:19:17.003048 |
| `schedule_date` | 2025-12-24 |
| `custom_supplier_confirmed_date` | 2025-12-27 |
| `custom_transport` | 해상 |
| `custom_note` | 에이전시 원산지증명 서류 보완 요청으로 통관 보류 |
| `currency` | KRW |
| `conversion_rate` | 1.0 |
| `buying_price_list` | Standard Buying |
| `price_list_currency` | KRW |
| `plc_conversion_rate` | 1.0 |
| `total_qty` | 175.0 |
| `base_total` | 133000000.0 |
| `base_net_total` | 133000000.0 |
| `total` | 133000000.0 |
| `net_total` | 133000000.0 |
| `grand_total` | 133000000.0 |
| `in_words` | KRW One Hundred And Thirty Three Million only. |
| `rounded_total` | 133000000.0 |
| `base_grand_total` | 133000000.0 |
| `base_in_words` | KRW One Hundred And Thirty Three Million only. |
| `base_rounded_total` | 133000000.0 |
| `apply_discount_on` | Grand Total |
| `supplier_group` | 레진 |
| `status` | To Bill |
| `advance_payment_status` | Not Initiated |
| `per_received` | 100.0 |
| `letter_head` | Company Letterhead - Grey |
| `language` | en |
| `party_account_currency` | KRW |

## Purchase Order Item  (356행)

| 필드 | 예시 |
| --- | --- |
| `name` | glbmmjrkkm |
| `parent` | PO-25-0018 |
| `item_code` | RS-14 |
| `supplier_part_no` | ZP-H33 |
| `item_name` | KrF 레진 PHS-C2 |
| `schedule_date` | 2026-01-21 |
| `item_group` | 레진 |
| `description` | BP-CN02(주) ZP-H33 520000원/kg |
| `qty` | 300.0 |
| `stock_uom` | Kg |
| `uom` | Kg |
| `conversion_factor` | 1.0 |
| `stock_qty` | 300.0 |
| `price_list_rate` | 540000.0 |
| `last_purchase_rate` | 540000.0 |
| `base_price_list_rate` | 540000.0 |
| `margin_type` | Amount |
| `margin_rate_or_amount` | 2100.0 |
| `rate_with_margin` | 540000.0 |
| `base_rate_with_margin` | 540000.0 |
| `rate` | 520000.0 |
| `amount` | 156000000.0 |
| `base_rate` | 520000.0 |
| `base_amount` | 156000000.0 |
| `stock_uom_rate` | 520000.0 |
| `net_rate` | 520000.0 |
| `net_amount` | 156000000.0 |
| `base_net_rate` | 520000.0 |
| `base_net_amount` | 156000000.0 |
| `warehouse` | WH-10 - NR |
| `actual_qty` | 50.0 |
| `company_total_stock` | 17.75 |
| `material_request` | MR-25-0018 |
| `material_request_item` | gl7iq911u2 |
| `received_qty` | 300.0 |
| `expense_account` | Cost of Goods Sold - NR |
| `cost_center` | Main - NR |
| `item_tax_rate` | {} |

## Purchase Receipt  (328행)

| 필드 | 예시 |
| --- | --- |
| `name` | GR-26-0001 |
| `supplier` | BP-JP02 |
| `supplier_name` | 미도리 케미칼(가상) |
| `supplier_delivery_note` | 022512-0081 |
| `posting_date` | 2026-01-02 |
| `custom_erp_entry_date` | 2026-01-02 |
| `custom_coa_attached` | 1 |
| `custom_supplier_lot` | 022512-0081 |
| `custom_po_ref` | PO-25-0006 |
| `posting_time` | 7:02:30 |
| `set_posting_time` | 1 |
| `currency` | KRW |
| `conversion_rate` | 1.0 |
| `buying_price_list` | Standard Buying |
| `price_list_currency` | KRW |
| `plc_conversion_rate` | 1.0 |
| `total_qty` | 87.5 |
| `base_total` | 66500000.0 |
| `base_net_total` | 66500000.0 |
| `total` | 66500000.0 |
| `net_total` | 66500000.0 |
| `grand_total` | 66500000.0 |
| `in_words` | KRW Sixty Six Million, Five Hundred Thousand only. |
| `rounded_total` | 66500000.0 |
| `base_grand_total` | 66500000.0 |
| `base_in_words` | KRW Sixty Six Million, Five Hundred Thousand only. |
| `base_rounded_total` | 66500000.0 |
| `apply_discount_on` | Grand Total |
| `status` | To Bill |
| `letter_head` | Company Letterhead - Grey |
| `language` | en |
| `remarks` | L 단위로 입고(발주는 kg). 발주 연결 못 함 — 발주번호 PO-26-0022 |

## Purchase Receipt Item  (328행)

| 필드 | 예시 |
| --- | --- |
| `name` | gofflc0n2h |
| `parent` | GR-26-0001 |
| `item_code` | RS-02 |
| `supplier_part_no` | MP-PHS 22 |
| `item_name` | KrF 레진 PHS-B |
| `description` | BP-JP02(주) MP-PHS 22 760000원/kg |
| `item_group` | 레진 |
| `received_qty` | 87.5 |
| `qty` | 87.5 |
| `uom` | Kg |
| `stock_uom` | Kg |
| `conversion_factor` | 1.0 |
| `received_stock_qty` | 87.5 |
| `stock_qty` | 87.5 |
| `price_list_rate` | 760000.0 |
| `base_price_list_rate` | 760000.0 |
| `margin_type` | Amount |
| `margin_rate_or_amount` | 2100.0 |
| `rate_with_margin` | 760000.0 |
| `base_rate_with_margin` | 760000.0 |
| `rate` | 760000.0 |
| `amount` | 66500000.0 |
| `base_rate` | 760000.0 |
| `base_amount` | 66500000.0 |
| `stock_uom_rate` | 760000.0 |
| `net_rate` | 760000.0 |
| `net_amount` | 66500000.0 |
| `base_net_rate` | 760000.0 |
| `base_net_amount` | 66500000.0 |
| `valuation_rate` | 760000.0 |
| `warehouse` | WH-10 - NR |
| `purchase_order` | PO-25-0006 |
| `schedule_date` | 2026-03-13 |
| `quality_inspection` | QI-26-0033 |
| `purchase_order_item` | glil9qvd62 |
| `serial_and_batch_bundle` | 0e054a7ae41c61b789b6 |
| `use_serial_batch_fields` | 1 |
| `batch_no` | RL-260102-RS02-01 |
| `expense_account` | Stock Received But Not Billed - NR |
| `item_tax_rate` | {} |
| `cost_center` | Main - NR |

## Batch  (707행)

| 필드 | 예시 |
| --- | --- |
| `name` | PL-250822-AD01-01 |
| `batch_id` | PL-250822-AD01-01 |
| `custom_supplier_lot` | 092508-0846 |
| `item` | PR-AD01 |
| `item_name` | NR-A 510 |
| `manufacturing_date` | 2025-08-22 |
| `batch_qty` | 29.0 |
| `stock_uom` | 병 |
| `expiry_date` | 2026-02-18 |
| `use_batchwise_valuation` | 1 |
| `reference_doctype` | Stock Reconciliation |
| `reference_name` | SR-OPEN-2026 |
| `supplier` | BP-JP02 |
| `description` | 제조일 미상(이관 lot) — 입고일로 기록 |

## Quality Inspection  (581행)

| 필드 | 예시 |
| --- | --- |
| `name` | QI-26-0001 |
| `report_date` | 2026-01-02 |
| `custom_requested_at` | 2025-12-19 15:00:00 |
| `custom_started_at` | 2025-12-22 09:00:00 |
| `custom_decided_at` | 2026-01-02 16:00:00 |
| `custom_erp_entry_at` | 2026-01-02 17:00:00 |
| `status` | Accepted |
| `child_row_reference` | golg14fqte |
| `inspection_type` | Incoming |
| `custom_category` | 입고 |
| `reference_type` | Stock Entry |
| `reference_name` | SE-IQC-26-0001 |
| `item_code` | RS-10 |
| `batch_no` | RL-251219-RS10-01 |
| `sample_size` | 1.0 |
| `item_name` | ArF 액침 레진 IM-A |
| `description` | BP-JP03(주) TK-IM8 1480000원/kg |
| `quality_inspection_template` | IQC-레진 |
| `manual_inspection` | 1 |
| `inspected_by` | sihyung@novaresist.com |
| `custom_inspector` | QC-3 |
| `custom_supplier` | BP-JP03 |
| `remarks` | 수분 규격 초과(재측정 동일), 공급사 통보 및 반품 |
| `letter_head` | Company Letterhead - Grey |

## Quality Inspection Reading  (2456행)

| 필드 | 예시 |
| --- | --- |
| `name` | gom3nogem0 |
| `parent` | QI-26-0001 |
| `specification` | 분자량 편차(Mw) |
| `status` | Accepted |
| `value` | 적합 |
| `numeric` | 1 |
| `manual_inspection` | 1 |
| `min_value` | -5.0 |
| `max_value` | 5.0 |
| `reading_value` | 확인 |
| `reading_1` | 0.27 |

## Work Order  (262행)

| 필드 | 예시 |
| --- | --- |
| `name` | WO-25-0073 |
| `production_item` | PR-AD04 |
| `bom_no` | BOM-PR-AD04-001 |
| `qty` | 128.0 |
| `custom_batch_size_l` | 500.0 |
| `custom_mix_tank` | MX-500-1 |
| `custom_wo_type` | 정규 |
| `custom_linked_so` | SO-26-0096 |
| `custom_fg_lot` | PL-260105-AD04-01 |
| `custom_yield_pct` | 97.0 |
| `custom_migration_note` | ERP 도입(2026-01-01) 전 2025년에 원재료 투입. 투입분은 재공 창고 기초재고로 이관. |
| `produced_qty` | 128.0 |
| `material_transferred_for_manufacturing` | 129.0 |
| `wip_warehouse` | WH-WIP - NR |
| `fg_warehouse` | WH-60 - NR |
| `skip_transfer` | 1 |
| `from_wip_warehouse` | 1 |
| `transfer_material_against` | Work Order |
| `planned_start_date` | 2025-12-30 08:00:00 |
| `custom_actual_start` | 2025-12-30 |
| `custom_actual_end` | 2026-01-05 |
| `custom_planned_end` | 2026-01-08 |
| `planned_end_date` | 2025-12-31 04:40:00 |
| `expected_delivery_date` | 2026-01-08 |
| `actual_start_date` | 2025-12-30 08:00:00 |
| `actual_end_date` | 2026-01-05 16:00:00 |
| `lead_time` | 9120.0 |
| `item_name` | NR-A 540 |
| `stock_uom` | Nos |
| `has_batch_no` | 1 |
| `update_consumed_material_cost_in_project` | 1 |
| `status` | Completed |

## Job Card  (1310행)

| 필드 | 예시 |
| --- | --- |
| `name` | PO-JOB00001 |
| `work_order` | WO-25-0073 |
| `operation` | 칭량 |
| `for_quantity` | 128.0 |
| `workstation` | 칭량실 |
| `custom_filter_lot` | MF-25K11 |
| `custom_crew` | 생산2조 |
| `stock_uom` | 병 |
| `production_item` | PR-AD04 |
| `bom_no` | BOM-PR-AD04-001 |
| `workstation_type` | 칭량 |
| `wip_warehouse` | WH-WIP - NR |
| `target_warehouse` | WH-60 - NR |
| `total_completed_qty` | 128.0 |
| `time_required` | 30.0 |
| `actual_start_date` | 2025-12-30 08:00:00 |
| `total_time_in_mins` | 60.0 |
| `actual_end_date` | 2025-12-30 09:00:00 |
| `item_name` | NR-A 540 |
| `status` | Completed |
| `operation_row_id` | 1 |
| `operation_id` | go4mma3bs1 |
| `sequence_id` | 1 |

## Job Card Time Log  (1220행)

| 필드 | 예시 |
| --- | --- |
| `name` | gqiupi5njm |
| `parent` | PO-JOB00001 |
| `from_time` | 2025-12-30 08:00:00 |
| `to_time` | 2025-12-30 09:00:00 |
| `time_in_mins` | 60.0 |
| `completed_qty` | 128.0 |

## Stock Entry  (1275행)

| 필드 | 예시 |
| --- | --- |
| `name` | SE-IQC-26-0001 |
| `stock_entry_type` | Material Transfer |
| `purpose` | Material Transfer |
| `set_posting_time` | 1 |
| `posting_date` | 2026-01-02 |
| `posting_time` | 7:03:00 |
| `work_order` | WO-25-0074 |
| `from_bom` | 1 |
| `use_multi_level_bom` | 1 |
| `bom_no` | BOM-PR-AD06-001 |
| `fg_completed_qty` | 129.0 |
| `from_warehouse` | WH-WIP - NR |
| `to_warehouse` | WH-60 - NR |
| `total_outgoing_value` | 110998520.0 |
| `total_incoming_value` | 110998520.0 |
| `letter_head` | Company Letterhead - Grey |
| `is_opening` | No |
| `remarks` | IQC 합격 QI-26-0001 |
| `total_amount` | 110998520.0 |

## Stock Entry Detail  (7140행)

| 필드 | 예시 |
| --- | --- |
| `name` | golg14fqte |
| `parent` | SE-IQC-26-0001 |
| `s_warehouse` | WH-10 - NR |
| `t_warehouse` | WH-20 - NR |
| `item_code` | RS-10 |
| `item_name` | ArF 액침 레진 IM-A |
| `is_finished_item` | 1 |
| `quality_inspection` | QI-26-0001 |
| `description` | BP-JP03(주) TK-IM8 1480000원/kg |
| `item_group` | 레진 |
| `qty` | 74.999 |
| `transfer_qty` | 74.999 |
| `uom` | Kg |
| `stock_uom` | Kg |
| `conversion_factor` | 1.0 |
| `basic_rate` | 1480000.0 |
| `valuation_rate` | 1480000.0 |
| `basic_amount` | 110998520.0 |
| `amount` | 110998520.0 |
| `use_serial_batch_fields` | 1 |
| `serial_and_batch_bundle` | 99710156be011e077993 |
| `batch_no` | RL-251219-RS10-01 |
| `expense_account` | Stock Adjustment - NR |
| `cost_center` | Main - NR |

## Non Conformance  (4행)

| 필드 | 예시 |
| --- | --- |
| `name` | NCR-26-001 |
| `subject` | [IQC 불합격] SV-01 RL-260601-SV01-01 |
| `custom_category` | IQC 불합격 |
| `custom_occurred_on` | 2026-06-05 |
| `custom_lot` | RL-260601-SV01-01 |
| `custom_item` | SV-01 |
| `custom_customer` | CU-A |
| `custom_cause` | 공급사 출하 전 수분 관리 미흡(공급사 회신) |
| `custom_closed_on` | 2026-06-29 |
| `procedure` | SOP-02 입고·IQC |
| `status` | Resolved |
| `details` | 수분 규격 초과(재측정 동일), 공급사 통보 및 반품 |
| `corrective_action` | 공급사 반품 및 대체 입고 요청 |

## Downtime Entry  (5행)

| 필드 | 예시 |
| --- | --- |
| `name` | DT-26-002 |
| `workstation` | FL-2 |
| `operator` | HR-EMP-00001 |
| `from_time` | 2026-10-12 08:00:00 |
| `to_time` | 2026-10-16 18:00:00 |
| `downtime` | 6360.0 |
| `stop_reason` | Unplanned machine maintenance |
| `remarks` | 필터 하우징 교체 |

## Sales Order  (93행)

| 필드 | 예시 |
| --- | --- |
| `name` | SO-25-0019 |
| `customer` | CU-A |
| `custom_urgent` | 1 |
| `custom_note` | 고객 긴급 요청 |
| `customer_name` | A사(가상, 메모리) |
| `order_type` | Sales |
| `transaction_date` | 2025-12-18 |
| `transaction_time` | 13:19:24.321888 |
| `delivery_date` | 2026-01-08 |
| `currency` | KRW |
| `conversion_rate` | 1.0 |
| `selling_price_list` | Standard Selling |
| `price_list_currency` | KRW |
| `plc_conversion_rate` | 1.0 |
| `total_qty` | 516.0 |
| `base_total` | 736440000.0 |
| `base_net_total` | 736440000.0 |
| `total` | 736440000.0 |
| `net_total` | 736440000.0 |
| `grand_total` | 736440000.0 |
| `in_words` | KRW Seven Hundred And Thirty Six Million, Four Hundred And F |
| `rounded_total` | 736440000.0 |
| `base_grand_total` | 736440000.0 |
| `base_in_words` | KRW Seven Hundred And Thirty Six Million, Four Hundred And F |
| `base_rounded_total` | 736440000.0 |
| `apply_discount_on` | Grand Total |
| `customer_group` | 메모리 |
| `territory` | All Territories |
| `status` | To Bill |
| `delivery_status` | Fully Delivered |
| `per_delivered` | 100.0 |
| `billing_status` | Not Billed |
| `advance_payment_status` | Not Requested |
| `amount_eligible_for_commission` | 736440000.0 |
| `letter_head` | Company Letterhead - Grey |
| `language` | en |

## Sales Order Item  (495행)

| 필드 | 예시 |
| --- | --- |
| `name` | gno0a2f0dn |
| `parent` | SO-25-0020 |
| `item_code` | PR-AD01 |
| `customer_item_code` | B-PR-AD01-05 |
| `is_stock_item` | 1 |
| `delivery_date` | 2026-01-05 |
| `item_name` | NR-A 510 |
| `description` | NR-A 510 (ArF 건식, 1갤런 병) |
| `item_group` | ArF 건식 |
| `qty` | 92.0 |
| `stock_uom` | 병 |
| `uom` | 병 |
| `conversion_factor` | 1.0 |
| `stock_qty` | 92.0 |
| `rate` | 1800000.0 |
| `amount` | 165600000.0 |
| `base_rate` | 1800000.0 |
| `base_amount` | 165600000.0 |
| `stock_uom_rate` | 1800000.0 |
| `grant_commission` | 1 |
| `net_rate` | 1800000.0 |
| `net_amount` | 165600000.0 |
| `base_net_rate` | 1800000.0 |
| `base_net_amount` | 165600000.0 |
| `valuation_rate` | 630000.0 |
| `gross_profit` | 107640000.0 |
| `warehouse` | WH-70 - NR |
| `actual_qty` | 145.0 |
| `company_total_stock` | 145.0 |
| `bom_no` | BOM-PR-AD01-001 |
| `projected_qty` | 145.0 |
| `delivered_qty` | 92.0 |
| `item_tax_rate` | {} |
| `transaction_date` | 2025-12-10 |
| `cost_center` | Main - NR |

## Delivery Note  (467행)

| 필드 | 예시 |
| --- | --- |
| `name` | DN-26-0001 |
| `customer` | CU-B |
| `customer_name` | B사(가상, 메모리) |
| `posting_date` | 2026-01-02 |
| `custom_erp_entry_date` | 2026-01-02 |
| `posting_time` | 7:04:15 |
| `set_posting_time` | 1 |
| `currency` | KRW |
| `conversion_rate` | 1.0 |
| `selling_price_list` | Standard Selling |
| `price_list_currency` | KRW |
| `plc_conversion_rate` | 1.0 |
| `total_qty` | 148.0 |
| `base_total` | 133200000.0 |
| `base_net_total` | 133200000.0 |
| `total` | 133200000.0 |
| `net_total` | 133200000.0 |
| `grand_total` | 133200000.0 |
| `in_words` | KRW One Hundred And Thirty Three Million, Two Hundred Thousa |
| `rounded_total` | 133200000.0 |
| `base_grand_total` | 133200000.0 |
| `base_in_words` | KRW One Hundred And Thirty Three Million, Two Hundred Thousa |
| `base_rounded_total` | 133200000.0 |
| `apply_discount_on` | Grand Total |
| `status` | To Bill |
| `installation_status` | Not Installed |
| `amount_eligible_for_commission` | 133200000.0 |
| `letter_head` | Company Letterhead - Grey |
| `language` | en |
| `customer_group` | 메모리 |
| `territory` | All Territories |

## Delivery Note Item  (658행)

| 필드 | 예시 |
| --- | --- |
| `name` | gov2dv73gr |
| `parent` | DN-26-0001 |
| `item_code` | PR-K04 |
| `item_name` | NR-K 440 |
| `customer_item_code` | B-PR-K04-01 |
| `description` | NR-K 440 (KrF, 1갤런 병) |
| `item_group` | KrF |
| `qty` | 13.0 |
| `stock_uom` | 병 |
| `uom` | 병 |
| `conversion_factor` | 1.0 |
| `stock_qty` | 13.0 |
| `rate` | 900000.0 |
| `amount` | 11700000.0 |
| `base_rate` | 900000.0 |
| `base_amount` | 11700000.0 |
| `stock_uom_rate` | 900000.0 |
| `grant_commission` | 1 |
| `net_rate` | 900000.0 |
| `net_amount` | 11700000.0 |
| `base_net_rate` | 900000.0 |
| `base_net_amount` | 11700000.0 |
| `incoming_rate` | 315000.0 |
| `warehouse` | WH-70 - NR |
| `against_sales_order` | SO-25-0020 |
| `so_detail` | gno77ucatu |
| `serial_and_batch_bundle` | 9c6b239ad84b9a58821d |
| `use_serial_batch_fields` | 1 |
| `batch_no` | PL-251114-K04-01 |
| `custom_remaining_shelf_life_days` | 131 |
| `custom_on_time` | 예 |
| `actual_qty` | 326.0 |
| `company_total_stock` | 326.0 |
| `expense_account` | Cost of Goods Sold - NR |
| `item_tax_rate` | {} |
| `cost_center` | Main - NR |

## NR Sales Forecast  (720행)

| 필드 | 예시 |
| --- | --- |
| `name` | gkm65691p4 |
| `version` | 2026-01 |
| `created_on` | 2026-01-05 |
| `customer` | CU-C |
| `item` | PR-AD04 |
| `target_month` | 2026-01 |
| `qty_bottles` | 88 |

## NR Production Plan  (240행)

| 필드 | 예시 |
| --- | --- |
| `name` | gl20m2392a |
| `plan_month` | 2026-03 |
| `sop_version` | S&OP-202603 |
| `item` | PR-K01 |
| `qty_bottles` | 163 |
| `plan_status` | 확정 |
