# 관리자 준비 가이드

[목차](../README.md)

Workshop 환경을 준비하고 정리하는 관리자용 문서입니다. 참가자는 보지 않아도 됩니다. 예시는 `p001` 기준이며 참가자마다 `pNNN`을 바꿔 반복합니다. 데이터 구조와 정답은 [데이터 설계](data-design.md)를 봅니다.

## 준비할 리소스

| 리소스 | 값 |
|---|---|
| Microsoft Fabric 용량 | **유료 F 용량**. Operations agent는 Trial 용량을 지원하지 않습니다. 12명 동시 실습 기준 F64 이상 권장 |
| 참가자 작업 영역 | `cos-pNNN` (참가자는 **Contributor** 이상) |
| Lakehouse | `lh_cos` (**schemas 켬**), `Files/workshop/data`에 CSV 11개 |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review` |
| Eventhouse | `eh_cos` (KQL Database 이름 동일) |
| Ontology | `ont_cos` — 기본 모델(엔터티 9, 관계 8) 또는 참고 모델(관계 10) |
| Microsoft Teams | 앱 **Fabric Operations Agent** 허용. 참가자는 Fabric과 **같은 계정**으로 Teams에 로그인 |
| Microsoft Purview (06장 데모) | 민감도 레이블 게시, DLP 정책 작성 권한. 강사 환경에서만 준비 |

## 1. Fabric 테넌트 설정

**Admin portal → Tenant settings**에서 참가자 보안 그룹에 아래 설정을 허용합니다. 반영에 최대 1시간 걸릴 수 있습니다.

| 설정 | 쓰는 장 |
|---|---|
| Users can create Fabric items | 전체 |
| Users can create ontology (preview) items, Graph (preview) 관련 설정 | 01–02 |
| Copilot and Azure OpenAI Service, (지역 밖 처리 필요 시) 지역 간 처리·저장 허용 | 01, 03–04 |
| Users can create and share Data agent item types | 03 |
| Operations agent (preview) 관련 설정, Real-Time Intelligence 항목 생성 | 04–05 |
| Information protection — 민감도 레이블 적용 허용 | 06 (강사) |

공식 문서: [Ontology 테넌트 설정](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview-tenant-settings), [Data agent 테넌트 설정](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-tenant-settings), [Operations agent 요구 사항](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent).

Teams 관리 센터에서 **Fabric Operations Agent** 앱을 참가자에게 허용합니다.

## 2. 참가자 작업 영역 일괄 준비

`admin/provision.py`가 참가자마다 작업 영역, Lakehouse, CSV 업로드, Notebook 4개, `01_prepare_data` 실행, Eventhouse, 기본 Ontology를 준비합니다. 이미 있는 항목은 다시 만들지 않습니다. 관리자 계정의 Azure CLI 로그인을 사용하며 비밀 값을 저장하지 않습니다.

1.  저장소 루트에서 Fabric 관리자(또는 용량 Contributor + 작업 영역 생성 권한) 계정으로 로그인합니다.

    ``` bash
    az login --tenant contoso.onmicrosoft.com
    ```

2.  참가자 목록 CSV를 만듭니다(예: `users.csv`, Git에 올리지 않음).

    ``` text
    participant,upn
    p001,p001@contoso.com
    p002,p002@contoso.com
    ```

3.  `--dry-run`으로 대상을 확인한 뒤 실제로 실행합니다.

    ``` bash
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv --dry-run
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv
    ```

**확인할 결과:** 참가자마다 `create workspace`, `create lakehouse lh_cos (schemas)`, `upload Files/workshop/data (11 csv)`, `import notebook …` 4줄, `run 01_prepare_data: completed`, `create eventhouse eh_cos`, `deploy ont_cos_base as ont_cos`가 출력됩니다.

| 옵션 | 용도 |
|---|---|
| `--reference-ontology` | 완성 모델(`fabric/ont_cos_reference`)을 `ont_cos`로 배포합니다. Ontology agent를 쓸 수 없는 환경이나 01장을 끝내지 못한 참가자용입니다. 기존 `ont_cos`를 먼저 지워야 합니다. |
| `--skip-prepare` | `01_prepare_data` 실행을 건너뜁니다. 참가자가 직접 실행하게 할 때 씁니다. |
| `--update-notebooks` | 이미 있는 Notebook을 저장소 최신 버전으로 덮어씁니다. |
| `--prefix` | 작업 영역 이름 접두사(기본 `cos-`) |
| `--role` | 참가자 권한(기본 `Contributor`) |
| `--tenant` | 여러 테넌트에 로그인한 경우 토큰을 받을 테넌트 |

**수동 준비:** 작업 영역을 만들고 용량에 할당한 뒤 `lh_cos`를 **Lakehouse schemas** 켜고 만듭니다. `Files/workshop/data`에 `data/*.csv`를 올리고, `notebooks/*.ipynb` 4개를 가져와 기본 Lakehouse를 `lh_cos`로 연결한 뒤 `01_prepare_data`를 실행합니다. Eventhouse `eh_cos`를 만들고, Ontology는 [01장](../docs/01-ontology.md)의 엔터티·관계 표대로 만들거나 `fabric/ont_cos_base`를 REST API로 배포합니다(`{{WORKSPACE_ID}}`, `{{LAKEHOUSE_ID}}` 치환).

소스를 고쳤다면 `python tools/build_notebooks.py`, `python tools/build_ontology.py`로 산출물을 다시 만들고 `python -m unittest discover -s tests`로 점검합니다.

## 3. 사전 점검 체크리스트

실습 전에 `cos-p001` 같은 작업 영역에서 교재대로 전체를 한 번 실행하고 아래 값을 확인합니다.

| 장 | 확인할 값 |
|---|---|
| 준비 | `gold` 테이블 11개, `ops` 스키마 비어 있음 |
| 01 | 관계 10개, `FormulaVersion.is_active`, `RawMaterial.cn_registration` 추가 |
| 02 | Graph Q1 4행 → `is_active` 필터 3행, 생산 계획 `PP-1101`·`PP-1102`·`PP-1103`, `ST-0711` |
| 02 | `02_answers` Q5 지연 전 여유 8·15·64·3일 |
| 03 | `da_cos` 질문 1–3이 정답과 일치 |
| 04 | `03_supply_change`: `ops.material_impact` 4행 중 영향 3행(-27·-20·-32일), 이벤트 `SUP-20261102-RM-HA-120-r1` open 1행, Teams 메시지 5–10분 |
| 05 | `nb_apply_review` Succeeded, `ops.review_request` 3행, `ops.action_log` 1행, `open → review_requested` |
| 06 | 레이블·DLP 정책 화면을 강사 계정으로 열 수 있음 |

## 4. 다시 시연하기

- 같은 작업 영역에서 04–05장을 다시 하려면 `03_supply_change`의 `run_tag`를 `r2`처럼 바꿔 실행합니다. ETA 지연은 원본 CSV 기준이라 누적되지 않습니다.
- 처음 상태로 되돌리려면 `01_prepare_data`를 `reset_ops = True`로 실행합니다. `gold` 테이블을 다시 만들고 `ops` 테이블을 지웁니다. Eventhouse 이력은 남으므로 새 `run_tag`를 씁니다.
- `03_supply_change` 실행 후 Graph에서 새 ETA를 보려면 Graph를 새로 고치거나 다시 Materialize합니다.

## 5. 정리

1. 참가자 `oa_cos`를 **Stop**합니다(5분마다 규칙 질의 실행).
2. 강사 환경의 DLP 정책·레이블 변경을 원래대로 돌립니다.
3. 작업 영역 `cos-pNNN`을 삭제합니다. 작업 영역 삭제로 Ontology, Graph, Data agent, Operations agent, Eventhouse, Lakehouse가 함께 지워집니다.
4. Teams 앱 허용·테넌트 설정을 실습 전 상태로 되돌립니다.
