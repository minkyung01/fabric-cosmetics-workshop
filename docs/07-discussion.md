# 07. Data Highway 2.0 논의

[목차](../README.md) \| 이전: [06. Purview 거버넌스](06-purview.md)

오늘 만든 흐름을 정리하고, Data Highway가 **검색·분석 기반에서 능동적인 업무 지원 기반으로** 어떻게 확장될 수 있는지 이야기합니다.

## 1. 오늘 만든 것

| 기능 | 역할 | 오늘 만든 것 |
|---|---|---|
| Ontology | 우리 업무에서 무엇을 뜻하는가 | 성분·원료·처방 버전·시험·공급사 관계와 `is_active` 규칙 |
| Graph | 무엇과 어떤 경로로 연결되는가 | `RM-HA-120` → 제품 3개·개발 과제 1개 경로 |
| Data Agent | 내가 궁금한 것을 질문한다 | `da_cos` |
| Operations Agent | 정해진 조건을 감시하고 먼저 알려 준다 | `oa_cos` + Teams 제안 |
| 승인 후 Notebook | 사람이 승인한 조치만 기록한다 | `nb_apply_review` → 검토 요청 3건 |
| Purview | 민감도와 관리 상태 | 레이블·DLP 범위 |

## 2. 논의 질문

1. 우리 연구소에서 **"사람이 묻기 전에 알려 줘야 하는"** 변화는 무엇인가요? (원료 단종, 규제 변경, 안정성 시험 이탈 …)
2. 그 변화의 영향 경로를 Ontology로 정의하려면 **어떤 엔터티와 관계가 아직 데이터로 없나요?**
3. 에이전트에게 맡길 범위와 **사람의 승인이 꼭 필요한 범위**는 어디서 나눌까요?
4. 승인 후 자동으로 기록할 수 있는 조치는 무엇이고, 어떤 시스템(구매, PLM, 규제 등록)과 연결해야 하나요?
5. 처방 배합비 같은 영업 비밀을 에이전트가 다룰 때 지켜야 할 기준은 무엇인가요?

## 3. 정리

**확인할 결과:** 팀별로 "다음에 해 볼 감시 시나리오" 1개와 필요한 데이터·승인 단계를 적습니다.

## 4. 마무리 작업

1. `oa_cos`에서 **Stop**을 누릅니다. 켜 두면 5분마다 규칙 질의가 실행되어 용량을 씁니다.
2. 열려 있는 Notebook의 Spark 세션을 중지합니다.
3. 작업 영역 삭제는 관리자가 합니다([관리자 가이드](../admin/README.md)).

## 이 장의 완료 기준

- 오늘 만든 흐름을 기능별 역할로 설명할 수 있습니다.
- `oa_cos`를 중지했습니다.

## Troubleshooting

- **Stop** 버튼이 보이지 않으면 `oa_cos`를 새로 고친 뒤 다시 엽니다.

## 공식 문서

- [Operations agent](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent)
- [Ontology에서 Graph 만들기](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-graph)

## 다음 단계

수고하셨습니다. [목차](../README.md)로 돌아갑니다.
