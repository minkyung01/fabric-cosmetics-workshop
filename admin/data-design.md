# 데이터 설계

[목차](../README.md) \| [관리자 가이드](README.md)

Contoso 코스메틱 연구소의 **가상 데이터**입니다. 실제 회사·공급사·처방과 관계없습니다. 기준일은 **2026-11-02**입니다.

## 테이블

CSV는 `data/`(UTF-8, BOM 없음)에 있고 `01_prepare_data`가 `gold.<table>`로 만듭니다.

| 테이블 | 행 | 키 | 주요 열 |
|---|---:|---|---|
| `ingredient` | 6 | `ingredient_id` | `inci_name`, `korean_name`, `function` |
| `supplier` | 4 | `supplier_id` | `supplier_name`, `country`, `risk_grade` |
| `raw_material` | 8 | `material_code` | `ingredient_id`, `supplier_id`, `lead_time_days`, `unit_price_krw`, `cn_registration` |
| `material_alternative` | 3 | `alt_id` | `material_code` → `alt_material_code`, `approval_status`, `condition_note` |
| `formula_version` | 5 | `version_id` | `formula_id`, `version_no`, `status`(현행·개발중·폐기), `is_active`, `approved_date` |
| `formula_line` | 15 | `line_id` | `version_id`, `material_code`, `pct_wt`(배합비, 영업 비밀) |
| `product` | 4 | `product_id` | `version_id`, `market`(KR·CN), `sales_status` |
| `dev_project` | 1 | `project_id` | `version_id`, `stage`, `owner`, `target_launch` |
| `stability_test` | 1 | `test_id` | `version_id`, `project_id`, `batch_date`, `status` |
| `production_plan` | 4 | `plan_id` | `product_id`, `planned_date`, `qty_ea` |
| `purchase_order` | 6 | `po_id` | `material_code`, `supplier_id`, `order_date`, `eta`, `status` |

실습 중 생기는 `ops` 테이블:

| 테이블 | 만드는 Notebook | 내용 |
|---|---|---|
| `ops.material_impact` | `03_supply_change` | 이벤트별 수요 대상, 필요일, 여유일, 영향 여부, 대체 제안 |
| `ops.review_request` | `nb_apply_review` | 영향 대상별 원료 변경 검토 요청 |
| `ops.action_log` | `nb_apply_review` | 승인 조치 이력 |

Eventhouse `eh_cos`의 `MaterialSupplyEvent`는 이벤트 상태 이력(`open` → `review_requested`)을 담습니다. 열 정의는 [04장](../docs/04-operations-agent.md)에 있습니다.

## Ontology

| 엔터티 | 원본 | 키 |
|---|---|---|
| Ingredient | `ingredient` | `ingredient_id` |
| Supplier | `supplier` | `supplier_id` |
| RawMaterial | `raw_material` | `material_code` |
| FormulaVersion | `formula_version` | `version_id` |
| Product | `product` | `product_id` |
| DevProject | `dev_project` | `project_id` |
| StabilityTest | `stability_test` | `test_id` |
| ProductionPlan | `production_plan` | `plan_id` |
| PurchaseOrder | `purchase_order` | `po_id` |

| 관계 | 방향 | 원본 | 기본 모델 |
|---|---|---|---|
| `has_ingredient` | RawMaterial → Ingredient | `raw_material` | 있음 |
| `supplied_by` | RawMaterial → Supplier | `raw_material` | 있음 |
| `uses_material` | FormulaVersion → RawMaterial | `formula_line` | **없음 (01장에서 추가)** |
| `made_with` | Product → FormulaVersion | `product` | 있음 |
| `develops` | DevProject → FormulaVersion | `dev_project` | 있음 |
| `tests_version` | StabilityTest → FormulaVersion | `stability_test` | 있음 |
| `for_project` | StabilityTest → DevProject | `stability_test` | 있음 |
| `produces` | ProductionPlan → Product | `production_plan` | 있음 |
| `orders` | PurchaseOrder → RawMaterial | `purchase_order` | 있음 |
| `alternative_to` | RawMaterial → RawMaterial | `material_alternative` | **없음 (01장에서 추가)** |

기본 모델에는 `FormulaVersion.is_active`, `RawMaterial.cn_registration` 속성도 없습니다. `tools/build_ontology.py`가 `fabric/ont_cos_base`와 `fabric/ont_cos_reference`를 만듭니다.

## 업무 규칙

- 공급 지연은 **원료 코드** 단위로 판단합니다(같은 성분 `ING-HA`라도 원료 `RM-HA-120`·`RM-HA-210`·`RM-HA-305`는 다름).
- 영향 분석은 `is_active = true`인 처방 버전만 봅니다. `FV-CRM-01-02`는 폐기입니다.
- 원료 필요일 = 생산 계획일 또는 안정성 시험 배치일(`예정`만) − QC 리드타임 7일.
- 여유일 = 필요일 − 입고 예정일. **여유일 < 0이면 영향 대상**입니다.
- 대체 원료는 `approval_status = 승인`만 제안합니다. 입고 예정일은 기준일 + 리드타임입니다. CN 시장 제품은 `cn_registration = 완료`여야 바로 쓸 수 있습니다.

## 시나리오와 정답

공급사 `SUP-02` Aqua Derm Chemicals가 `RM-HA-120`(`PO-5501`, 입고 예정 2026-11-10)을 **35일 지연** → 2026-12-15.

| 대상 | 연결 | 필요일 | 지연 전 여유 | 지연 후 여유 | 영향 | 제안 |
|---|---|---|---:|---:|---|---|
| `PP-1101` | `P-101` 수분 장벽 크림, KR | 2026-11-18 | 8 | -27 | 예 | RM-HA-210 대체 사용 검토 |
| `PP-1102` | `P-102` 수분 장벽 크림(중국), CN | 2026-11-25 | 15 | -20 | 예 | RM-HA-210 CN 등록 필요 — 등록 또는 일정 조정 검토 |
| `PP-1103` | `P-301` 시카 앰플, KR | 2027-01-13 | 64 | 29 | 아니오 | |
| `ST-0711` | `DP-2026-07` 하이드라 토너 | 2026-11-13 | 3 | -32 | 예 | RM-HA-210 대체 사용 검토 |

- `PP-1104`(`P-401` 데일리 로션)는 `RM-HA-120`을 쓰지 않습니다.
- 대체 원료: `RM-HA-210`(승인, `SUP-01`, 리드타임 10일 → 11-12 입고, CN 등록 필요), `RM-HA-305`(검토중, 42일), `ALT-003`(`RM-PHE-002` → `RM-GLY-001`)은 반려.

`02_answers` 정답:

| 질문 | 정답 |
|---|---|
| Q1 `RM-HA-120`을 쓰는 처방 버전 | 4개: `FV-CRM-01-02`(폐기), `FV-CRM-01-03`, `FV-TON-02-01`, `FV-AMP-03-02` |
| Q2 영향 후보 제품·과제 | `P-101`, `P-102`, `P-301`, `DP-2026-07` |
| Q3 대체 원료 | `RM-HA-210` 승인 / `RM-HA-305` 검토중 |
| Q4 같은 공급사 위험 | `SUP-02`의 `RM-PHE-002`도 `FV-CRM-01-03`, `FV-AMP-03-02`에 사용 |
| Q5 지연 전 여유일 | `PP-1101` 8, `PP-1102` 15, `PP-1103` 64, `ST-0711` 3 |
| Q6 지연 후 영향 | `ops.material_impact` 영향 3건(-27, -20, -32) |

이벤트: `SUP-20261102-RM-HA-120-r1`, `impacted_count = 3`.
