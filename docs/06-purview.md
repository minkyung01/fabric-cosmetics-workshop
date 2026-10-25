# 06. Purview 거버넌스 — 연구 데이터 보호 (데모)

[목차](../README.md) \| 이전: [05. 승인 후 조치](05-approval.md) \| 다음: [07. Data Highway 2.0 논의](07-discussion.md)

에이전트가 연구 데이터를 읽고 조치까지 연결하면, **어떤 데이터가 민감하고 누가 다룰 수 있는지**가 더 중요해집니다. 이 장은 **강사가 준비된 환경에서 10분 동안 시연**합니다. 참가자는 화면을 보고 질문에 답합니다.

## 시작 전 확인 (강사)

- Microsoft Purview 정보 보호 라이선스와 민감도 레이블이 게시되어 있고, 테넌트에서 Fabric 항목에 레이블 적용이 허용되어 있습니다.
- DLP 정책을 보여 주려면 Fabric(또는 Premium) 용량 작업 영역이어야 하고, 정책 작성 권한(규정 준수 관리자 등)이 필요합니다.
- **실제 권한과 지원 범위가 확보된 항목만 보여 줍니다.** 준비되지 않은 기능은 슬라이드로 설명하고 시연하지 않습니다.

## 1. 무엇이 민감한가

| 데이터 | 예 | 민감도 |
|---|---|---|
| 처방 배합비 | `formula_line.pct_wt` | 영업 비밀 — 가장 높음 |
| 개발 과제·안정성 시험 | `dev_project`, `stability_test` | 사내 기밀 |
| 공급사·단가 | `supplier`, `raw_material.unit_price_krw` | 사내 기밀 |
| 검토 요청·조치 이력 | `ops.review_request`, `ops.action_log` | 사내 일반 |

**확인할 결과:** 참가자가 "에이전트가 답할 때 배합비를 그대로 보여 줘도 되는가?"에 답할 수 있습니다.

## 2. 민감도 레이블 적용

1. 작업 영역에서 `lh_cos`의 **Settings** → **Sensitivity label**(또는 리본의 레이블 아이콘)에서 사내 기밀 레이블을 고릅니다.
2. 레이블이 항목 이름 옆에 표시되는지 확인합니다.

**확인할 결과:** `lh_cos`에 레이블이 보이고, 지원되는 내보내기(예: Excel, PBIX)에서 레이블이 이어집니다.

## 3. DLP 정책 범위 보기

1. Purview 포털 → **Data loss prevention** → **Policies**에서 준비된 정책을 엽니다.
2. 위치가 **Fabric and Power BI workspaces**이고, 대상 작업 영역에 `cos-` 작업 영역이 포함된 것을 보여 줍니다.
3. 조건(민감 정보 유형 또는 레이블)과 작업(정책 팁, 경고)을 설명합니다.

**확인할 결과:** DLP가 지원하는 Fabric 항목(Lakehouse, KQL Database, 의미 체계 모델 등)과 레이블이 함께 쓰이는 구조를 설명할 수 있습니다.

## 4. 카탈로그에서 찾기 (준비된 경우)

Purview **Unified Catalog**에 Fabric 작업 영역을 스캔해 두었다면 `lh_cos`의 테이블을 검색해 소유자·설명·분류를 보여 줍니다.

## 꼭 구분할 것

- **Lineage(계보) 화면은 Fabric 기능입니다.** Purview 자체 기능처럼 설명하지 않습니다.
- **Ontology의 업무 정의는 접근 통제가 아닙니다.** 누가 읽을 수 있는지는 작업 영역 역할, 항목 권한, OneLake 보안, 레이블·DLP가 정합니다.
- 승인된 Operations agent 작업은 **작성자 권한**으로 실행됩니다. 작성자 권한을 최소로 두는 것도 거버넌스입니다.

## 이 장의 완료 기준

- 처방 배합비처럼 민감한 데이터를 구분하고, 레이블·DLP·카탈로그가 각각 하는 일을 설명할 수 있습니다.

## Troubleshooting

- 레이블 메뉴가 보이지 않으면 테넌트의 정보 보호 설정과 레이블 게시 정책 대상에 사용자가 포함되었는지 확인합니다.
- DLP 정책이 작업 영역에 적용되지 않으면 용량 종류(Fabric·Premium)와 정책 위치 설정을 확인합니다. KQL Database는 OneLake 가용성이 켜져 있어야 합니다.

## 공식 문서

- [Fabric의 DLP 정책 구성](https://learn.microsoft.com/en-us/fabric/governance/data-loss-prevention-configure)
- [Power BI·Fabric DLP 시작하기](https://learn.microsoft.com/en-us/purview/dlp-powerbi-get-started)
- [Fabric의 민감도 레이블](https://learn.microsoft.com/en-us/fabric/fundamentals/apply-sensitivity-labels)

## 다음 단계

[07. Data Highway 2.0 논의](07-discussion.md)에서 오늘 만든 흐름을 실제 업무에 어떻게 적용할지 이야기합니다.
