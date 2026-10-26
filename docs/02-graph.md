# 02. Graph — 영향 경로 추적

[목차](../README.md) \| 이전: [01. Ontology](01-ontology.md) \| 다음: [03. Data Agent](03-data-agent.md)

Ontology는 원본에 바인딩된 업무 모델이며 **Graph가 필수는 아닙니다.** 이 장에서는 선택적으로 인스턴스(원료 `RM-HA-120`, 처방 버전 `FV-CRM-01-03` …)를 노드·에지로 투영해 다단계 경로를 탐색합니다. **질의와 필터를 바꿔 진짜 영향 대상만 남기는** 연습입니다. Graph를 쓰지 않는 환경은 `02_answers`로 대상을 확인한 뒤 [03장](03-data-agent.md)의 Ontology·Lakehouse 경로로 진행할 수 있습니다.

## 시작 전 확인

- 01장에서 Ontology Agent로 생성·보강하고 5단계의 핵심 경로(`uses_material` 포함)와 `is_active` 속성 바인딩을 점검했습니다.
- 질의는 GQL(Graph Query Language)로 씁니다. 기본 형태는 `MATCH (노드:레이블)-[:관계]->(노드:레이블) WHERE … RETURN …`입니다.

## 1. Graph 만들기

1. `ont_cos`의 리본에서 **Manage graph**를 누릅니다. "Preparing graph..." 후 **Choose what to project**에서 엔터티와 관계의 **Status**가 모두 **Eligible**인지 확인합니다.
2. 핵심 모델의 엔터티 9개·관계 10개를 선택하고 **Continue** → **Materialize**를 누릅니다. 위쪽 탭에 `ont_cos_graph_`로 시작하는 Graph model이 열립니다. 완료 상태를 확인한 뒤 진행합니다. 데이터 크기뿐 아니라 용량·반영 대기에도 영향을 받습니다.

**확인할 결과:** 엔터티 9개·관계 10개가 Eligible이고, 작업 영역에 `ont_cos_graph_…` 항목이 생깁니다. 이 항목은 Ontology가 관리하므로 직접 고치지 않습니다.

확장 모델을 사용해도 모든 엔터티를 투영할 필요는 없습니다. 우선 핵심 경로만 선택합니다. **Ontology 바인딩 가능 여부와 Graph 투영 적격성은 별개**이며 현재 Graph 투영에는 키·매핑, 엔터티/관계별 단일 기반 테이블, 지원되는 Lakehouse/미러링 Delta 원본이 필요합니다. 다중 바인딩이나 의미 체계 모델을 쓴다고 모두 투영 가능한 것은 아닙니다.

## 2. 탐색 화면에서 경로 펼치기

1. `ont_cos`의 **Home**에서 **Explore graph**를 누릅니다.
2. `RawMaterial` 노드 중 `RM-HA-120`을 찾아 연결된 노드를 펼칩니다. `FormulaVersion` 노드에서 다시 `Product`·`DevProject`·`StabilityTest`로 펼칩니다.

**확인할 결과:** `RM-HA-120`에서 처방 버전 4개가 보이고, 그중 `FV-CRM-01-02`(폐기)에는 제품이 연결되어 있지 않습니다. 같은 성분의 `RM-HA-210`은 `alternative_to`로만 연결됩니다.

## 3. GQL로 질의하기

Graph model `ont_cos_graph_…`을 열고 질의 편집기(**Code editor** 또는 **Query**)에서 아래 질의를 하나씩 실행합니다. 각 질의 뒤의 **예상 결과**와 비교합니다.

**Q1. 이 원료를 쓰는 처방 버전은?**

``` gql
MATCH (fv:FormulaVersion)-[:uses_material]->(rm:RawMaterial)
WHERE rm.material_code = 'RM-HA-120'
RETURN fv.version_id, fv.formula_name, fv.status, fv.is_active
```

**예상 결과:** 4행 — `FV-CRM-01-02`(폐기, false), `FV-CRM-01-03`(현행), `FV-TON-02-01`(개발중), `FV-AMP-03-02`(현행).

**Q2. 업무 규칙 적용 — 폐기 버전 제외**

Q1의 `WHERE`에 `AND fv.is_active = true`를 **직접 추가해** 실행합니다.

**예상 결과:** 3행. `FV-CRM-01-02`가 빠집니다. 같은 Graph라도 **필터 하나가 영향 대상을 바꿉니다.**

**Q3. 제품과 생산 계획까지**

``` gql
MATCH (pp:ProductionPlan)-[:produces]->(p:Product)-[:made_with]->(fv:FormulaVersion)-[:uses_material]->(rm:RawMaterial)
WHERE rm.material_code = 'RM-HA-120' AND fv.is_active = true
RETURN pp.plan_id, pp.planned_date, p.product_id, p.product_name, p.market
```

**예상 결과:** 3행 — `PP-1101`(2026-11-25, `P-101`, KR), `PP-1102`(2026-12-02, `P-102`, CN), `PP-1103`(2027-01-20, `P-301`, KR).

**Q4. 개발 과제와 안정성 시험까지**

``` gql
MATCH (st:StabilityTest)-[:tests_version]->(fv:FormulaVersion)-[:uses_material]->(rm:RawMaterial),
      (st)-[:for_project]->(dp:DevProject)
WHERE rm.material_code = 'RM-HA-120' AND fv.is_active = true
RETURN dp.project_id, dp.project_name, st.test_id, st.batch_date, st.status
```

**예상 결과:** 1행 — `DP-2026-07` 하이드라 토너 출시, `ST-0711`, 배치일 2026-11-20, `예정`.

**Q5. 공급사 관점 — 같은 공급사의 원료를 쓰는 처방은? (도전)**

``` gql
MATCH (s:Supplier)<-[:supplied_by]-(rm:RawMaterial)<-[:uses_material]-(fv:FormulaVersion)
WHERE s.supplier_id = 'SUP-02' AND fv.is_active = true
RETURN rm.material_code, rm.material_name, fv.version_id
```

**예상 결과:** 5행 — `RM-HA-120` × 3개 버전, `RM-PHE-002`(페녹시에탄올) × 2개 버전(`FV-CRM-01-03`, `FV-AMP-03-02`). 같은 공급사에 문제가 번지면 수분 장벽 크림·시카 앰플은 원료 두 개가 동시에 걸립니다.

**Q6. 대체 원료 후보**

``` gql
MATCH (rm:RawMaterial)-[:alternative_to]->(alt:RawMaterial)-[:supplied_by]->(s:Supplier)
WHERE rm.material_code = 'RM-HA-120'
RETURN alt.material_code, alt.material_name, alt.lead_time_days, alt.cn_registration, s.supplier_name
```

**예상 결과:** 2행 — `RM-HA-210`(리드타임 10일, CN `필요`, 한빛바이오), `RM-HA-305`(42일, `완료`, Nordic Actives). 승인 상태(`승인`·`검토중`)는 관계에 속성이 없어 Graph에 나오지 않습니다. `02_answers` Q3에서 확인합니다.

## 4. 정답 Notebook과 비교

**예상 코드 실행 시간:** 약 1–3분(세션 준비 제외).

1. `02_answers`를 열고 기본 Lakehouse가 내 작업 영역의 `lh_cos`인지 확인합니다. 미연결 상태라면 [00장의 연결 절차](00-scenario.md#4-notebook에-기본-lakehouse-연결)에 따라 연결·저장합니다. 세션이 연결되어 있지 않다면 **Connect**로 시작합니다.
2. 연결 완료 후 **Run all**을 누르고 Q1–Q5 결과를 위 Graph 결과와 비교합니다.

**예상 출력:**

| 출력 | 행 수와 확인할 값 |
|---|---|
| Q1 처방 버전 | 4행, 폐기 버전 1개 포함 |
| Q2 영향 후보 | 4행, 제품 3개·개발 과제 1개 |
| Q3 대체 원료 | 2행, `RM-HA-210` 승인·`RM-HA-305` 검토중 |
| Q4 같은 공급사 원료 | 2행, `RM-PHE-002`를 쓰는 활성 처방 |
| Q5 필요일 대비 여유 | 4행, 여유일 8·15·64·3일 |
| Q6 영향 분석 | `ops.material_impact가 아직 없습니다` 안내 |

지연 반영 전 Q6 안내는 정상입니다. 이를 없애려고 `03_supply_change`를 먼저 실행하지 않습니다. 뒤에 나오는 DA 보조 조회 표는 03장에서 사용합니다.

**확인할 결과:** Graph의 Q2·Q3·Q4는 `02_answers`의 Q1·Q2와, Graph의 Q6은 Q3과 같은 대상을 가리킵니다. `02_answers`의 Q5는 **원료 필요일과 여유일**까지 계산합니다(지연 전: `PP-1101` 8일, `PP-1102` 15일, `PP-1103` 64일, `ST-0711` 3일).

> **토론 포인트:** Graph는 "무엇이 연결되어 있는가"를 빠르게 보여 줍니다. 그러나 "며칠 늦으면 문제인가" 같은 날짜 계산과 판정은 **명시적인 질의·Notebook**으로 하는 편이 정확하고 검증하기 쉽습니다. 4장의 `03_supply_change`가 그 역할을 합니다.

## 이 장의 완료 기준

- Graph model이 만들어졌고 Q1–Q4를 실행했습니다.
- `is_active` 필터로 폐기 버전이 빠지는 것을 확인했습니다.
- 영향 후보(생산 계획 3건, 안정성 시험 1건)를 `02_answers`와 비교했습니다.

## Troubleshooting

- **Manage graph**에서 **Ineligible**이면 키뿐 아니라 원본 종류·바인딩 수·지원 속성 형식을 확인합니다. [관리자 제약사항](../admin/preview-limitations.md)의 투영 적격성 항목을 참고합니다.
- 관계가 **Not mapped**로 나오면 관계 설정에서 양쪽 Property와 원본 열을 확인합니다.
- 질의가 0행이면 레이블·속성 이름의 대소문자를 Graph model의 스키마(노드·에지 목록)와 비교합니다. 예제는 엔터티 타입·관계 이름을 사용하며, 네임스페이스 접두사가 붙은 환경은 실제 레이블에 맞춰 수정합니다.
- `is_active`가 없다는 오류가 나면 01장 4단계의 보강과 5단계 점검을 마친 뒤 **Manage graph**로 다시 Materialize합니다. Graph는 Materialize 시점의 데이터 스냅샷입니다.
- 다른 핵심 경로는 있고 `is_active`만 누락된 경우 임시로 `WHERE fv.status <> '폐기'`를 쓸 수 있습니다. 타입·관계 자체가 없으면 필터로 대신할 수 없으므로 01장에서 보완하거나 `02_answers`로 확인합니다.
- 원본 ETA만 바뀌었다면 Graph 항목의 **… → Schedule → Refresh now**로 갱신합니다. 스키마 변경 후 재투영과 원본 데이터 새로 고침을 구분합니다.

## 공식 문서

- [Ontology에서 Graph 만들기와 제한 사항](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-graph)
- [GQL 언어 가이드](https://learn.microsoft.com/en-us/fabric/graph/gql-language-guide)
- [GQL 그래프 패턴 질의](https://learn.microsoft.com/en-us/fabric/graph/gql-graph-patterns)

## 다음 단계

[03. Data Agent](03-data-agent.md)에서 같은 질문을 자연어로 묻고 결과를 비교합니다.
