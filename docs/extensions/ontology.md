# 선택. Ontology 엔터티 확장 — 기본 과정 완료 후

[목차](../../README.md) \| 이전: [07. Purview 거버넌스](../07-purview.md)

**07장 Purview까지 기본 과정을 마친 뒤에만 진행하는 선택 실습입니다.** 생략해도 기본 과정의 완료에는 영향이 없습니다.

기존 `ont_cos`를 Ontology Agent와 보강해 **원료 → 로트·검사·재고 → 제조소**, **대체 원료 → 공급사 자격·시장 등록**, **생산 계획 → 배치·설비**, **변경 건 → 처방 평가·담당 팀**을 연결합니다. 별도 Ontology를 만드는 것이 기본 경로가 아니며, 핵심 엔터티·ID·키·관계·바인딩은 보존합니다.

| 프로필 | 원본 CSV/테이블 | 엔터티 | 관계 | 항목 |
|---|---:|---:|---:|---|
| 기본 과정 완성(참고) | 핵심 11 | 9 | 10 | 07장까지 사용한 `ont_cos` |
| 선택 확장 완성(참고) | 총 28 | 26 | 40 | 같은 `ont_cos`에 추가·보강 |

테이블과 엔터티는 일대일이 아닙니다. 핵심의 `formula_line`, `material_alternative`는 관계 매핑용이며, 확장 엔터티 17개는 각자 한 테이블에 바인딩됩니다.

## 시작 전 확인

- 00~07장을 마쳤고 `oa_cos` 감시를 중지했습니다.
- 기존 `ont_cos`와 `da_cos`를 사용하며, **00장의 첫 적재에서 직접 만든** `lh_cos.gold`의 추가 17개 포함 테이블 28개가 남아 있습니다.
- 확장 전 모델의 정의·이름·키·관계와 기존 질문의 응답·생성 SQL을 기록해 비교 기준을 남깁니다. 04장에서 공급 일정이 바뀌었으므로 **현재 데이터 상태에서** 기준 응답을 확보합니다.
- 확장 데이터는 기준일 **2026-11-02의 고정 스냅샷**이며 핵심 Notebook이 갱신하거나 동기화하지 않습니다.
- 추가 테이블이 없다면 관리자에게 확인하고 이번 선택 실습은 보류합니다. **`01_prepare_data`를 다시 실행하지 않습니다.** 기본 과정의 공급 상태·승인 결과를 초기화하거나 직접 테넌트·배포 설정을 바꾸지 않습니다.

## 추가 엔터티와 바인딩

원본 스키마는 모두 `gold`입니다. 핵심 9개 정의는 [01장](../01-ontology.md)의 표와 같습니다.

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

## 실습 1. Ontology Agent로 기존 모델 확장

1. 기존 `ont_cos`를 열고 Ontology Agent의 모드가 **Plan**인지 확인합니다.
2. 다음 질문으로 추가 업무 범위와 원본을 조사합니다.

    ```text
    기본 과정에서 만든 현재 ont_cos를 유지하면서 다음 업무 질문을 지원하도록 확장안을 제안해줘.
    원본은 lh_cos.gold의 핵심 11개와 추가 17개 테이블이야. ops, Files, Eventhouse, SQL Serving DB는 범위에서 제외해.
    - RM-HA-120의 로트별 검사 결과, 사용 가능 상태, 재고 수량과 보관 위치는 어떻게 다른가?
    - CN 제품 P-102에 대체 원료를 쓰려면 공급사 자격·대체 승인·제품 등록·시장별 원료 등록을 각각 어떻게 확인해야 하는가?
    - 이 원료를 쓰는 생산 후보 계획은 어떤 제조 배치·라인·제조소와 연결되는가?
    - 기존 변경 검토 건에서 처방별 평가와 담당 팀·조직은 어떻게 연결되는가?
    필요한 엔터티·속성·관계·원본 바인딩과 질문별 설계 근거를 제안해줘.
    기존 엔터티·ID·키·속성·관계·바인딩은 보존하고 이미 있는 대상은 재사용해.
    추가 원본의 실제 열과 행으로 키·관계·바인딩을 검증하고, 오류나 미확인 값은 명시해줘.
    재고를 핵심 일정 영향 계산에서 자동 차감하거나 원료 등록 상태를 양방향 동기화하는 설계는 하지 마.
    gold.change_request와 change_assessment는 기존 검토 이력이며 ops의 승인 요청과 다르다는 맥락을 포함해줘.
    추가·유지 항목, 검증 결과와 변경 미리 보기를 보여줘.
    ```

3. 위의 참고 엔터티·원본·키 표와 비교해 질문에 필요한 대상이 연결되는지 봅니다. **26개·40개는 참고 설계의 수치이지 AI 출력 개수를 맞추는 목표가 아닙니다.** 기존 핵심 경로 보존과 실제 원본 연결을 우선합니다.
4. 검토한 변경안에 미해결 문제가 없으면 **Act**로 전환해 `검토한 추가·보강 변경안만 현재 ont_cos에 적용해줘. 기존 핵심 정의와 원본 데이터, 다른 Fabric 항목은 바꾸지 마.`를 보냅니다.
5. **Plan**으로 돌아가 저장된 정의·바인딩과 실제 행을 확인합니다. 추가 이름·방향이 참고와 다르면 필요한 경로를 대조하고, 뒤의 GQL도 실제 스키마에 맞춥니다.

**확인할 결과:** 별도 완성 모델로 교체하지 않고 기존 `ont_cos`에 새 업무 경로가 추가됩니다. 기본 과정의 원본과 승인·SQL 상태는 그대로이며, 모델 크기 자체가 실제 테넌트의 정확도·성능 검증을 뜻하지는 않습니다.

## 실습 2. Lakehouse SQL로 업무 경로 확인

`lh_cos`의 **SQL analytics endpoint**에서 [extended-queries.sql](../../fabric/sql/extended-queries.sql)의 QX1–QX4를 각각 실행합니다. `sqldb_cos`의 Serving 스키마에서 실행하는 SQL이 아닙니다. endpoint 동기화 후 `gold` 확장 테이블이 보이는지 먼저 확인합니다. 각 질의의 대상 ID·상태·수량·담당 조직을 기록한 뒤 아래 결과와 대조합니다.

<details>
<summary>결과 대조 — 직접 질의를 실행한 뒤 펼치기</summary>

| 질문 | 기대 결과 |
|---|---|
| QX1. 같은 `RM-HA-120` 로트의 검사·재고·위치는 같은가? | 2행. `LOT-120-A` / `GR-01` / 적합·사용가능·가용 **8kg**. `LOT-120-B` / `GR-02` / 부적합·격리 **5kg**. 모두 인천 원료 창고·인천 제조소·생산운영 조직 |
| QX2. CN 제품 `P-102`에 승인된 대체 원료를 바로 쓸 수 있는가? | 1행. 제품 등록 완료·`RM-HA-210` 공급사 자격 승인과 별개로 **원료 CN 등록은 필요** |
| QX3. 원료를 쓰는 생산 후보 계획은 어느 설비에 연결되는가? | 3행. `PP-1101 → BATCH-01 → 인천`, `PP-1102 → BATCH-02 → 오산`, `PP-1103 → BATCH-03 → 인천` |
| QX4. 기존 변경 건의 처방 평가는 누가 담당하는가? | 3행. `CA-01` 구매·생산계획/대기, `CA-02` 처방개발/진행중, `CA-03` 등록검토/등록확인 |

</details>

**확인할 결과:** 개수만 늘어난 모델이 아니라 업무 경로를 따라 ID·상태·담당 조직을 찾을 수 있습니다. 공급사 자격 ≠ 대체 승인 ≠ 원료 등록 ≠ 제품 등록이며, 보관 중인 재고 ≠ 바로 사용할 수 있는 재고입니다.

## 실습 3. 확장된 Ontology 문맥으로 같은 질문 검증

1. 기존 `da_cos`에서 연결된 `ont_cos`의 문맥을 **Refresh**하고 `lh_cos` 원본과 preview runtime을 확인합니다.
2. 다음을 기존 Agent instructions에 추가합니다. 기본 과정의 일정 영향 판정 지침은 유지합니다.

    ```text
    확장된 ont_cos의 의미와 바인딩을 참고해 lh_cos.gold에 SQL로 질의합니다.
    기준일은 2026-11-02입니다. 재고는 로트 검사·disposition·availability를 구분합니다.
    공급사 자격·대체 승인·제품 등록·시장별 원료 등록을 서로 대체하지 않습니다.
    change_request/change_assessment는 기존 검토 이력이며 ops 승인 실행 결과가 아닙니다.
    핵심 공급 지연 영향은 일정 기준으로 판단하며, 확장 재고를 자동 차감하지 않습니다.
    표에 ID·상태·관련 원본을 표시하고 확인되지 않는 승인이나 등록을 추정하지 않습니다.
    ```

3. QX1–QX4의 질문을 자연어로 묻고 생성 SQL·원본·결과를 위 정답과 비교합니다. 답이 다르면 생성 질의의 조인·필터를 검사하며 정답으로 간주하지 않습니다.
4. 확장 직전에 기록한 기존 질문도 다시 실행해 같은 데이터 상태의 기준 응답과 비교합니다. 03장 초기 상태의 답과 04장 지연 반영 후의 답을 혼동하지 않습니다.

현재 Data Agent는 Ontology 안의 일부 엔터티만 선택해 노출하지 못하므로 새 문맥 전체가 질문 해석에 영향을 줄 수 있습니다. 기존 질문의 원본·질의·결과까지 다시 확인하며, 소량 예제의 성공을 대규모 데이터의 성능·질의 정확도 보장으로 해석하지 않습니다.

## 실습 4. 필요한 경로만 Graph로 투영 (선택)

Lakehouse·에이전트 경로를 먼저 확인한 뒤 Graph 적격성을 검사합니다. `ont_cos`의 **Manage graph**에서 `RawMaterial → MaterialLot ← InventoryBalance → Warehouse → ManufacturingSite` 경로와 필요한 관계를 선택해 투영합니다. 전체 26개를 한 번에 투영할 필요는 없습니다. 기존 Graph의 데이터 새로 고침만으로 새 모델 경로까지 추가되었다고 간주하지 않습니다.

```gql
MATCH (rm:RawMaterial)<-[:lot_of_material]-(lot:MaterialLot)
      <-[:inventory_of_lot]-(stock:InventoryBalance)-[:stored_in]->(w:Warehouse)
      -[:warehouse_at_site]->(site:ManufacturingSite)
WHERE rm.material_code = 'RM-HA-120'
RETURN lot.lot_id, lot.disposition, stock.qty_kg, stock.availability, w.warehouse_name, site.site_name
```

**기대 결과:** QX1과 같은 두 로트·8kg 가용/5kg 격리·인천 제조소. 검사 결과·발주를 더 보고 싶으면 관련 엔터티와 관계를 추가로 투영합니다. 투영할 수 없다면 원본·키·바인딩을 확인하고 [02장의 Troubleshooting](../02-graph.md#troubleshooting)을 참고합니다.

## 핵심 실습과의 경계

기존 공급 지연 영향은 **일정 기준**이며 재고 할당·실사용 수량·안전 재고·수율 계산을 하지 않습니다. 확장 재고가 존재한다고 핵심의 영향 3건을 자동 상쇄하지 않습니다. 실제 수량 기반 대응에는 소요량·할당·생산 소비 모델이 더 필요합니다.

`GoodsReceipt`는 `PO-5501`의 과거 부분 입고, 핵심의 `purchase_order.eta`는 남은 공급 일정입니다. `LOT-210-A`는 기초 재고로 입고 이력 수집 범위 밖입니다. `MaterialRegistration`의 CN 상태는 핵심 `raw_material.cn_registration`과 같은 초기값이지만 자동 양방향 동기화하지 않습니다.

`gold.change_request/change_assessment`는 **사전에 존재하는 별도 검토 이력**입니다. Teams 승인으로 새로 생성하는 `ops.review_request/action_log`나 SQL Serving 결과로 오해하지 않습니다. 확장은 핵심 Notebook의 계산·쓰기 범위를 변경하지 않으며 기존 영향 대상 `PP-1101`, `PP-1102`, `ST-0711`을 유지합니다.

## 선택 실습 마무리

기존 핵심 정의를 보존하면서 추가한 업무 경로와, 확장 전후 질의 결과를 기록합니다. 기본 과정으로 돌아가 재실행하려면 확장된 문맥이 남아 있음을 확인합니다. 항목 정리는 관리자에게 요청하고 [목차](../../README.md)로 돌아갑니다.
