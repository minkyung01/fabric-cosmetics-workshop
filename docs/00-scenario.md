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
2. Graph에서 `RM-HA-120`의 영향 대상을 찾고, **현행·개발중 처방만** 남기도록 필터를 바꿔 봅니다.
3. Data Agent에 같은 질문을 하고 Graph·정답 Notebook과 비교합니다.
4. Operations Agent가 **공급 지연을 감지해 Teams로 알리고**, 승인하면 **검토 요청이 기록**되게 합니다.
5. 승인된 요청을 SQL DB로 게시하고, 담당 팀별 조회와 검토 착수·이력 확인을 수행합니다.
6. 연구 데이터에 민감도 레이블을 적용하고, 준비된 환경에서 DLP 정책과 연결합니다.

**정답 미리 보기:** 지연을 반영하면 영향 대상은 3건입니다 — 생산 계획 `PP-1101`(수분 장벽 크림, KR), `PP-1102`(수분 장벽 크림, CN), 개발 과제 `DP-2026-07`의 안정성 시험 `ST-0711`. 시카 앰플 생산 계획 `PP-1103`은 여유가 29일 남아 영향이 없고, 폐기된 처방 `FV-CRM-01-02`는 분석 대상이 아닙니다.

## 1. 완성된 업무 흐름 보기 (강사 시연)

강사가 미리 완성한 작업 영역에서 마지막 장면을 먼저 보여 줍니다.

**공급 지연 반영 → 감시 조건 충족 → Teams 제안 → 담당자 승인 → 검토 요청 기록**

**확인할 결과:** Teams의 **Fabric Operations Agent** 채팅에 영향 대상 3건과 대응 제안이 담긴 메시지가 오고, 승인 후 `ops.review_request`에 검토 요청 3건이 생깁니다. AI가 처방이나 발주를 직접 바꾸지 않는다는 점에 주목합니다.

## 2. 내 작업 영역 확인

1. [Fabric 포털](https://app.fabric.microsoft.com)에 로그인하고 왼쪽 **Workspaces**에서 `cos-pNNN`(예: `cos-p001`)을 엽니다.
2. 아래 항목이 있는지 확인합니다.

| 항목 | 이름 | 비고 |
|---|---|---|
| Lakehouse | `lh_cos` | `gold` 스키마 아래 테이블 11개 |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review` | 기본 Lakehouse가 `lh_cos` |
| Notebook | `04_publish_serving` | 승인 후 게시 SQL 생성, 기본 Lakehouse `lh_cos` |
| Eventhouse | `eh_cos` | KQL 데이터베이스 `eh_cos` 포함 |
| Ontology | `ont_cos` | 기본 모델(엔터티 9개, 관계 8개) |
| SQL database | `sqldb_cos` | 관리자가 준비. 06장에서 스키마 생성·게시·조회 |

3. `lh_cos`를 열고 **Tables** → `gold` → `purchase_order`를 누릅니다.

**예상 결과:** 6행이 보이고 `PO-5501`(RM-HA-120)의 `eta`가 `2026-11-10`, `status`가 `확정`입니다. 아직 지연이 반영되지 않은 상태입니다.

## 이 장의 완료 기준

- 시나리오와 정답 미리 보기의 영향 대상 3건을 이해했습니다.
- 내 작업 영역에 준비된 항목과 06장·07장의 환경 조건을 확인했습니다.

## Troubleshooting

- 작업 영역이 보이지 않으면 관리자에게 계정과 작업 영역 번호를 확인합니다.
- `gold` 테이블이 없거나 `PO-5501`이 `지연` 상태면 `01_prepare_data`를 열어 **Run all**로 초기화합니다(약 2–3분).
- `ont_cos`가 없으면 관리자에게 `provision.py` 재실행을 요청합니다.

## 공식 문서

- [Microsoft Fabric IQ와 Ontology 개요](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview)
- [Operations agent 개요](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent)

## 다음 단계

[01. Ontology](01-ontology.md)에서 기본 모델에 빠진 관계와 업무 규칙을 채웁니다.
