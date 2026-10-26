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

## 1. 빈 작업 영역과 권한 확인

1. [Fabric 포털](https://app.fabric.microsoft.com)에 로그인하고 왼쪽 **Workspaces**에서 `cos-pNNN`(예: `cos-p001`)을 엽니다.
2. 내 계정에 이 작업 영역의 **Contributor 권한**과 항목 생성 기능이 있는지 확인합니다. 테넌트·용량·Teams·Purview의 공통 설정은 관리자가 준비하지만, **작업 영역 안의 실습 항목은 직접 만듭니다.**
3. 처음에는 작업 영역이 비어 있어야 합니다. 기존 항목이 있다면 삭제하거나 덮어쓰지 말고 관리자에게 새 실습 작업 영역인지 확인합니다.

| 항목 | 이름 | 비고 |
|---|---|---|
| Lakehouse | `lh_cos` | **이 장에서 직접 생성**. Lakehouse schemas를 켜고 `gold` 테이블도 직접 적재 |
| 원본 CSV | `Files/workshop/data` | **이 장에서 직접 업로드**. 핵심 11개, 선택 확장 포함 시 28개 |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review`, `04_publish_serving` | **이 장에서 5개를 직접 가져오고**, 각각 `lh_cos`를 기본 Lakehouse로 연결 |
| Eventhouse | `eh_cos` | **04장에서 직접 생성**. 지금은 없어도 정상. 같은 이름의 기본 KQL Database 자동 생성 |
| Ontology | `ont_cos` | **01장에서 직접 생성**. 지금은 없어도 정상 |
| SQL database | `sqldb_cos` | **06장에서 직접 생성**. 지금은 없어도 정상. 항목 생성 가능 여부는 사전 확인 |

## 2. 실습 파일 내려받기

1. [실습 저장소](https://github.com/minkyung01/fabric-cosmetics-workshop)를 열고 **Code → Download ZIP**으로 내려받아 압축을 풉니다. [ZIP 직접 다운로드](https://github.com/minkyung01/fabric-cosmetics-workshop/archive/refs/heads/main.zip)도 가능합니다. 별도로 안내받은 배포본이 있다면 그 버전을 사용합니다.
2. 압축을 푼 폴더에서 `data`의 핵심 CSV 11개와 `notebooks`의 `.ipynb` 파일 5개를 확인합니다. `notebooks/src`의 `.py` 파일이 아니라 **`.ipynb` 파일**을 가져옵니다. 로컬 Python·Git 설치는 필요 없습니다.
3. 07장 이후 선택 확장까지 할지 안내를 확인합니다. 진행할 경우 `data/extended`의 추가 CSV 17개도 **첫 적재 전에** 업로드합니다. 모델 확장 자체는 07장 이후에만 합니다.

## 3. Lakehouse 직접 만들기

1. 내 작업 영역에서 **+ New item → Lakehouse**를 선택합니다.
2. 이름을 **`lh_cos`**로 입력하고 **Lakehouse schemas** 체크를 유지한 채 **Create**를 누릅니다.
3. 생성이 끝나면 **Tables → dbo**와 **Files**가 보이는지 확인합니다. `dbo`는 스키마 지원 Lakehouse의 기본 스키마이며, `gold`·`ops`는 아직 없어도 정상입니다. SQL analytics endpoint는 Lakehouse와 함께 만들어지는 항목으로, 06장의 쓰기 가능한 SQL DB와 다릅니다.

스키마를 끈 Lakehouse나 기존 항목을 임의로 삭제·재생성하지 않습니다. `dbo`가 보이지 않으면 관리자와 스키마 설정을 확인한 뒤 진행합니다.

## 4. CSV 업로드와 원본 확인

1. `lh_cos`의 **Files**에서 **… → New subfolder**로 `workshop`을 만들고, 그 아래 `data` 하위 폴더를 만듭니다. 최종 경로는 **Files → workshop → data**입니다.
2. 이 `data` 폴더 안에서 **Upload files**를 선택하고 로컬 `data` 폴더의 다음 핵심 CSV 11개를 함께 업로드합니다. 폴더 전체가 아닌 **파일을 선택**해 `data/data`처럼 한 단계 더 중첩되지 않게 합니다.

```text
ingredient.csv          supplier.csv          raw_material.csv
material_alternative.csv formula_version.csv  formula_line.csv
product.csv             dev_project.csv       stability_test.csv
production_plan.csv     purchase_order.csv
```

3. 선택 확장도 할 경우 로컬 `data/extended`의 CSV 17개를 **같은 `Files/workshop/data` 폴더**에 추가 업로드합니다. Lakehouse 안에 `extended` 하위 폴더를 만들지 않습니다. 핵심만이면 11개, 확장 포함이면 28개가 같은 위치에 있어야 합니다.
4. `purchase_order.csv`를 미리 보고 `po_id`, `material_code`, `eta`, `status` 등의 열이 있는지 확인합니다. 파일을 테이블로 하나씩 수동 변환하지 않고 다음 Notebook에서 타입·스키마를 맞춰 함께 적재합니다.

확장 CSV가 모두 있으면 아래 Notebook이 총 28개 테이블을 만들지만, 01장의 Ontology는 핵심 11개 테이블만으로 시작합니다. 추가 파일이 일부만 있으면 오류로 중지하므로 첫 적재 전에 파일 구성을 확인합니다.

## 5. Notebook 5개 가져오기와 기본 Lakehouse 연결

1. 내 작업 영역으로 돌아가 도구 모음의 **Import → Notebook**(또는 **Import notebook**)을 선택합니다.
2. 로컬 `notebooks` 폴더의 다음 **`.ipynb` 5개**를 가져옵니다. 가져온 항목 이름도 아래와 같은지 확인합니다.

    ```text
    01_prepare_data.ipynb
    02_answers.ipynb
    03_supply_change.ipynb
    nb_apply_review.ipynb
    04_publish_serving.ipynb
    ```

3. **각 Notebook을 하나씩 열어** Lakehouse 탐색기의 **Add lakehouse → Existing lakehouse**로 내 작업 영역의 `lh_cos`를 선택합니다. 새 Lakehouse를 또 만들지 않습니다.
4. `lh_cos`를 **기본 Lakehouse로 고정(핀)**하고 저장 상태를 확인합니다. 연결만 추가한 상태가 아니라 기본 표시가 있는지, 작업 영역도 내 `cos-pNNN`인지 확인합니다. 이미 Spark 세션이 시작됐다면 기본 Lakehouse를 바꾼 뒤 세션을 다시 시작합니다.

**지금은 `01_prepare_data`만 실행합니다.** 나머지는 각 장의 질의·지연 반영·승인 후 조치·게시 단계에서 사용합니다. 특히 `03_supply_change`나 `nb_apply_review`를 미리 실행하지 않습니다. 승인 액션으로 실행할 `nb_apply_review`도 기본 Lakehouse를 미리 연결해야 합니다.

## 6. Notebook으로 gold 테이블 직접 만들기

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
- `lh_cos`를 스키마 지원 상태로 만들고 CSV를 올렸으며, Notebook 5개를 가져와 각각 기본 Lakehouse를 연결했습니다.
- `01_prepare_data`를 직접 실행해 `gold` 테이블을 만들었습니다.
- 테이블 수와 `PO-5501`의 초기 ETA·상태, 06장·07장의 환경 조건을 확인했습니다.

## Troubleshooting

- 작업 영역이 보이지 않으면 관리자에게 계정과 작업 영역 번호를 확인합니다.
- **항목 생성·가져오기 메뉴가 없거나 거부됨:** 작업 영역의 Contributor 권한, 유료 용량과 테넌트 설정을 관리자와 확인합니다. 테넌트·Purview 관리자 권한을 요청하거나 다른 사람 작업 영역에 항목을 만들지 않습니다.
- 처음에 `gold`가 없는 것은 정상입니다. 위 적재를 수행하고, 실패했다면 오류·CSV 폴더·기본 Lakehouse 연결을 확인합니다. 테이블을 만들지 못한 채 01장으로 넘어가지 않습니다.
- **기존 실습 테이블 오류:** 일부 테이블만 생성된 실패 이력도 포함합니다. 현재 테이블·승인 결과를 관리자와 확인하고, 초기화가 필요한 경우에만 동의 후 `reset_ops = True`로 실행합니다.
- **CSV 경로/파일 오류:** `Files/workshop/data`에 핵심 11개가 있는지, 확장 파일은 17개 전체가 같은 폴더에 있는지 확인합니다. `data/data`나 `data/extended` 하위 폴더에 잘못 올리지 않았는지 확인하며, 데이터가 없는데 적재 성공으로 처리하지 않습니다.
- **가져온 Notebook에서 Files/테이블을 찾지 못함:** 해당 Notebook의 기본 Lakehouse가 내 `lh_cos`인지 확인합니다. Notebook Resources에 CSV를 올린 것은 Lakehouse Files 업로드와 다릅니다.
- Notebook은 성공했지만 SQL analytics endpoint에 테이블이 아직 안 보이면 탐색기를 새로 고치고 동기화 상태를 확인합니다. 동기화 대기를 이유로 적재 Notebook을 재실행하지 않습니다.
- `PO-5501`이 이미 `지연`이면 기존 진행 상태입니다. 임의로 초기화하지 말고 관리자와 재사용·복구 범위를 확인합니다.
- `ont_cos`는 01장에서 만듭니다. 이미 엔터티가 들어 있는 항목이 있다면 임의로 삭제하지 말고 관리자에게 빈 항목부터 시작할 작업 영역을 확인합니다.

## 공식 문서

- [Microsoft Fabric IQ와 Ontology 개요](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview)
- [Lakehouse schemas와 생성 설정](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-schemas)
- [Notebook 가져오기·기본 Lakehouse 연결](https://learn.microsoft.com/en-us/fabric/data-engineering/how-to-use-notebook)
- [Operations agent 개요](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent)

## 다음 단계

직접 만든 `gold` 테이블을 원본으로 [01. Ontology](01-ontology.md)에서 Ontology Agent와 초안을 만들고, 질문의 범위를 넓혀 모델을 보강합니다.
