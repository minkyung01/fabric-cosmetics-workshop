# 01. Ontology — 업무 의미와 관계 보완

[목차](../README.md) \| 이전: [00. 시나리오와 미션](00-scenario.md) \| 다음: [02. Graph](02-graph.md)

관리자가 배포한 기본 Ontology `ont_cos`에는 엔터티 9개와 관계 8개가 있습니다. 그런데 이 모델로는 **"이 원료를 쓰는 처방은?"에 답할 수 없습니다.** 처방 버전과 원료를 잇는 관계가 빠져 있기 때문입니다. 이 장에서는 빠진 관계와 업무 규칙을 채워, 2장에서 영향 경로를 끝까지 따라갈 수 있게 합니다.

## 시작 전 확인

- 00장에서 `gold` 테이블 11개와 `ont_cos`를 확인했습니다.
- Ontology는 **엔터티 타입**(업무 대상), **관계**(대상 사이의 연결), **데이터 바인딩**(엔터티·관계를 원본 테이블과 잇는 설정)으로 구성됩니다. `RawMaterial`은 엔터티 타입이고, `gold.raw_material`의 각 행(`RM-HA-120` 등)은 인스턴스입니다.

## 1. 기본 모델 살펴보기

1. 작업 영역에서 `ont_cos`를 엽니다.
2. 왼쪽 **Explorer**의 **Entity Types**와 가운데 캔버스를 봅니다.

| 엔터티 타입 | 원본 테이블 (`gold`) | 키 | 의미 |
|---|---|---|---|
| `Ingredient` | `ingredient` | `ingredient_id` | 성분(INCI). 여러 원료가 같은 성분을 가질 수 있음 |
| `RawMaterial` | `raw_material` | `material_code` | 구매 단위 원료. 같은 성분이라도 공급사·규격이 다르면 다른 원료 |
| `Supplier` | `supplier` | `supplier_id` | 공급사 |
| `FormulaVersion` | `formula_version` | `version_id` | 처방의 특정 버전(현행·개발중·폐기) |
| `Product` | `product` | `product_id` | 판매 제품. 시장(KR·CN)별로 다른 ID |
| `DevProject` | `dev_project` | `project_id` | 신제품 개발 과제 |
| `StabilityTest` | `stability_test` | `test_id` | 처방 버전의 안정성 시험 |
| `ProductionPlan` | `production_plan` | `plan_id` | 제품 생산 계획 |
| `PurchaseOrder` | `purchase_order` | `po_id` | 원료 발주 |

**확인할 결과:** 캔버스 아래 상태 표시줄에 엔터티 9개, 관계 8개가 보입니다. `RawMaterial`과 `FormulaVersion` 사이에 선이 없습니다.

> **토론 포인트:** "성분"과 "원료"를 구분하지 않으면 무엇이 문제일까요? 공급 지연은 **원료**(`RM-HA-120`) 단위로 생기지만, 같은 성분(소듐하이알루로네이트)의 다른 원료 `RM-HA-210`은 영향이 없습니다.

## 2. 빠진 관계 추가 — 처방 버전이 사용하는 원료

처방 배합 정보는 `gold.formula_line`(처방 버전 ID, 원료 코드, 배합비)에 있습니다. 이 테이블을 매핑 테이블로 쓰는 관계를 추가합니다.

**방법 A — Ontology agent (권장)**

1. 리본의 Ontology agent 창을 열고 **Plan** 모드를 고릅니다.
2. 아래 요청을 보냅니다.

    ``` text
    gold.formula_line을 매핑 테이블로 써서 FormulaVersion → RawMaterial 관계 uses_material을 추가해줘.
    원본 열은 version_id(FormulaVersion 키)와 material_code(RawMaterial 키)야.
    또 gold.material_alternative를 매핑 테이블로 써서 RawMaterial → RawMaterial 관계 alternative_to를 추가해줘.
    원본 열은 material_code(원래 원료)와 alt_material_code(대체 원료)야.
    다른 엔터티·키·관계·바인딩은 바꾸지 말고, RM-HA-120에서 처방 버전 4개와 대체 원료 2개로 이어지는지 실제 행으로 검증해줘.
    ```

3. 제안과 검증 결과를 검토한 뒤 **Act** 모드로 바꿔 `검토한 계획대로 적용해줘. 다른 항목은 바꾸지 마.`를 보냅니다.

**방법 B — 직접 추가**

1. **Explorer**에서 `FormulaVersion`을 고르고 **Configure** → 오른쪽 **Manage relationships** → 관계 추가를 누릅니다.
2. 이름 `uses_material`, Origin `FormulaVersion`(Property `version_id`), Target `RawMaterial`(Property `material_code`), 매핑 테이블 `gold.formula_line`을 지정하고 저장합니다.
3. 같은 방법으로 `RawMaterial` → `RawMaterial` 관계 `alternative_to`(매핑 테이블 `gold.material_alternative`, 열 `material_code` → `alt_material_code`)를 추가합니다.

**확인할 결과:** 캔버스에 `FormulaVersion → RawMaterial`(`uses_material`)과 `RawMaterial → RawMaterial`(`alternative_to`) 관계가 보이고, 관계는 모두 10개입니다.

## 3. 업무 규칙을 속성으로 추가

영향 분석에는 두 가지 업무 규칙이 필요합니다. 원본 테이블에는 열이 있지만 기본 모델에는 바인딩되어 있지 않습니다.

| 규칙 | 엔터티 | 추가할 속성 (원본 열) |
|---|---|---|
| 폐기된 처방 버전은 영향 분석에서 제외한다 | `FormulaVersion` | `is_active` (Boolean) — 현행·개발중이면 true |
| CN 판매 제품에는 CN 등록이 완료된 원료만 대체 사용할 수 있다 (사내 가상 기준) | `RawMaterial` | `cn_registration` (String) — `완료`·`필요` |

1. Ontology agent(**Plan**)에 아래 요청을 보냅니다.

    ``` text
    FormulaVersion에 gold.formula_version.is_active 열을 Boolean 속성 is_active로, RawMaterial에 gold.raw_material.cn_registration 열을 String 속성 cn_registration으로 바인딩해줘.
    그리고 아래 업무 규칙을 해당 엔터티 타입의 설명 끝에 한국어로 덧붙여줘. 이름, 키, 다른 속성, 관계는 바꾸지 마.
    - FormulaVersion: 영향 분석은 is_active = true(현행·개발중)인 버전만 대상으로 한다. 폐기 버전은 제외한다.
    - RawMaterial: 원료 필요일 = 생산 계획일 또는 안정성 시험 배치일 − QC 리드타임 7일. 필요일보다 입고 예정일이 늦으면 영향 대상이다.
    - RawMaterial: 대체 원료는 material_alternative.approval_status가 '승인'인 것만 사용할 수 있고, CN 판매 제품에는 cn_registration이 '완료'인 원료만 쓸 수 있다.
    ```

2. 검토 후 **Act** 모드에서 적용합니다. UI에서 직접 하려면 엔터티의 **Configure**에서 속성을 추가하고 원본 열을 연결합니다.

**확인할 결과:** `FormulaVersion`의 **Configure**에 `is_active` 속성이 `is_active` 열에, `RawMaterial`에 `cn_registration`이 바인딩되어 있습니다. 설명은 실행되는 코드가 아니라 **Data Agent가 참고하는 업무 설명**입니다. 정확한 계산은 4장의 `03_supply_change`가 합니다.

## 4. 점검

1. `RawMaterial`의 **Configure** → **Manage relationships**에서 `uses_material`을 엽니다.
2. Origin `FormulaVersion`의 Property가 `version_id`, Target `RawMaterial`의 Property가 `material_code`인지 확인하고 **Cancel**을 누릅니다.

**확인할 결과:** 엔터티 9개, 관계 10개. 모든 엔터티에 키가 있습니다(키가 없는 엔터티는 Graph에 올라가지 않습니다).

## 이 장의 완료 기준

- `uses_material`, `alternative_to` 관계가 있고 관계는 모두 10개입니다.
- `FormulaVersion.is_active`, `RawMaterial.cn_registration` 속성이 바인딩되어 있습니다.
- 업무 규칙 3개가 엔터티 설명에 들어 있습니다.

## Troubleshooting

- **자기 자신을 가리키는 관계(`RawMaterial → RawMaterial`)를 만들 수 없는 경우:** `alternative_to`는 건너뜁니다. 대체 원료 질문은 2장 Q6 대신 `02_answers`의 Q3로 확인합니다.
- **에이전트가 기존 관계를 다시 만들거나 이름을 바꾸려는 경우:** Plan 단계에서 `기존 항목은 유지하고 중복 생성하지 마.`를 덧붙여 다시 요청합니다.
- **시간 안에 끝내지 못한 경우:** 관리자에게 완성 모델로 교체를 요청합니다(`provision.py --reference-ontology`, `fabric/ont_cos_reference`). 기존 `ont_cos`를 지운 뒤 다시 배포합니다.
- 브라우저를 새로 고치면 에이전트 대화는 사라지지만, 적용한 엔터티 타입과 관계는 남습니다.

## 공식 문서

- [Ontology agent 사용·Plan/Act 모드](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent)
- [관계 타입과 매핑 테이블](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-relationship-types)

## 다음 단계

[02. Graph](02-graph.md)에서 Ontology로 Graph를 만들고 `RM-HA-120`의 영향 경로를 따라갑니다.
