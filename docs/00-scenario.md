# 00. 시나리오와 미션

[목차](../README.md) \| 다음: [01. Ontology](01-ontology.md)

## 상황

Caldova 코스메틱 연구소의 원료 담당자는 2026년 11월 2일 월요일 아침, 공급사 **Aqua Derm Chemicals**로부터 메일을 받습니다.

> "소듐하이알루로네이트 1% 용액(저분자), 원료 코드 `RM-HA-120`의 다음 입고가 **11월 10일에서 12월 15일로 35일 늦어집니다**."

지금까지는 담당자가 처방 시스템·생산 계획·개발 과제 목록을 하나씩 열어 영향 대상을 찾았습니다. 이 워크숍에서는 같은 일을 다음 순서로 바꿔 봅니다.

| 단계 | 질문 | 사용하는 기능 |
|---|---|---|
| 이해 | 업무 대상을 어떤 키로 식별하고, 원본 데이터와 관계를 어떻게 연결해 재사용하는가? | Ontology |
| 찾기 | `RM-HA-120`에서 출발하면 어떤 처방·제품·과제까지 닿는가? 폐기된 처방은 빼야 하지 않나? | Graph |
| 묻기 | "RM-HA-120 공급이 늦어지면 무엇을 검토해야 해?"를 자연어로 물으면? | Data Agent |
| 먼저 알리기 | 공급 지연이 생기면 사람이 묻기 전에 알려 줄 수 있나? | Operations Agent + Teams |
| 승인 후 조치 | 담당자가 승인하면 검토 요청을 등록하고 이력을 남긴다 | Notebook |
| 업무 제공 | 승인 결과를 담당자가 조회하고 검토 상태를 바꾸려면? | SQL database in Fabric |
| 관리 | 처방 배합비 같은 영업 비밀은 어떻게 관리하나? | Microsoft Purview |

## 미션

1. Ontology에 빠진 관계와 업무 규칙을 채워 **영향 경로가 끊기지 않게** 합니다.
2. Graph 또는 Lakehouse SQL로 `RM-HA-120`의 영향 후보를 찾고, **현행·개발중 처방만** 남기도록 필터를 바꿔 봅니다.
3. Data Agent에 같은 질문을 하고 직접 실행한 질의·Notebook 결과와 비교합니다.
4. Operations Agent가 **공급 지연을 감지해 Teams로 알리고**, 승인하면 **검토 요청이 기록**되게 합니다.
5. 승인된 요청을 SQL DB로 게시하고, 담당 팀별 조회와 검토 착수·이력 확인을 수행합니다.
6. 연구 데이터에 민감도 레이블을 적용하고, 준비된 환경에서 DLP 정책과 연결합니다.

**탐색할 질문:** 같은 원료를 쓰는 대상이 모두 지연될까요? 연결되어 있다는 사실만으로 영향을 확정할 수 있을까요? 대체 원료가 있어도 바로 사용할 수 없는 경우는 무엇일까요?

실습하면서 **대상 ID·연결 경로·일정 근거·검토할 조치**를 기록합니다. 먼저 직접 질의하고 판단한 뒤, 각 단계의 예상 결과와 정답 Notebook으로 대조합니다.

**업무 경계:** 승인 후에도 AI가 처방이나 구매 발주를 직접 변경하지는 않습니다. 이 실습에서 실행하는 조치는 검토 요청과 이력 기록입니다.

## 1. 내 작업 영역 확인

1. [Fabric 포털](https://app.fabric.microsoft.com)에 로그인하고 왼쪽 **Workspaces**에서 `cos-pNNN`(예: `cos-p001`)을 엽니다.
2. 아래 항목이 있는지 확인합니다.

| 항목 | 이름 | 비고 |
|---|---|---|
| Lakehouse | `lh_cos` | `gold` 스키마 아래 핵심 테이블 11개(선택 확장 준비 시 28개) |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review` | 기본 Lakehouse가 `lh_cos` |
| Notebook | `04_publish_serving` | 승인 후 게시 SQL 생성, 기본 Lakehouse `lh_cos` |
| Eventhouse | `eh_cos` | KQL 데이터베이스 `eh_cos` 포함 |
| Ontology | `ont_cos` | 기본 모델(엔터티 9개, 관계 8개) |
| SQL database | `sqldb_cos` | 관리자가 준비. 06장에서 스키마 생성·게시·조회 |

3. `lh_cos`를 열고 **Tables** → `gold` → `purchase_order`를 누릅니다.

**예상 결과:** 6행이 보이고 `PO-5501`(RM-HA-120)의 `eta`가 `2026-11-10`, `status`가 `확정`입니다. 아직 지연이 반영되지 않은 상태입니다.

## 이 장의 완료 기준

- 공급 지연의 영향과 대체 원료 검토에 필요한 질문을 설명할 수 있습니다.
- 실습 중 기록할 항목과 승인 후 실행할 조치의 범위를 이해했습니다.
- 내 작업 영역에 준비된 항목과 06장·07장의 환경 조건을 확인했습니다.

## Troubleshooting

- 작업 영역이 보이지 않으면 관리자에게 계정과 작업 영역 번호를 확인합니다.
- `gold` 테이블이 없거나 `PO-5501`이 이미 `지연` 상태면 관리자에게 초기 상태 복원을 요청합니다. `01_prepare_data` 재실행은 기존 실습 결과를 삭제하므로 임의로 초기화하지 않습니다.
- `ont_cos`가 없으면 관리자에게 실습 항목 준비를 요청합니다.

## 공식 문서

- [Microsoft Fabric IQ와 Ontology 개요](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview)
- [Operations agent 개요](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent)

## 다음 단계

[01. Ontology](01-ontology.md)에서 기본 모델에 빠진 관계와 업무 규칙을 채웁니다.
