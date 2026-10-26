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

1. 준비된 CSV를 확인하고 Notebook을 실행해 **`lh_cos.gold`에 실습 테이블을 직접 만듭니다.**
2. 빈 Ontology에서 **Ontology Agent로 업무 질문에 맞는 초안을 만들고**, 추가 질문에 필요한 대상·관계·업무 맥락을 보강합니다. 적용 전에는 사람이 원본과 설계를 검토합니다.
3. Graph 또는 Lakehouse SQL로 `RM-HA-120`의 영향 후보를 찾고, **현행·개발중 처방만** 남기도록 필터를 바꿔 봅니다.
4. Data Agent에 같은 질문을 하고 직접 실행한 질의·Notebook 결과와 비교합니다.
5. Operations Agent가 **공급 지연을 감지해 Teams로 알리고**, 승인하면 **검토 요청이 기록**되게 합니다.
6. SQL DB를 직접 만들어 승인된 요청을 게시하고, 담당 팀별 조회와 검토 착수·이력 확인을 수행합니다.
7. 연구 데이터에 민감도 레이블을 적용하고, 준비된 환경에서 DLP 정책과 연결합니다.

**탐색할 질문:** 같은 원료를 쓰는 대상이 모두 지연될까요? 연결되어 있다는 사실만으로 영향을 확정할 수 있을까요? 대체 원료가 있어도 바로 사용할 수 없는 경우는 무엇일까요?

실습하면서 **대상 ID·연결 경로·일정 근거·검토할 조치**를 기록합니다. 먼저 직접 질의하고 판단한 뒤, 각 단계의 예상 결과와 정답 Notebook으로 대조합니다.

**업무 경계:** 승인 후에도 AI가 처방이나 구매 발주를 직접 변경하지는 않습니다. 이 실습에서 실행하는 조치는 검토 요청과 이력 기록입니다.

## 1. 내 작업 영역 확인

1. [Fabric 포털](https://app.fabric.microsoft.com)에 로그인하고 왼쪽 **Workspaces**에서 `cos-pNNN`(예: `cos-p001`)을 엽니다.
2. 아래 표에서 준비된 항목과 직접 만들 항목을 구분합니다.

| 항목 | 이름 | 비고 |
|---|---|---|
| Lakehouse | `lh_cos` | 스키마 사용 설정된 항목. **`gold` 테이블은 이 장에서 직접 생성**하므로 지금은 없어도 정상 |
| 원본 CSV | `Files/workshop/data` | 핵심 CSV 11개. 선택 확장용 CSV가 함께 있으면 총 28개 |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review` | 기본 Lakehouse가 `lh_cos` |
| Notebook | `04_publish_serving` | 승인 후 게시 SQL 생성, 기본 Lakehouse `lh_cos` |
| Eventhouse | `eh_cos` | **04장에서 직접 생성**. 지금은 없어도 정상. 같은 이름의 기본 KQL Database 자동 생성 |
| Ontology | `ont_cos` | **01장에서 직접 생성**. 지금은 없어도 정상 |
| SQL database | `sqldb_cos` | **06장에서 직접 생성**. 지금은 없어도 정상. 생성에는 Member 또는 Admin 권한 필요 |

## 2. CSV 원본 확인

1. `lh_cos`를 열고 **Files → workshop → data**로 이동합니다. `Tables`가 아니라 **Files의 CSV**부터 확인합니다.
2. 다음 핵심 CSV 11개가 같은 폴더에 있는지 확인합니다.

```text
ingredient.csv          supplier.csv          raw_material.csv
material_alternative.csv formula_version.csv  formula_line.csv
product.csv             dev_project.csv       stability_test.csv
production_plan.csv     purchase_order.csv
```

3. `purchase_order.csv`를 미리 보고 `po_id`, `material_code`, `eta`, `status` 등의 열이 있는지 확인합니다. 파일을 테이블로 하나씩 수동 변환하지 않고 다음 Notebook에서 타입·스키마를 맞춰 함께 적재합니다.

07장 이후 Ontology 엔터티 확장도 진행할 환경이라면 추가 CSV 17개가 **첫 적재 전에 같은 폴더에** 있어야 합니다. 아래 Notebook이 총 28개 테이블을 만들지만, 01장의 Ontology는 핵심 11개 테이블만으로 시작합니다. 추가 파일이 일부만 있으면 오류로 중지하므로 관리자에게 파일 구성을 확인합니다.

## 3. Notebook으로 gold 테이블 직접 만들기

1. 작업 영역에서 **`01_prepare_data`**를 엽니다. 파일 이름은 `01_`로 시작하지만 **이 00장에서 실행하는 준비 Notebook**입니다.
2. Notebook의 기본 Lakehouse가 내 작업 영역의 `lh_cos`인지 확인합니다. 연결이 없거나 다른 Lakehouse이면 `lh_cos`를 기본 Lakehouse로 연결한 뒤 진행합니다.
3. 매개변수 셀을 확인합니다. 최초 적재는 다음 기본값을 유지합니다.

    ```python
    data_folder = "Files/workshop/data"
    reset_ops = False
    ```

4. **Run all**을 누르고 모든 셀이 성공할 때까지 기다립니다. 출력의 **`데이터 프로필: 11개 테이블`**과 `gold.<table>`별 행 수를 확인합니다. 확장 CSV도 준비된 환경은 **28개 테이블**로 표시됩니다.
5. `lh_cos`로 돌아가 탐색기를 새로 고칩니다. **Tables → gold**에서 핵심 테이블 11개(확장 포함 시 28개)를 확인합니다. `ops` 스키마도 생성하지만 영향 분석·승인 결과 테이블은 아직 없습니다.
6. **gold → purchase_order**를 열어 초기 데이터를 확인합니다.

**예상 결과:** `purchase_order` 6행, `PO-5501`(RM-HA-120)의 `eta = 2026-11-10`, `status = 확정`입니다. CSV를 업무 테이블로 적재했으며 아직 지연은 반영하지 않았습니다.

**재실행 주의:** 기본 `reset_ops = False`에서는 기존 실습 테이블이 있으면 **쓰기 전에 오류로 중지**합니다. 단순히 다시 확인하려고 값을 True로 바꾸지 않습니다. `reset_ops = True`는 기존 `gold`를 CSV로 덮어쓰고 `ops` 결과를 삭제하는 명시적 초기화이며, 현재 결과를 확인하고 초기화에 동의한 경우에만 사용합니다. 기존 테이블을 재사용했다면 직접 생성한 범위와 구분해 기록합니다.

## 이 장의 완료 기준

- 공급 지연의 영향과 대체 원료 검토에 필요한 질문을 설명할 수 있습니다.
- 실습 중 기록할 항목과 승인 후 실행할 조치의 범위를 이해했습니다.
- CSV와 기본 Lakehouse 연결을 확인하고 `01_prepare_data`를 직접 실행해 `gold` 테이블을 만들었습니다.
- 테이블 수와 `PO-5501`의 초기 ETA·상태, 06장·07장의 환경 조건을 확인했습니다.

## Troubleshooting

- 작업 영역이 보이지 않으면 관리자에게 계정과 작업 영역 번호를 확인합니다.
- 처음에 `gold`가 없는 것은 정상입니다. 위 적재를 수행하고, 실패했다면 오류·CSV 폴더·기본 Lakehouse 연결을 확인합니다. 테이블을 만들지 못한 채 01장으로 넘어가지 않습니다.
- **기존 실습 테이블 오류:** 일부 테이블만 생성된 실패 이력도 포함합니다. 현재 테이블·승인 결과를 관리자와 확인하고, 초기화가 필요한 경우에만 동의 후 `reset_ops = True`로 실행합니다.
- **CSV 경로/파일 오류:** `Files/workshop/data`에 핵심 11개가 있는지, 확장 파일은 17개 전체가 같은 폴더에 있는지 확인합니다. 데이터가 없는데 적재 성공으로 처리하지 않습니다.
- Notebook은 성공했지만 SQL analytics endpoint에 테이블이 아직 안 보이면 탐색기를 새로 고치고 동기화 상태를 확인합니다. 동기화 대기를 이유로 적재 Notebook을 재실행하지 않습니다.
- `PO-5501`이 이미 `지연`이면 기존 진행 상태입니다. 임의로 초기화하지 말고 관리자와 재사용·복구 범위를 확인합니다.
- `ont_cos`는 01장에서 만듭니다. 이미 엔터티가 들어 있는 항목이 있다면 임의로 삭제하지 말고 관리자에게 빈 항목부터 시작할 작업 영역을 확인합니다.

## 공식 문서

- [Microsoft Fabric IQ와 Ontology 개요](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview)
- [Operations agent 개요](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent)

## 다음 단계

직접 만든 `gold` 테이블을 원본으로 [01. Ontology](01-ontology.md)에서 Ontology Agent와 초안을 만들고, 질문의 범위를 넓혀 모델을 보강합니다.
