# 관리자 준비 가이드

[목차](../README.md)

Workshop 환경을 준비하고 정리하는 관리자용 문서입니다. 참가자는 보지 않아도 됩니다. 예시는 `p001` 기준이며 참가자마다 `pNNN`을 바꿔 반복합니다. 데이터 구조와 정답은 [데이터 설계](data-design.md)를 봅니다.

**사전 필독:** [미리 보기 제약·호환성](preview-limitations.md). Ontology 새/기존 경험과 API 정의 호환성, **2027-01-31 기존 경험 종료**, Graph 선택 투영·적격성, Data Agent 문맥 갱신·권한, Operations Agent 감시·실행 권한을 확인합니다. 엔터티가 많은 시나리오는 [26개 엔터티 선택 확장](extended-model.md)을 별도로 준비합니다.

## 준비할 리소스

| 리소스 | 값 |
|---|---|
| Microsoft Fabric 용량 | **유료 F 용량**. Operations agent는 Trial 용량을 지원하지 않습니다. 12명 동시 실습 기준 F64 이상 권장 |
| 참가자 작업 영역 | `cos-pNNN` (참가자는 **Contributor** 이상) |
| Lakehouse | `lh_cos` (**schemas 켬**), `Files/workshop/data`에 핵심 CSV 11개. 선택 확장은 17개 추가, 총 28개 |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review`, `04_publish_serving` |
| Eventhouse | `eh_cos` (KQL Database 이름 동일) |
| Ontology | `ont_cos` — 기본 모델(엔터티 9, 관계 8) 또는 참고 모델(관계 10). 확장은 별도 `ont_cos_extended`(엔터티 26, 관계 40) |
| Microsoft Teams | 앱 **Fabric Operations Agent** 허용. 참가자는 Fabric과 **같은 계정**으로 Teams에 로그인 |
| SQL database | `sqldb_cos` — 작업 영역 Admin/Member가 수동 생성. 참가자별 DB 권장 |
| Microsoft Purview (07장) | 참가자 Pro/PPU·레이블 사용 권한·게시 정책. DLP·카탈로그 확장은 아래 별도 조건 확인 |

## 1. Fabric 테넌트 설정

**Admin portal → Tenant settings**에서 참가자 보안 그룹에 아래 설정을 허용합니다. 반영에 최대 1시간 걸릴 수 있습니다.

| 설정 | 쓰는 장 |
|---|---|
| Users can create Fabric items | 전체 |
| Users can create ontology (preview) items, Graph (preview) 관련 설정 | 01–02 |
| Copilot and Azure OpenAI Service, (지역 밖 처리 필요 시) 지역 간 처리·저장 허용 | 01, 03–04 |
| Users can create and share Data agent item types | 03 |
| Operations agent (preview) 관련 설정, Real-Time Intelligence 항목 생성 | 04–05 |
| Information protection — 민감도 레이블 적용 허용 | 07 |

공식 문서: [Ontology 테넌트 설정](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview-tenant-settings), [Data agent 테넌트 설정](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-tenant-settings), [Operations agent 요구 사항](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent).

Teams 관리 센터에서 **Fabric Operations Agent** 앱을 참가자에게 허용합니다.

## 2. 참가자 작업 영역 일괄 준비

`admin/provision.py`가 참가자마다 작업 영역, Lakehouse, CSV 업로드, Notebook 5개, `01_prepare_data` 실행, Eventhouse, 기본 Ontology를 준비합니다. **SQL DB·Purview 정책은 자동 생성하지 않으며 아래 사전 준비가 필요합니다.** 이미 있는 항목은 다시 만들지 않습니다. 관리자 계정의 Azure CLI 로그인을 사용하며 비밀 값을 저장하지 않습니다.

1.  저장소 루트에서 Fabric 관리자(또는 용량 Contributor + 작업 영역 생성 권한) 계정으로 로그인합니다.

    ``` bash
    az login --tenant <your-tenant-id>
    ```

2.  참가자 목록 CSV를 만듭니다(예: `users.csv`, Git에 올리지 않음).

    ``` text
    participant,upn
    p001,p001@example.com
    p002,p002@example.com
    ```

3.  `--dry-run`으로 대상을 확인한 뒤 실제로 실행합니다.

    ``` bash
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv --dry-run
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv
    ```

**확인할 결과:** 참가자마다 `create workspace`, `create lakehouse lh_cos (schemas)`, `upload Files/workshop/data (11 csv)`, `import notebook …` 5줄, `run 01_prepare_data: completed`, `create eventhouse eh_cos`, `deploy ont_cos_base as ont_cos`가 출력됩니다.

| 옵션 | 용도 |
|---|---|
| `--reference-ontology` | 완성 모델(`fabric/ont_cos_reference`)을 `ont_cos`로 배포합니다. Ontology agent를 쓸 수 없는 환경이나 01장을 끝내지 못한 참가자용입니다. 기존 `ont_cos`를 먼저 지워야 합니다. |
| `--extended-ontology` | 확장 CSV 17개를 추가 업로드하고 별도 `ont_cos_extended` 완성 모델을 배포합니다. 기존 작업 영역은 `--update-notebooks`도 필요하며 승인 실습 전에 준비합니다([확장 가이드](extended-model.md)). |
| `--skip-prepare` | `01_prepare_data` 실행을 건너뜁니다. 참가자가 직접 실행하게 할 때 씁니다. |
| `--update-notebooks` | 이미 있는 Notebook을 저장소 최신 버전으로 덮어씁니다. |
| `--prefix` | 작업 영역 이름 접두사(기본 `cos-`) |
| `--role` | 참가자 권한(기본 `Contributor`) |
| `--tenant` | 여러 테넌트에 로그인한 경우 토큰을 받을 테넌트 |

**수동 준비:** 작업 영역을 만들고 용량에 할당한 뒤 `lh_cos`를 **Lakehouse schemas** 켜고 만듭니다. `Files/workshop/data`에 `data/*.csv`를 올리고, `notebooks/*.ipynb` 5개를 가져와 기본 Lakehouse를 `lh_cos`로 연결한 뒤 `01_prepare_data`를 실행합니다. Eventhouse `eh_cos`를 만들고, Ontology는 [01장](../docs/01-ontology.md)의 엔터티·관계 표대로 만들거나 `fabric/ont_cos_base`를 REST API로 배포합니다(`{{WORKSPACE_ID}}`, `{{LAKEHOUSE_ID}}` 치환).

## SQL Serving DB 준비 (06장)

1. 작업 영역 **Admin/Member** 계정으로 **New item → SQL database**에서 `sqldb_cos`를 만듭니다. 기본 Contributor 참가자에게 생성 권한이 있다고 가정하지 않습니다.
2. SQL database 쿼리 편집기에서 [serving.sql](../fabric/sql/serving.sql)을 실행합니다. 참가자가 DDL을 직접 할 환경이면 06장 1단계로 남겨도 됩니다.
3. 참가자 계정으로 SELECT·EXECUTE와 필요한 항목 접근을 확인합니다. 최소 권한 경로에서는 관리자가 스키마를 만든 뒤 해당 DB 사용자에게 `GRANT SELECT, EXECUTE ON SCHEMA::serving TO [참가자 DB 사용자];`를 적용합니다. 사용자 생성·항목 공유는 조직의 Entra/SQL 권한 절차를 따릅니다.
4. `04_publish_serving`은 SQL 연결·전송을 하지 않습니다. 출력된 **게시 SQL을 참가자가 SQL DB에서 실행**하는 경로를 실제 계정으로 확인합니다. DB 연결 문자열·토큰을 저장소에 넣지 않습니다.
5. `usp_start_review`는 상태와 이력을 한 트랜잭션으로 변경합니다. 이 실습의 팀별 `WHERE` 조회는 권한 분리(RLS)가 아니며, 운영 앱으로 확장할 때는 별도 인증·인가가 필요합니다.

## Purview 실습 준비 (07장)

**기본 실습은 레이블 적용만으로 구성할 수 있습니다.** DLP·카탈로그까지 모두 처음부터 참가자에게 구성시키는 것은 관리자 권한·라이선스·비동기 반영 때문에 재사용성이 낮습니다. 운영할 범위를 사전에 공지합니다.

| 범위 | 준비 사항 | 사전 확인 |
|---|---|---|
| 레이블 적용 | Fabric 정보 보호 설정, 참가자의 Pro/PPU·항목 편집 권한, 레이블 사용 가능한 그룹에 게시. Purview 정보 보호 라이선스는 조직 계약에 맞게 확인 | 실제 참가자 계정으로 `lh_cos`의 레이블 메뉴·저장·재열기 확인 |
| DLP 확장 | 정책 작성자에 지원 라이선스(M365 E5 / E5 Compliance / E5 Information Protection & Governance / Purview capacities 중 해당 조건)와 공식 문서의 관리 역할 필요. Fabric/Premium 용량 작업 영역만 대상으로 구성 | 신규 테넌트 온보딩에 몇 시간이 걸릴 수 있음. 수업 전에 조건 매치·정책 팁까지 확인 |
| 카탈로그 확장 | 별도의 Purview 계정·Fabric 연결·스캔·메타데이터 읽기 권한 및 해당 비용 확인 | 검색 가능한 자산을 미리 확보. 레이블 적용에는 카탈로그 스캔 불필요 |

실습 레이블 예시는 `Caldova-R&D-Confidential`입니다. 기존 조직 레이블이 맞으면 재사용하며 참가자에게 임의의 운영 레이블을 만들게 하지 않습니다. 새 레이블 게시·테넌트 설정·정책 전파를 수업 중 대기하는 구성은 피합니다.

**DLP 확장 구성:**

1. Purview → **Data loss prevention → Policies → Create policy → Custom**을 선택합니다.
2. 위치를 **Fabric and Power BI workspaces**로 하고 **실습 작업 영역만 명시적으로 포함**합니다. 전체 테넌트를 기본 범위로 둔 채 저장하지 않습니다.
3. 조건은 실습 민감도 레이블, 작업은 정책 팁·필요한 알림으로 설정합니다. 접근 차단은 사용하지 않습니다. 구성 모드와 알림 대상은 조직 정책에 맞게 승인받고, 실습 항목에서 정책 팁 표시가 되는지 실제 확인합니다.
4. Delta 데이터 변경 후 평가되는 흐름을 사전에 확인합니다. `01_prepare_data` 재실행은 `ops`를 초기화하므로 **승인 실습 전에** 평가용 데이터를 준비합니다.
5. 소유자용 DLP 상세·응답 화면은 Admin/Member 계정으로 확인합니다. 모든 참가자에게 Purview 관리자나 작업 영역 Admin을 주지 말고, 기본 Contributor는 레이블 적용을 수행하고 소유자 화면은 준비된 계정으로 함께 확인할 수 있습니다.
6. 실습에는 실제 개인정보나 배합 비밀을 넣지 않습니다. 배합비 자체가 민감 정보 유형 탐지에 걸린다고 가정하지 않고 레이블 조건을 사용합니다.

정책 적용·평가가 늦거나 라이선스가 없다면 기본 실습만 진행합니다. 미수행 확장을 수행 완료로 표시하지 않습니다. 실제 데이터 권한과 레이블 분류를 구분하며 모든 내보내기·복사본이 자동 보호된다고 설명하지 않습니다.

공식 근거: [레이블 적용·Pro/PPU 요구](https://learn.microsoft.com/en-us/fabric/fundamentals/apply-sensitivity-labels), [DLP 구성·역할·라이선스](https://learn.microsoft.com/en-us/fabric/governance/data-loss-prevention-configure), [DLP 지원 범위·평가·온보딩 제한](https://learn.microsoft.com/en-us/purview/dlp-powerbi-get-started).

## 로컬 점검(키트 유지보수자용)

**대상은 관리자·교재 유지보수자입니다. 참가자는 로컬 Python·Git 환경을 준비할 필요가 없습니다.** 아래 명령은 저장소 루트에서 실행합니다.

참가자에게는 [README](../README.md)와 `docs/`의 실습 절차를 안내합니다. 00장에서는 영향 대상 ID·건수를 미리 공개하지 않고 탐색 질문과 판단 근거를 기록하게 합니다. 단계별 예상 결과·참고 Notebook은 직접 실행 후 대조하는 데 사용합니다.

```powershell
python tools/build_notebooks.py
python tools/build_ontology.py
python tools/build_architecture.py
python -m unittest discover -s tests -v
```

Notebook·Ontology·아키텍처 산출물의 최신 여부, 문서 링크·Lesson 순서, CSV와 기대 영향 계산, 게시 SQL 생성 등을 오프라인으로 점검합니다. **Fabric 배포·SQL 엔진 동작·Teams 승인·Purview 정책 평가를 대신하지 않습니다.** 실제 테넌트 사전 점검을 별도로 수행합니다.

배포 정의는 `fabric/ont_cos_base`(시작 모델), `fabric/ont_cos_reference`(핵심 완성 모델), `fabric/ont_cos_extended`(선택 확장 모델)에 있습니다. 준비 Notebook의 기본 과정 실행은 관리자가 사전에 마치며, 참가자가 초기화를 요청하면 진행 중인 `ops` 결과 삭제 여부를 먼저 확인합니다.

아키텍처는 `tools/build_architecture.py`에서 수정한 뒤 SVG·Excalidraw를 함께 재생성합니다. 직접 편집은 [Microsoft Excalidraw](https://aka.ms/excalidraw)에서 가능하지만 생성기 변경 없이 산출물만 수정하면 재생성 시 덮어씁니다. 아이콘 원본·사용 조건은 [출처 문서](../assets/icon-attribution.md)에 보관합니다.

## 3. 사전 점검 체크리스트

실습 전에 `cos-p001` 같은 작업 영역에서 교재대로 전체를 한 번 실행하고 아래 값을 확인합니다.

| 장 | 확인할 값 |
|---|---|
| 준비 | 핵심 `gold` 테이블 11개(선택 확장 28개), `ops` 스키마 비어 있음. API 생성 모델의 경험·바인딩 확인 |
| 01 | 관계 10개, `FormulaVersion.is_active`, `RawMaterial.cn_registration` 추가 |
| 02 | Graph Q1 4행 → `is_active` 필터 3행, 생산 계획 `PP-1101`·`PP-1102`·`PP-1103`, `ST-0711` |
| 02 | `02_answers` Q5 지연 전 여유 8·15·64·3일 |
| 03 | Graph 없이도 `da_cos`가 Ontology 문맥으로 Lakehouse SQL 실행, 질문 1–3이 정답과 일치 |
| 04 | `03_supply_change`: `ops.material_impact` 4행 중 영향 3행(-27·-20·-32일), 이벤트 `SUP-20261102-RM-HA-120-r1` open 1행, Teams 메시지 5–10분 |
| 05 | `nb_apply_review` Succeeded, `ops.review_request` 3행, `ops.action_log` 1행, `open → review_requested` |
| 06 | `sqldb_cos` 요청 3행, 팀별 조회 2/1행, 검토 착수 후 이력 1행. 중복 착수는 오류, 재게시 0행 추가·검토중 상태 유지 |
| 07 기본 | 참가자 계정으로 `lh_cos` 레이블 적용·재열기 |
| 07 확장 | 구성한 범위에 한해 DLP 정책 팁 또는 카탈로그 검색을 확인 |
| 모델 확장 | 선택한 경우에만 `ont_cos_extended` 26개/40개, QX1–QX4 결과 2/1/3/3행. 기본 영향 3건 유지 |

## 4. 다시 시연하기

- 같은 작업 영역에서 04–05장을 다시 하려면 `03_supply_change`의 `run_tag`를 `r2`처럼 바꿔 실행합니다. ETA 지연은 원본 CSV 기준이라 누적되지 않습니다.
- 처음 상태로 되돌리려면 `01_prepare_data`를 `reset_ops = True`로 실행합니다. `gold` 테이블을 다시 만들고 `ops` 테이블을 지웁니다. Eventhouse 이력은 남으므로 새 `run_tag`를 씁니다.
- `03_supply_change` 실행 후 Graph에서 새 ETA를 보려면 Graph를 새로 고치거나 다시 Materialize합니다.
- **SQL DB는 `01_prepare_data` 초기화 대상이 아닙니다.** 새 이벤트를 쓰면 이전 업무 상태를 보존하며 반복할 수 있습니다. 완전 초기화가 필요하면 관리자 승인 아래 실습용 `sqldb_cos`만 재생성하고 `serving.sql`을 다시 실행합니다.

## 5. 정리

1. 참가자 `oa_cos`를 **Stop**합니다(5분마다 규칙 질의 실행).
2. 실습용 DLP 정책의 작업 영역 범위를 해제하고, 수업을 위해 만든 정책·레이블만 조직 승인 절차에 따라 정리합니다. 기존 운영 정책·레이블은 변경하지 않습니다.
3. 작업 영역 `cos-pNNN` 삭제 전 SQL DB의 실습 이력이 더 이상 필요 없는지 확인합니다. 삭제로 Ontology, Graph, Data agent, Operations agent, Eventhouse, Lakehouse, SQL DB가 함께 삭제 대상이 됩니다.
4. Purview 스캔·카탈로그 실습 자산과 별도 자원을 정리합니다. Teams·테넌트 설정은 수업을 위해 변경한 것만 승인받아 복원합니다.
