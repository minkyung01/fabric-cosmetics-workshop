# 데이터 설계

[목차](../README.md) \| [관리자 가이드](README.md)

Caldova 코스메틱 연구소의 **가상 데이터**입니다. Microsoft의 가상 제약 회사 Caldova를 화장품 R&D 시나리오로 각색했으며 실제 회사·공급사·처방과 관계없습니다. 기준일은 **2026-11-02**입니다.

## 테이블

관리용 원본은 `data/`의 CSV(UTF-8, BOM 없음)이며 빌드 시 준비 코드에 포함됩니다. 관리자는 각 작업 영역에 Notebook 5개를 가져옵니다. 참가자는 00장에서 Lakehouse 생성과 기본 연결을 마친 뒤 `01_prepare_data`로 `gold.<table>`을 만듭니다. 참가자의 파일 업로드나 실행 중 외부 파일 다운로드는 없습니다.

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

준비 Notebook은 `purchase_order`에 `original_eta`(date)를 추가해 최초 ETA를 보존합니다. `03_supply_change`는 이 값을 기준으로 지연을 계산하므로 재실행해도 지연이 누적되지 않습니다. 다른 업무 열·키·관계는 관리용 CSV와 같습니다.

선택 확장 원본은 `data/extended/`에 있으며 준비 코드에도 포함됩니다. 참가자가 00장 첫 실행 전에 `include_extended = True`로 설정하면 **첫 적재에서 총 28개 테이블을 직접 생성**합니다. 기존 Ontology에 연결하는 [엔터티 확장 선택 실습](../docs/extensions/ontology.md)은 **07장 Purview 완료 이후**에만 진행합니다. 준비 절차는 [확장 환경 준비](extended-model.md)에 있습니다. 핵심 영향 계산에는 추가하지 않습니다.

| 테이블 | 행 | 키 | 주요 열 |
|---|---:|---|---|
| `organization` | 2 | `organization_id` | `organization_name` |
| `team` | 3 | `team_id` | `organization_id`, `team_name` |
| `supplier_qualification` | 3 | `qualification_id` | `supplier_id`, `market_code`, `status`, `valid_until` |
| `material_spec` | 3 | `spec_id` | `material_code`, `spec_name` |
| `material_lot` | 3 | `lot_id` | `material_code`, `supplier_id`, `spec_id`, `disposition` |
| `goods_receipt` | 2 | `receipt_id` | `po_id`, `lot_id`, `received_date`, `qty_kg` |
| `quality_inspection` | 3 | `inspection_id` | `lot_id`, `spec_id`, `result`, `inspected_date` |
| `warehouse` | 2 | `warehouse_id` | `site_id`, `warehouse_name` |
| `inventory_balance` | 4 | `balance_id` | `lot_id`, `warehouse_id`, `qty_kg`, `availability` |
| `manufacturing_site` | 2 | `site_id` | `organization_id`, `site_name` |
| `production_line` | 2 | `line_id` | `site_id`, `line_name` |
| `manufacturing_batch` | 3 | `batch_id` | `plan_id`, `line_id`, `version_id`, `status` |
| `market` | 2 | `market_code` | `market_name` |
| `material_registration` | 4 | `registration_id` | `material_code`, `market_code`, `status` |
| `product_registration` | 3 | `registration_id` | `product_id`, `market_code`, `status` |
| `change_request` | 2 | `change_id` | `material_code`, `project_id`, `team_id`, `status` |
| `change_assessment` | 3 | `assessment_id` | `change_id`, `version_id`, `team_id`, `status` |

실습 중 생기는 `ops` 테이블:

| 테이블 | 만드는 Notebook | 내용 |
|---|---|---|
| `ops.material_impact` | `03_supply_change` | 이벤트별 수요 대상, 필요일, 여유일, 영향 여부, 대체 제안 |
| `ops.review_request` | `nb_apply_review` | 영향 대상별 원료 변경 검토 요청 |
| `ops.action_log` | `nb_apply_review` | 승인 조치 이력 |

Eventhouse `eh_cos`의 `MaterialSupplyEvent`는 이벤트 상태 이력(`open` → `review_requested`)을 담습니다. 열 정의는 [04장](../docs/04-operations-agent.md)에 있습니다.

SQL database `sqldb_cos`의 업무 데이터는 [06장](../docs/06-serving-db.md)에서 생성합니다.

| 객체 | 원본·관리 주체 | 내용 |
|---|---|---|
| `serving.review_request` | `04_publish_serving`이 승인 요청으로 게시 SQL 생성 → SQL DB에서 실행 | `request_id` 기본 키, 이벤트·대상 유일 키, 담당 팀, 여유일, 제안, `요청됨/검토중` 상태 |
| `serving.workflow_history` | `serving.usp_start_review` | SQL 상태 변경 전후·로그인·UTC 시간 |

배합비는 게시하지 않습니다. Lakehouse `ops.review_request`는 승인 시점 스냅샷, SQL은 게시 후 업무 상태를 소유합니다. 재게시에는 신규 ID만 추가하여 SQL 상태를 보존합니다. SQL의 상태는 Lakehouse·Eventhouse로 자동 역동기화되지 않습니다. `requested_by`는 Notebook 실행 사용자로서 Teams 승인자 증빙이 아니며, SQL 이력의 `changed_by`는 상태를 바꾼 SQL 로그인입니다.

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

기본 과정은 참가자가 빈 `ont_cos`에서 Agent로 생성·보강합니다. 아래는 후속 GQL과 맞추기 위한 핵심 참고 설계이며 초기부터 관리자 배포로 제공하지 않습니다.

| 관계 | 방향 | 원본 | 질문 범위 |
|---|---|---|---|
| `has_ingredient` | RawMaterial → Ingredient | `raw_material` | 초안: 원료의 의미 |
| `supplied_by` | RawMaterial → Supplier | `raw_material` | 초안: 공급사 |
| `uses_material` | FormulaVersion → RawMaterial | `formula_line` | 초안: 처방의 사용 원료 |
| `made_with` | Product → FormulaVersion | `product` | 초안: 제품의 처방 |
| `develops` | DevProject → FormulaVersion | `dev_project` | 보강: 개발 과제 |
| `tests_version` | StabilityTest → FormulaVersion | `stability_test` | 보강: 시험 대상 |
| `for_project` | StabilityTest → DevProject | `stability_test` | 보강: 시험의 개발 과제 |
| `produces` | ProductionPlan → Product | `production_plan` | 보강: 생산 일정 |
| `orders` | PurchaseOrder → RawMaterial | `purchase_order` | 초안: 발주·입고 예정일 |
| `alternative_to` | RawMaterial → RawMaterial | `material_alternative` | 보강: 대체 후보 |

보강 단계에서는 `FormulaVersion.is_active`, `RawMaterial.cn_registration`과 업무 맥락도 추가·검증합니다. Agent가 이미 바인딩한 항목은 중복 생성하지 않습니다. 참고 초안은 성분·원료·공급사·처방·제품·발주 6개와 위 초안 관계 5개, 보강 후 핵심 참고는 9개·10개입니다. 실제 Agent 출력은 달라질 수 있으며 필요한 경로·원본 매핑으로 판정합니다.

`tools/build_ontology.py`는 이전 과정의 중간 참고 `fabric/ont_cos_base`(9개/8개, 두 속성 누락), 완성 복구용 `fabric/ont_cos_reference`, 선택 확장 `fabric/ont_cos_extended`를 만듭니다. **중간 참고 모델은 이번 생성 실습의 초안 산출물이나 기본 배포가 아닙니다.** 확장은 완성 핵심 9개 엔터티·10개 관계를 보존하고 17개 엔터티·30개 관계를 더합니다. 원본·키 표, 업무 경로·정답·핵심과의 경계는 [확장 실습](../docs/extensions/ontology.md)에 있습니다.

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

03장에서는 Data Agent 생성·지침 입력을 체험한 뒤 **Ontology Agent의 Plan 모드에서 DA01–DA07 핵심 7문항**을 진행합니다. 현재 Preview 환경의 Ontology 메타데이터 연계 제약을 Data Agent의 전반적인 원본 조회 불가로 확대하지 않습니다. `02_answers`에도 같은 질문·번호·순서의 Markdown과 실행 셀이 있으며, 실행 출력에도 질문을 표시합니다. 앞의 Q1–Q6은 01–02장용으로 유지합니다. 질문과 공통 프롬프트·정답 기준은 [03장](../docs/03-data-agent.md)에 있습니다.

| 추가 검증 | 기준 |
|---|---|
| DA01 전체·활성 처방 | 전체 4개와 포함 3개·제외 1개를 같은 표에서 확인. 개발중인 `FV-TON-02-01`도 활성으로 포함 |
| DA02 경계 | `ST-0711` 필요일 11-13. 입고 11-13은 여유 0·일정 지연 없음이나 추가 여유 없음·주의, 11-14는 -1·일정 1일 지연. `is_impacted`는 일정 지연만 판정하며 주의 상태와 구분 |
| DA03 일정·CN 비교 | `PP-1102` 필요일 11-25. `RM-HA-210`은 11-12 입고·여유 13일/CN 등록 필요, `RM-HA-305`는 12-14 입고·여유 -19일/CN 등록 완료. 두 조건을 모두 충족하지 않으며 사용 승인은 별도 |
| DA04 공급사 경로 | 같은 공급사의 `RM-PHE-002`가 활성 처방을 통해 제품 3개로 이어짐. 실제 발주 `PO-5505`의 ETA와 연결상 위험을 구분 |
| DA05 입고 가정 | 11-10 → 12-15, QC 7일. `PP-1101`/`PP-1102`/`PP-1103`/`ST-0711` 여유 8/15/64/3 → -27/-20/29/-32 |
| DA06 통합 | 생산 2건·시험 1건을 원 발주·공급사와 조인한 3행. 시험 시장은 NULL 유지. 저장된 ETA와 가정 ETA는 별도 열. 일정 조정·원료 확보 검토 대상이며 대체 후보·승인은 조회하지 않음 |
| DA07 발주 검토 기한 | 리드타임 10일. 최종 발주일과 기준일 대비 남은 일수는 `ST-0711` 11-03/1일 → `PP-1101` 11-08/6일 → `PP-1102` 11-15/13일. CN 등록 검토와 사용 승인·공정 검증은 별도이며 추가 검증 기간을 포함한 기한은 아님 |

가정 계산은 **SELECT만 실행**하고 원본 ETA·QC·`ops`를 변경하지 않습니다. DA02·DA03·DA05–DA07은 질문에 명시한 날짜·QC를 사용하므로 현재 원본의 지연 반영 여부와 독립적으로 비교합니다. DA01–DA07은 `gold`의 10개 테이블 범위에서 확인하며 `material_alternative`를 요구하지 않습니다. 앞의 Q3 등 다른 실습에서 쓰는 원본 테이블은 삭제하지 않습니다. 모델에 속성이 안 보이는 것과 원본 데이터 부재를 구분하며, Plan에서 질문을 검증하다 임의로 모델을 변경하지 않습니다. 복수 시스템 간 교차 원본 지원이나 일반 정확도 수치를 입증하는 벤치마크가 아닙니다.

이벤트: `SUP-20261102-RM-HA-120-r1`, `impacted_count = 3`.
