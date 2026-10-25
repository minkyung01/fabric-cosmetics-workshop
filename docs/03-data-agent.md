# 03. Data Agent — 같은 문제를 자연어로 묻기

[목차](../README.md) \| 이전: [02. Graph](02-graph.md) \| 다음: [04. Operations Agent](04-operations-agent.md)

2장에서 직접 경로를 따라가 찾은 영향 대상을, 이번에는 **자연어로 질문**해 찾습니다. Data Agent는 **Graph model**(미리 보기, GQL 생성)과 **Ontology**(미리 보기, 업무 정의를 참고해 원본에 대한 질의 생성)를 데이터 원본으로 쓸 수 있습니다. 참가자가 만든 관계 모델을 AI가 활용하는 모습을 확인하는 것이 목적입니다.

## 시작 전 확인

- 2장의 Graph model `ont_cos_graph_…`이 만들어져 있습니다.
- 테넌트에서 Data agent와 Copilot·Azure OpenAI 설정이 켜져 있어야 합니다(관리자 준비 사항).
- Data agent 하나에 데이터 원본은 최대 5개까지 연결할 수 있습니다.

## 1. Data Agent 만들고 원본 연결

1. 작업 영역에서 **+ New item** → **Data agent**를 고르고 이름을 `da_cos`로 만듭니다.
2. **Add data source**(또는 **Add data**)에서 `ont_cos`(Ontology)를 추가합니다.
3. 같은 방법으로 Graph model `ont_cos_graph_…`을 추가합니다.

**확인할 결과:** 왼쪽 **Explorer**에 원본 2개(Ontology, Graph model)가 보입니다.

## 2. 에이전트 지침 입력

**Agent instructions**에 아래 지침을 붙여 넣습니다.

``` text
Contoso 코스메틱 연구소의 원료 변경 영향 분석을 돕습니다. 답은 한국어로 씁니다.

용어
- 성분(Ingredient)과 원료(RawMaterial)는 다릅니다. 공급 지연은 원료 코드(material_code) 단위로 판단합니다.
- 처방 버전(FormulaVersion)의 status는 현행·개발중·폐기입니다. is_active = true인 버전만 영향 분석 대상입니다.

영향 대상 찾기
- 원료 → 처방 버전(uses_material) → 제품(made_with) → 생산 계획(produces), 처방 버전 → 안정성 시험(tests_version) → 개발 과제(for_project) 경로를 따라갑니다.
- 원료 필요일 = 생산 계획일 또는 안정성 시험 배치일 − 7일(QC 리드타임). 입고 예정일이 필요일보다 늦으면 영향 대상입니다.
- 대체 원료는 alternative_to 관계로 찾고, CN 시장 제품에는 cn_registration이 '완료'인 원료만 제안합니다.

답변 원칙
- 영향 대상은 ID와 이름을 함께 표로 보여 줍니다.
- 어떤 경로·조건으로 찾았는지 한 줄로 설명합니다.
- 확인할 수 없는 값은 추측하지 말고 확인할 수 없다고 말합니다.
- 구매 발주나 처방을 바꾸라고 단정하지 말고 '검토 필요'로 제안합니다.
```

## 3. 질문하고 비교하기

**Test data agent**(채팅 창)에서 아래 질문을 하나씩 하고, 2장 Graph 결과·`02_answers`와 비교합니다. 질문 사이에 **Clear chat**을 누릅니다.

| # | 질문 | 기대 답 (정답 기준) |
|---|---|---|
| 1 | `RM-HA-120 원료를 쓰는 처방 버전을 상태와 함께 알려줘` | 4개, 그중 `FV-CRM-01-02`는 폐기 |
| 2 | `RM-HA-120을 쓰는 현행·개발중 처방과 연결된 제품, 개발 과제는?` | 제품 `P-101`, `P-102`, `P-301` / 과제 `DP-2026-07` |
| 3 | `RM-HA-120을 쓰는 제품의 생산 계획일과 시장은?` | `PP-1101` 11-25 KR, `PP-1102` 12-02 CN, `PP-1103` 2027-01-20 KR |
| 4 | `RM-HA-120 입고가 12월 15일로 늦어지면 원료 필요일을 못 맞추는 대상은?` | `PP-1101`(필요일 11-18), `PP-1102`(11-25), `ST-0711`(11-13). `PP-1103`은 여유 |
| 5 | `RM-HA-120 대신 쓸 수 있는 원료와 중국 판매 제품에 쓸 수 있는지 알려줘` | `RM-HA-210`(리드타임 10일, CN 등록 필요), `RM-HA-305`(42일, CN 완료) |

**확인할 결과:** 질문 1–3은 Graph·`02_answers`와 같은 대상이 나옵니다. 질문 4처럼 **날짜 계산과 판정이 섞인 질문**은 답이 흔들릴 수 있습니다. 답에 포함된 생성 질의(GQL·SQL)를 펼쳐 어떤 조건으로 찾았는지 확인합니다.

> **토론 포인트:** Data Agent는 "내가 궁금한 것을 질문"할 때 강력합니다. 하지만 매번 사람이 물어야 합니다. 공급 지연처럼 **정해진 조건**은 사람이 묻기 전에 알려 주는 편이 낫습니다 — 다음 장의 Operations Agent입니다.

## 이 장의 완료 기준

- `da_cos`에 Ontology와 Graph model이 연결되어 있습니다.
- 질문 5개 중 1–3의 답이 정답과 같고, 4–5의 답을 정답과 비교해 차이를 설명할 수 있습니다.

## Troubleshooting

- Graph model이 원본 목록에 보이지 않으면 Graph의 미리 보기 기능 설정을 관리자에게 확인하고, Ontology만으로 진행합니다.
- "데이터에 접근할 수 없다"는 답이 나오면 `lh_cos` 읽기 권한과 Ontology 원본 바인딩을 확인합니다.
- 답이 지침과 다르게 폐기 버전을 포함하면 질문에 `is_active가 true인 버전만`을 덧붙여 다시 묻고, 지침의 문장이 저장되었는지 확인합니다.

## 공식 문서

- [Data agent 데이터 원본 추가 (Graph model 포함)](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-add-datasources)
- [Ontology를 Data agent 원본으로 사용](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-ontology-sources)
- [Data agent 개념·지원 원본·지침](https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent)

## 다음 단계

[04. Operations Agent](04-operations-agent.md)에서 공급 지연을 감시하고 먼저 알려 주는 에이전트를 만듭니다.
