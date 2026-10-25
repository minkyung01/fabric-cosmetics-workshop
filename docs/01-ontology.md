# 01. Ontology — 데이터에 연결된 업무 모델 완성

[목차](../README.md) \| 이전: [00. 시나리오와 미션](00-scenario.md) \| 다음: [02. Graph](02-graph.md)

관리자가 배포한 기본 Ontology `ont_cos`에는 엔터티 9개와 관계 8개가 있습니다. 그런데 이 모델로는 **"이 원료를 쓰는 처방은?"에 답할 수 없습니다.** 처방 버전과 원료를 잇는 관계가 빠져 있기 때문입니다. 이 장에서는 빠진 관계와 업무 규칙을 채워, 2장에서 영향 경로를 끝까지 따라갈 수 있게 합니다.

**Ontology는 용어집만이 아닙니다.** `RawMaterial`이라는 단어에 뜻을 붙이는 것에서 끝나지 않고, `material_code`로 업무 대상을 식별하고 원본 열에 바인딩하며 `uses_material`로 처방과 연결합니다. Graph·에이전트가 같은 연결과 맥락을 재사용하는 기반입니다. 다만 설명에 쓴 규칙이 자동 실행되거나 접근 권한을 대신하지는 않습니다. 이 키트의 여유일 계산·판정은 명시적인 질의와 Notebook에서 실행합니다.

**Graph 없이도 Lakehouse에 직접 바인딩할 수 있습니다.** 이 키트의 엔터티·관계는 `lh_cos.gold` Delta 테이블에 바인딩됩니다. Ontology는 업무 맥락을 제공하고 Data Agent가 원본에 SQL을 실행하는 경로와, 필요한 대상을 Graph로 투영해 GQL로 탐색하는 경로를 구분합니다. Ontology 캔버스의 관계 그림이 곧 인스턴스 Graph 저장소는 아닙니다.

| 모델 요소 | 이 실습에서 확인하는 것 | 다음 Lesson에서 쓰이는 곳 |
|---|---|---|
| 엔터티·키 | `RawMaterial.material_code`는 구매 단위 원료의 식별자 | Graph에서 `RM-HA-120` 인스턴스 탐색 |
| 속성·데이터 바인딩 | `is_active`를 `gold.formula_version.is_active`에 연결 | 폐기 버전 제외 필터와 에이전트 질의 |
| 관계·관계 바인딩 | `uses_material`을 `formula_line`에 연결 | 원료 → 처방 → 제품·시험의 다단계 영향 경로 |
| 업무 맥락 | 필요일·대체 승인·CN 등록 조건을 공유 | Data Agent 지침과 명시적 계산을 대조 |

이 실습에서는 규칙을 설명·지침으로 표현하고 정확한 계산은 Notebook에서 실행합니다. 별도의 Ontology Rules 기능을 구성하는 과정은 아닙니다. 메뉴나 기능이 보이지 않으면 현재 작업 영역의 지원 여부를 관리자에게 확인합니다.

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

## 5. Plan 모드로 Ontology에 질문하기

**Plan은 변경 계획만 세우는 모드가 아닙니다.** 현재 Ontology의 의미·구조·바인딩을 설명하거나, 연결된 원본 데이터를 읽어 질문에 답할 수도 있습니다. **질문·답변을 위해 Act로 전환할 필요는 없습니다.** Plan은 Ontology나 작업 영역을 변경하지 않으며, 모델 변경을 적용할 때만 제안을 검토한 뒤 Act를 사용합니다.

1. `ont_cos`의 **Ontology agent**를 열고 입력창 아래 모드가 **Plan**인지 확인합니다.
2. 먼저 모델 자체에 대해 질문합니다.

    ```text
    이 Ontology에서 Ingredient와 RawMaterial은 어떻게 다른지 설명해줘.
    RawMaterial의 키와 원본 테이블, FormulaVersion과 연결되는 uses_material 관계의 매핑 테이블·열도 알려줘.
    현재 정의와 바인딩을 근거로 답하고, Ontology나 작업 영역은 변경하지 마.
    ```

    **기대 결과:** 성분과 구매 단위 원료의 차이, `RawMaterial`의 키 `material_code`와 원본 `gold.raw_material`, `uses_material`의 매핑 `gold.formula_line.version_id → material_code`를 설명합니다. 아직 관계를 추가하지 않았다면 현재 모델에는 없다고 답해야 하며, 설명만 듣기 위해 변경안을 적용하지 않습니다.

3. 같은 Plan 모드에서 바인딩된 데이터에 질문합니다.

    ```text
    RM-HA-120을 사용하는 모든 처방 버전을 version_id, status, is_active와 함께 표로 보여줘.
    어떤 원본에 어떤 질의를 실행했는지도 보여줘. 확인할 수 없는 값은 추정하지 마.
    Ontology나 작업 영역은 변경하지 마.
    ```

    **기대 결과:** `FV-CRM-01-02`(폐기, false), `FV-CRM-01-03`(현행, true), `FV-TON-02-01`(개발중, true), `FV-AMP-03-02`(현행, true)의 **4행**입니다. `02_answers` Q1과 비교합니다.

**확인할 결과:** Plan 상태를 유지한 채 모델 설명과 데이터 질의 응답을 확인하고, 엔터티·관계·바인딩은 바뀌지 않았습니다. 이 키트에서는 Graph를 만들지 않아도 Lakehouse에 **SQL**로 질의할 수 있습니다. Graph가 있는 관계 탐색에는 GQL을 사용할 수 있으므로, 응답의 실제 실행 원본·질의·결과를 확인합니다. Plan은 읽기 전용이지 데이터 접근 권한을 우회하는 모드는 아닙니다.

Ontology Agent도 질문에 답할 수 있습니다. 03장의 **Data Agent는 별도 에이전트 항목**에 Ontology 문맥과 원본을 연결해 질문하는 경험이며, Ontology Agent는 현재 Ontology 안에서 설명·질의·모델 개선을 함께 수행한다는 차이가 있습니다.

## 이 장의 완료 기준

- `uses_material`, `alternative_to` 관계가 있고 관계는 모두 10개입니다.
- `FormulaVersion.is_active`, `RawMaterial.cn_registration` 속성이 바인딩되어 있습니다.
- 업무 규칙 3개가 엔터티 설명에 들어 있습니다.
- Ontology Agent의 **Plan**으로 모델 설명과 데이터 질의 응답을 확인하고, 질문·답변과 **Act**의 모델 변경 적용을 구분할 수 있습니다.
- 엔터티 이름만 바꾸는 것과 키·속성·관계를 원본 데이터에 바인딩하는 것의 차이를 설명할 수 있습니다.

## 선택 확장 — 26개 엔터티로 업무 경로 넓히기

별도 `ont_cos_extended`가 준비되어 있다면 [확장 실습](extensions/ontology.md)에서 로트·검사·재고, 공급사 자격과 시장별 등록, 생산설비·변경 검토 담당을 탐색합니다. 핵심 9개 엔터티에 17개를 추가한 **26개 엔터티·40개 관계**, 원본은 **28개 테이블**입니다. `formula_line`과 `material_alternative`는 관계 매핑 테이블이므로 테이블 수와 엔터티 수는 다릅니다.

핵심 실습은 `ont_cos`에서 그대로 진행합니다. 확장 모델 전체를 Graph로 만들 필요는 없으며 먼저 Lakehouse SQL로 결과를 확인합니다. 큰 모델을 추가한 것 자체가 실제 테넌트의 정확도·성능 검증을 뜻하지는 않습니다.

## Troubleshooting

- **자기 자신을 가리키는 관계(`RawMaterial → RawMaterial`)를 만들 수 없는 경우:** `alternative_to`는 건너뜁니다. 대체 원료 질문은 2장 Q6 대신 `02_answers`의 Q3로 확인합니다.
- **에이전트가 기존 관계를 다시 만들거나 이름을 바꾸려는 경우:** Plan 단계에서 `기존 항목은 유지하고 중복 생성하지 마.`를 덧붙여 다시 요청합니다.
- **모델 구성을 완료하기 어려운 경우:** 완성 참고 모델로 이어서 진행할 수 있는지 관리자에게 요청합니다. 현재 `ont_cos`를 임의로 삭제하거나 다시 배포하지 않습니다.
- 브라우저를 새로 고치면 에이전트 대화는 사라지지만, 적용한 엔터티 타입과 관계는 남습니다.

## 공식 문서

- [Ontology agent 사용·Plan/Act 모드](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent)
- [관계 타입과 매핑 테이블](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-relationship-types)
- [Ontology의 업무 맥락·데이터 바인딩·규칙](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview)

## 다음 단계

[02. Graph](02-graph.md)에서 선택적으로 인스턴스 경로를 탐색합니다. Graph를 사용하지 않는 구성은 [03. Data Agent](03-data-agent.md)로 바로 이동해 Ontology·Lakehouse 경로를 실습합니다.
