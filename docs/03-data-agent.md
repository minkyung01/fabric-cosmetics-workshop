# 03. Data Agent — 같은 문제를 자연어로 묻기

[목차](../README.md) \| 이전: [02. Graph](02-graph.md) \| 다음: [04. Operations Agent](04-operations-agent.md)

앞에서 확인한 영향 대상을 이번에는 **자연어로 질문**해 찾습니다. 기본 경로는 **Ontology 업무 맥락 → Lakehouse SQL**입니다. Ontology 자체가 질의 실행 엔드포인트이거나 Graph 저장소인 것은 아닙니다. 별도 Graph model을 연결하면 GQL 질의와도 비교할 수 있습니다.

## 시작 전 확인

- 1장에서 `ont_cos`의 관계와 속성을 완성했고, `lh_cos`의 SQL analytics endpoint에서 `gold` 테이블을 조회할 수 있습니다. Graph는 필수가 아닙니다.
- 테넌트에서 Data agent와 Copilot·Azure OpenAI 설정이 켜져 있어야 합니다(관리자 준비 사항).
- Data agent 하나에 데이터 원본은 최대 5개까지 연결할 수 있습니다.

## 1. Data Agent 만들고 원본 연결

1. 작업 영역에서 **+ New item** → **Data agent**를 고르고 이름을 `da_cos`로 만듭니다.
2. **Sources → Add sources → Add an ontology**(환경에 따라 **Add data source**)에서 `ont_cos`를 추가합니다. 새 Ontology 문맥 경험은 **preview runtime**을 사전에 확인합니다.
3. Ontology를 펼쳐 엔터티와 연결된 원본 `lh_cos`를 확인합니다. 필요하면 연결 가능한 Lakehouse 원본을 추가/마운트해 원본별 지침·예제 SQL을 설정합니다. 요청 사용자에게 Lakehouse/SQL endpoint 읽기 권한이 있어야 합니다.
4. **선택:** 02장을 수행했다면 Graph model `ont_cos_graph_…`을 추가합니다. SQL과 GQL을 구분해서 비교하려면 별도의 `da_cos_graph`를 만들고 Graph 원본만 연결하는 편이 명확합니다.

**확인할 결과:** Sources에서 `ont_cos`와 연결된 Lakehouse 원본을 확인하고, 기본 질문의 실행 단계에 **SQL과 실제 Lakehouse 실행 원본**이 표시됩니다. Graph를 만들지 않아도 이 단계가 동작합니다. Ontology 편집 후 문맥은 자동 반영에 최대 10분이 걸릴 수 있으므로 **Refresh**로 갱신합니다.

## 2. 에이전트 지침 입력

**Agent instructions**에 아래 지침을 붙여 넣습니다.

``` text
Caldova 코스메틱 연구소의 원료 변경 영향 분석을 돕습니다. 답은 한국어로 씁니다.
기본 질의는 ont_cos의 정의와 바인딩을 참고해 lh_cos의 gold 테이블에 SQL로 실행합니다.
관계 이름은 업무 의미이며 SQL 테이블명과 같다고 가정하지 않습니다.

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

**Test data agent**(채팅 창)에서 아래 질문을 하나씩 하고 `02_answers`와 비교합니다. Graph를 수행했다면 2장 결과도 비교합니다. 질문 사이에 **Clear chat**을 누릅니다.

| # | 질문 | 기대 답 (정답 기준) |
|---|---|---|
| 1 | `RM-HA-120 원료를 쓰는 처방 버전을 상태와 함께 알려줘` | 4개, 그중 `FV-CRM-01-02`는 폐기 |
| 2 | `RM-HA-120을 쓰는 현행·개발중 처방과 연결된 제품, 개발 과제는?` | 제품 `P-101`, `P-102`, `P-301` / 과제 `DP-2026-07` |
| 3 | `RM-HA-120을 쓰는 제품의 생산 계획일과 시장은?` | `PP-1101` 11-25 KR, `PP-1102` 12-02 CN, `PP-1103` 2027-01-20 KR |
| 4 | `RM-HA-120 입고가 12월 15일로 늦어지면 원료 필요일을 못 맞추는 대상은?` | `PP-1101`(필요일 11-18), `PP-1102`(11-25), `ST-0711`(11-13). `PP-1103`은 여유 |
| 5 | `RM-HA-120 대신 쓸 수 있는 원료와 중국 판매 제품에 쓸 수 있는지 알려줘` | `RM-HA-210`(리드타임 10일, CN 등록 필요), `RM-HA-305`(42일, CN 완료) |

**확인할 결과:** 질문 1–3은 `02_answers`와 같은 대상이 나옵니다. 질문 4처럼 **날짜 계산과 판정이 섞인 질문**은 답이 흔들릴 수 있습니다. 실행 단계와 생성 SQL을 펼쳐 실제 원본·조인·조건을 확인합니다. 선택 Graph 에이전트에서는 같은 질문의 생성 GQL과 결과를 비교합니다. 한 에이전트에 두 원본을 넣고 항상 원하는 쪽으로 라우팅될 것이라고 가정하지 않습니다.

> **토론 포인트:** Data Agent는 "내가 궁금한 것을 질문"할 때 강력합니다. 하지만 매번 사람이 물어야 합니다. 공급 지연처럼 **정해진 조건**은 사람이 묻기 전에 알려 주는 편이 낫습니다 — 다음 장의 Operations Agent입니다.

## 이 장의 완료 기준

- `da_cos`가 Ontology 문맥을 활용해 Lakehouse에 SQL 질의하는 경로를 확인했습니다. Graph는 선택 비교입니다.
- 질문 5개 중 1–3의 답이 정답과 같고, 4–5의 답을 정답과 비교해 차이를 설명할 수 있습니다.

## Troubleshooting

- Graph model이 원본 목록에 보이지 않으면 Graph의 미리 보기 기능 설정을 관리자에게 확인하고, Ontology만으로 진행합니다.
- "데이터에 접근할 수 없다"는 답이 나오면 `lh_cos` 읽기 권한과 Ontology 원본 바인딩을 확인합니다.
- 답이 지침과 다르게 폐기 버전을 포함하면 질문에 `is_active가 true인 버전만`을 덧붙여 다시 묻고, 지침의 문장이 저장되었는지 확인합니다.
- 엔터티 정의가 오래되면 Ontology 문맥 **Refresh**를 실행하고 내려받은 문맥·실행 단계를 확인합니다. 문맥 편집은 Ontology에서 합니다.
- 확장 모델의 일부 엔터티만 Data Agent에 노출하는 선택 기능은 현재 지원되지 않습니다. 기본 `ont_cos`와 확장 `ont_cos_extended`는 별도 에이전트로 비교합니다([확장 실습](../admin/extended-model.md)).

## 공식 문서

- [Data agent 데이터 원본 추가 (Graph model 포함)](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-add-datasources)
- [Ontology를 Data agent 원본으로 사용](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-ontology-sources)
- [Data agent 개념·지원 원본·지침](https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent)

## 다음 단계

[04. Operations Agent](04-operations-agent.md)에서 공급 지연을 감시하고 먼저 알려 주는 에이전트를 만듭니다.
