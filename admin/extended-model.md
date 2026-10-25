# 선택 확장 — 26개 엔터티로 업무 경로 탐색

[목차](../README.md) \| [관리자 가이드](README.md) \| [미리 보기 제약·호환성](preview-limitations.md)

핵심 9개 엔터티를 유지하면서 **원료 → 로트·검사·재고 → 제조소**, **대체 원료 → 공급사 자격·시장 등록**, **생산 계획 → 배치·설비**, **변경 건 → 처방 평가·담당 팀**을 연결합니다. 기본 과정의 대체물이 아니라 준비된 환경에서 선택하는 확장 실습입니다.

| 프로필 | 원본 CSV/테이블 | 엔터티 | 관계 | 항목 |
|---|---:|---:|---:|---|
| 핵심 시작 | 11 | 9 | 8 | `ont_cos` |
| 핵심 완성 | 11 | 9 | 10 | `ont_cos` 또는 참고 정의 |
| 선택 확장 완성 | 28 | 26 | 40 | 별도 `ont_cos_extended` |

테이블과 엔터티는 일대일이 아닙니다. 핵심의 `formula_line`, `material_alternative`는 관계 매핑용이며, 확장 엔터티 17개는 각자 한 테이블에 바인딩됩니다. 아래 이름은 자동 생성 정의의 엔터티 타입명입니다.

## 관리자 준비

**먼저 핵심 환경을 리허설합니다.** 새/기존 Ontology 경험과 REST 정의의 호환성을 [사전 점검](preview-limitations.md#2-새-ontology-경험과-api-배포-정의의-호환성)한 뒤 다음 옵션을 사용합니다.

```powershell
python admin/provision.py --capacity <capacity-id> --participants p001 --extended-ontology --dry-run
python admin/provision.py --capacity <capacity-id> --participants p001 --extended-ontology
```

핵심 `ont_cos`를 그대로 두고 별도 완성 모델을 추가합니다. 원본 CSV 11개에 `data/extended`의 17개를 더해 **같은 `Files/workshop/data` 폴더**에 업로드합니다. `01_prepare_data`는 확장 파일이 모두 있을 때 28개 테이블을 생성하며 일부만 있으면 오류로 중지합니다.

이미 준비한 작업 영역은 **`--update-notebooks`도 지정**해 새 준비 Notebook을 가져와야 합니다. 다시 실행하면 기본 `reset_ops = True`에 따라 승인 결과가 초기화되므로 **승인 실습 전**에 준비합니다. 기존 Ontology 항목은 자동 덮어쓰기·마이그레이션하지 않습니다. `--skip-prepare`를 지정했다면 `01_prepare_data`를 직접 실행해 확장 테이블을 확인한 후 바인딩을 사용합니다.

수동 준비는 두 CSV 폴더의 파일을 모두 같은 목적지에 올리고 `01_prepare_data`를 실행한 뒤 `fabric/ont_cos_extended`를 별도 항목으로 배포합니다. API 정의가 맞지 않는 새 경험에서는 아래 표와 `tools/build_ontology.py`의 `EXTENDED_RELATIONSHIPS`를 기준으로 수동 생성합니다. 생성에 실패한 모델을 완료로 표시하지 않습니다.

확장 옵션을 뺐다고 이전 확장 파일·테이블이 자동 삭제되지는 않습니다. 핵심만으로 리허설할 때는 새 작업 영역을 사용합니다. 추가 데이터는 기준일 **2026-11-02의 고정 스냅샷**이며 핵심 Notebook이 갱신하거나 동기화하지 않습니다.

## 추가 엔터티와 바인딩

원본 스키마는 모두 `gold`입니다. 핵심 9개 정의는 [01장](../docs/01-ontology.md)의 표와 같습니다.

| 엔터티 | 테이블 | 키 | 업무 구분 |
|---|---|---|---|
| Organization | `organization` | `organization_id` | 연구개발·생산운영 조직 |
| Team | `team` | `team_id` | 주관/평가 담당 팀 |
| SupplierQualification | `supplier_qualification` | `qualification_id` | 시장별 공급사 자격 평가 |
| MaterialSpec | `material_spec` | `spec_id` | 원료별 품질 규격 |
| MaterialLot | `material_lot` | `lot_id` | 사용가능·격리 로트 |
| GoodsReceipt | `goods_receipt` | `receipt_id` | 발주의 부분 입고 이력 |
| QualityInspection | `quality_inspection` | `inspection_id` | 로트 검사 결과 |
| Warehouse | `warehouse` | `warehouse_id` | 제조소 내 창고 |
| InventoryBalance | `inventory_balance` | `balance_id` | 로트·창고별 잔량 |
| ManufacturingSite | `manufacturing_site` | `site_id` | 제조소 |
| ProductionLine | `production_line` | `line_id` | 제조소의 생산 라인 |
| ManufacturingBatch | `manufacturing_batch` | `batch_id` | 계획·처방·라인의 연결 |
| Market | `market` | `market_code` | KR·CN 시장 |
| MaterialRegistration | `material_registration` | `registration_id` | 시장별 원료 등록 |
| ProductRegistration | `product_registration` | `registration_id` | 시장별 제품 등록 |
| ChangeRequest | `change_request` | `change_id` | 기존 변경 검토 건 |
| ChangeAssessment | `change_assessment` | `assessment_id` | 처방별 검토 담당과 상태 |

## 실습 1. Lakehouse SQL로 업무 경로 확인

`lh_cos`의 **SQL analytics endpoint**에서 [extended-queries.sql](../fabric/sql/extended-queries.sql)의 QX1–QX4를 각각 실행합니다. `sqldb_cos`의 Serving 스키마에서 실행하는 SQL이 아닙니다. endpoint 동기화 후 `gold` 확장 테이블이 보이는지 먼저 확인합니다.

| 질문 | 기대 결과 |
|---|---|
| QX1. 같은 `RM-HA-120` 로트의 검사·재고·위치는 같은가? | 2행. `LOT-120-A` / `GR-01` / 적합·사용가능·가용 **8kg**. `LOT-120-B` / `GR-02` / 부적합·격리 **5kg**. 모두 인천 원료 창고·인천 제조소·생산운영 조직 |
| QX2. CN 제품 `P-102`에 승인된 대체 원료를 바로 쓸 수 있는가? | 1행. 제품 등록 완료·`RM-HA-210` 공급사 자격 승인과 별개로 **원료 CN 등록은 필요** |
| QX3. 원료를 쓰는 생산 후보 계획은 어느 설비에 연결되는가? | 3행. `PP-1101 → BATCH-01 → 인천`, `PP-1102 → BATCH-02 → 오산`, `PP-1103 → BATCH-03 → 인천` |
| QX4. 기존 변경 건의 처방 평가는 누가 담당하는가? | 3행. `CA-01` 구매·생산계획/대기, `CA-02` 처방개발/진행중, `CA-03` 등록검토/등록확인 |

**확인할 결과:** 개수만 늘어난 모델이 아니라 업무 경로를 따라 ID·상태·담당 조직을 찾을 수 있습니다. 공급사 자격 ≠ 대체 승인 ≠ 원료 등록 ≠ 제품 등록이며, 보관 중인 재고 ≠ 바로 사용할 수 있는 재고입니다.

## 실습 2. Ontology 문맥으로 같은 질문 검증

1. `ont_cos_extended`에서 엔터티 **26개**, 관계 **40개**, 원본·키·속성 바인딩을 확인합니다.
2. `da_cos_extended`를 별도로 만들고 확장 Ontology를 추가합니다. 연결된 `lh_cos` 원본과 preview runtime을 확인합니다. 기본 `da_cos`를 확장 모델로 교체하지 않습니다.
3. 다음을 Agent instructions에 추가합니다.

    ```text
    ont_cos_extended의 의미와 바인딩을 참고해 lh_cos.gold에 SQL로 질의합니다.
    기준일은 2026-11-02입니다. 재고는 로트 검사·disposition·availability를 구분합니다.
    공급사 자격·대체 승인·제품 등록·시장별 원료 등록을 서로 대체하지 않습니다.
    change_request/change_assessment는 기존 검토 이력이며 ops 승인 실행 결과가 아닙니다.
    표에 ID·상태·관련 원본을 표시하고 확인되지 않는 승인이나 등록을 추정하지 않습니다.
    ```

4. QX1–QX4의 질문을 자연어로 묻고 생성 SQL·원본·결과를 위 정답과 비교합니다. Ontology 편집 직후에는 문맥을 **Refresh**합니다. 답이 다르면 생성 질의의 조인·필터를 검사하며 정답으로 간주하지 않습니다.

현재 Data Agent는 Ontology 안의 일부 엔터티만 선택해 노출하지 못합니다. 모델을 나눠 비교하는 이유이며, 소량 예제의 성공이 대규모 데이터의 성능·질의 정확도 보장은 아닙니다.

## 실습 3. 필요한 경로만 Graph로 투영 (선택)

Lakehouse·에이전트 경로를 먼저 확인한 뒤 Graph 적격성을 검사합니다. 전체 26개를 한 번에 만들기보다 `RawMaterial → MaterialLot ← InventoryBalance → Warehouse → ManufacturingSite` 경로와 필요한 관계만 선택합니다.

```gql
MATCH (rm:RawMaterial)<-[:lot_of_material]-(lot:MaterialLot)
      <-[:inventory_of_lot]-(stock:InventoryBalance)-[:stored_in]->(w:Warehouse)
      -[:warehouse_at_site]->(site:ManufacturingSite)
WHERE rm.material_code = 'RM-HA-120'
RETURN lot.lot_id, lot.disposition, stock.qty_kg, stock.availability, w.warehouse_name, site.site_name
```

**기대 결과:** QX1과 같은 두 로트·8kg 가용/5kg 격리·인천 제조소. 검사 결과·발주를 더 보고 싶으면 관련 엔터티와 관계를 추가로 투영합니다. 지원 원본·키·단일 바인딩·갱신 주기의 제약은 [관리자 문서](preview-limitations.md)를 확인합니다.

## 핵심 실습과의 경계

기존 공급 지연 영향은 **일정 기준**이며 재고 할당·실사용 수량·안전 재고·수율 계산을 하지 않습니다. 확장 재고가 존재한다고 핵심의 영향 3건을 자동 상쇄하지 않습니다. 실제 수량 기반 대응에는 소요량·할당·생산 소비 모델이 더 필요합니다.

`GoodsReceipt`는 `PO-5501`의 과거 부분 입고, 핵심의 `purchase_order.eta`는 남은 공급 일정입니다. `LOT-210-A`는 기초 재고로 입고 이력 수집 범위 밖입니다. `MaterialRegistration`의 CN 상태는 핵심 `raw_material.cn_registration`과 같은 초기값이지만 자동 양방향 동기화하지 않습니다.

`gold.change_request/change_assessment`는 **사전에 존재하는 별도 검토 이력**입니다. Teams 승인으로 새로 생성하는 `ops.review_request/action_log`나 SQL Serving 결과로 오해하지 않습니다. 확장은 핵심 Notebook의 계산·쓰기 범위를 변경하지 않으며 기존 영향 대상 `PP-1101`, `PP-1102`, `ST-0711`을 유지합니다.
