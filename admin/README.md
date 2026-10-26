# 관리자 준비 가이드

[목차](../README.md)

Workshop 환경을 준비하고 정리하는 관리자용 문서입니다. 참가자는 보지 않아도 됩니다. 예시는 `p001` 기준이며 참가자마다 `pNNN`을 바꿔 반복합니다. 데이터 구조와 정답은 [데이터 설계](data-design.md)를 봅니다.

**사전 필독:** [미리 보기 제약·호환성](preview-limitations.md). Ontology 새/기존 경험과 API 정의 호환성, **2027-01-31 기존 경험 종료**, Graph 선택 투영·적격성, Data Agent 문맥 갱신·권한, Operations Agent 감시·실행 권한을 확인합니다. [엔터티 확장 선택 실습](extended-model.md)을 제공한다면 추가 CSV는 기본 과정 전에 배치하고, 참가자가 00장에서 테이블을 적재한 뒤 모델 확장은 07장 Purview 완료 이후에만 진행합니다.

## 준비할 리소스

| 리소스 | 값 |
|---|---|
| Microsoft Fabric 용량 | **유료 F 용량**. Operations agent는 Trial 용량을 지원하지 않습니다. 12명 동시 실습 기준 F64 이상 권장 |
| 참가자 작업 영역 | `cos-pNNN` (전체 과정 참가자는 **본인 실습 작업 영역의 Member**. 06장 SQL DB 생성에 필요하며 테넌트·운영 작업 영역 권한과 구분) |
| Lakehouse | `lh_cos` (**schemas 켬**), `Files/workshop/data`에 핵심 CSV 11개. 선택 확장은 17개 추가, 총 28개. `gold` 테이블은 사전 생성하지 않고 참가자가 00장에서 적재 |
| Notebook | `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review`, `04_publish_serving` |
| Eventhouse | 사전 생성하지 않음. 참가자가 04장에서 `eh_cos` 생성, 같은 이름의 기본 KQL Database 자동 생성·이벤트 테이블 구성 |
| Ontology | 기본 준비에서는 **생성하지 않음**. 참가자가 01장에서 핵심 `ont_cos` 생성·보강. 07장 이후 선택 실습은 같은 항목을 확장하며 별도 완성 모델은 비교·복구용 |
| Microsoft Teams | 앱 **Fabric Operations Agent** 허용. 참가자는 Fabric과 **같은 계정**으로 Teams에 로그인 |
| SQL database | 사전 생성하지 않음. 참가자가 06장에서 본인 실습 작업 영역에 `sqldb_cos`와 Serving 스키마 직접 생성 |
| Microsoft Purview (07장) | 참가자 Pro/PPU·레이블 사용 권한·게시 정책. 선택 활동인 DLP 정책 팁 확인·카탈로그 자산 검색은 아래 별도 조건 확인 |

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

`admin/provision.py`가 참가자마다 작업 영역, 스키마 사용 Lakehouse, CSV 업로드와 실행 전 Notebook 5개를 준비합니다. **기본 실행은 `01_prepare_data`를 실행하지 않으며 `gold`를 적재하지 않습니다.** 참가자가 00장에서 준비 Notebook으로 `gold` 테이블을 만들고, 01장에서 `ont_cos`, 04장에서 `eh_cos`와 이벤트 테이블, 06장에서 `sqldb_cos`와 Serving 스키마를 직접 만듭니다. **관리자는 항목 생성 권한과 Purview 정책·레이블을 사전 준비합니다.** 이미 있는 항목은 다시 만들지 않습니다. 관리자 계정의 Azure CLI 로그인을 사용하며 비밀 값을 저장하지 않습니다.

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
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv --role Member --dry-run
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv --role Member
    ```

**확인할 결과:** 새 참가자 작업 영역마다 `create workspace`, `create lakehouse lh_cos (schemas)`, `upload Files/workshop/data (11 csv)`, `import notebook …` 5줄이 출력됩니다. **`run 01_prepare_data: completed`는 기본 경로에서 나오지 않고**, `leave gold-table loading to participants in chapter 00` 안내가 표시됩니다. `gold`·`ops`의 실습 테이블과 `ont_cos`·`eh_cos`·`sqldb_cos`는 미생성 상태로 남깁니다. `--dry-run`에서도 00장 적재·01장 Ontology·04장 Eventhouse 생성 안내를 확인합니다.

**참가자 권한:** 전체 과정은 명시적으로 `--role Member`를 사용합니다. 스크립트의 기본값 `Contributor`는 유지하지만 06장 DB 생성에는 부족합니다. 기존 역할 할당은 이 옵션으로 자동 승격하지 않으므로, 이미 Contributor인 참가자는 관리자 승인 절차로 **해당 실습 작업 영역만 Member로 변경**한 뒤 실제 계정에서 확인합니다. 운영 작업 영역이나 테넌트 권한은 늘리지 않습니다.

**기존 환경 재사용:** 이전 버전이 배포했거나 참가자가 만든 `ont_cos`는 자동 삭제·초기화하지 않으며, 기본 실행 시 기존 항목 보존과 새 생성 실습용 작업 영역 필요를 출력합니다. 처음부터 생성하는 과정은 새 작업 영역에서 준비합니다. **기본 재실행은 준비 Notebook을 실행하지 않아 기존 `gold`·`ops` 상태를 초기화하지 않습니다.** CSV는 다시 업로드되므로 입력 파일 변경 여부를 확인하고, 기존 Notebook은 `--update-notebooks`를 명시할 때만 교체합니다.

이전 교재로 준비한 작업 영역에 새 적재 절차를 적용하려면 **`--update-notebooks`로 최신 준비 Notebook과 재실행 보호를 반영**합니다. `--run-prepare`는 붙이지 않습니다. 기존 테이블이 자동으로 비워지는 것은 아니므로, 생성부터 진행할 참가자에게는 새 작업 영역을 제공합니다. 참가자 편집 내용이 있으면 Notebook 교체 전에 보존합니다.

**관리자 리허설·복구:** 새 별도 환경에서 관리자가 테이블까지 적재해야 할 때만 `--run-prepare`를 명시합니다. 기존 준비 Notebook이 있으면 `--update-notebooks`도 필요합니다. 최신 Notebook의 기본 `reset_ops = False`는 기존 실습 테이블이 있으면 중지하므로, 이 옵션을 데이터 강제 초기화로 사용하지 않습니다. 복구 모델을 배포할 때는 원본 테이블이 먼저 있어야 하며, 새 복구 환경은 `--reference-ontology --run-prepare`를 함께 사용합니다.

기존 `eh_cos`도 삭제하거나 다시 생성하지 않습니다. 참가자가 기존 항목을 재사용하면 데이터베이스 이름·테이블·이력을 확인하고, 새 이벤트에는 새 `run_tag`를 사용합니다. Eventhouse 생성부터 진행할 환경은 새 작업 영역으로 준비합니다.

| 옵션 | 용도 |
|---|---|
| `--reference-ontology` | `ont_cos`가 없을 때 완성 모델(`fabric/ont_cos_reference`)을 배포하는 **복구 경로**. 이미 있으면 보존하며 덮어쓰지 않음. Agent 생성 실습의 기본 준비 옵션이 아님 |
| `--extended-ontology` | 비교·복구용 별도 `ont_cos_extended` 완성 모델과 확장 CSV 17개를 준비하는 옵션. 기존 작업 영역은 `--update-notebooks`도 필요. 기본 과정 시작 전에만 실행하며, 데이터만 준비하는 권장 경로와 구분합니다([확장 가이드](extended-model.md)). |
| `--run-prepare` | 관리자 리허설·복구 환경에서만 `01_prepare_data` 실행을 명시적으로 요청. 참가자 기본 준비에는 사용하지 않음 |
| `--skip-prepare` | 이전 명령 호환용. 미실행이 이미 기본값이며 `--run-prepare`와 함께 사용할 수 없음 |
| `--update-notebooks` | 이미 있는 Notebook을 저장소 최신 버전으로 덮어씁니다. |
| `--prefix` | 작업 영역 이름 접두사(기본 `cos-`) |
| `--role` | 신규 참가자 역할 할당(기본 `Contributor`). 전체 과정은 `Member` 명시. 기존 역할은 자동 변경하지 않음 |
| `--tenant` | 여러 테넌트에 로그인한 경우 토큰을 받을 테넌트 |

**수동 준비:** 작업 영역을 만들고 용량에 할당한 뒤 참가자를 해당 실습 작업 영역의 Member로 추가합니다. `lh_cos`를 **Lakehouse schemas** 켜고 만들고 `Files/workshop/data`에 `data/*.csv`를 올립니다. 07장 이후 선택 실습을 제공한다면 `data/extended/*.csv`도 같은 위치에 **미리** 올립니다. `notebooks/*.ipynb` 5개를 가져와 기본 Lakehouse를 `lh_cos`로 연결하되 **`01_prepare_data`는 실행하지 않습니다.** 참가자가 00장에서 최초 적재합니다. **Ontology·Eventhouse·SQL DB도 미생성 상태로 남깁니다.** 별도 리허설 작업 영역에서 00장 참가자 적재부터 전체 흐름을 확인합니다.

**01장 복구:** Agent 오류로 진행이 막혔다면 현재 정의·항목 ID와 작업 내용을 먼저 보존합니다. 호환성을 확인한 `fabric/ont_cos_reference`를 별도 복구 작업 영역에 배포하거나, 현재 항목에서 누락 부분을 수동 보완합니다. 복구 작업 영역도 Lakehouse 등 필요한 원본이 있어야 하며 API 배포 시 `{{WORKSPACE_ID}}`, `{{LAKEHOUSE_ID}}`를 해당 원본 ID로 치환합니다. 다른 Ontology 항목을 사용하면 이후 Graph·Data Agent 연결을 다시 확인합니다. `--reference-ontology`로 기존 `ont_cos`를 교체할 수는 없으며, 복구 모델 사용을 Agent 생성 완료로 표시하지 않습니다.

## SQL Serving DB 준비 (06장)

1. 참가자별 **실습 작업 영역의 Member** 권한과 SQL database 생성 가능 여부를 확인합니다. 참가자용 `sqldb_cos`와 Serving 스키마는 사전 생성하지 않습니다.
2. 별도 리허설 작업 영역에서 실제 참가자와 같은 권한으로 [06장](../docs/06-serving-db.md)의 DB 생성 → [serving.sql](../fabric/sql/serving.sql) 실행 → SELECT·프로시저 실행을 확인합니다. 항목 생성과 SQL 실행 권한을 실제 계정으로 점검하며, Purview 관리자 권한으로 대체하지 않습니다.
3. 기존 DB를 재사용하는 복구 경로에서는 원본·항목 접근과 필요한 SQL 권한을 조직 절차에 따라 확인합니다. 이 경로를 참가자가 DB부터 직접 생성한 것으로 표시하지 않으며, 기존 요청·상태·이력을 삭제하지 않습니다.
4. `04_publish_serving`은 SQL 연결·전송을 하지 않습니다. 출력된 **게시 SQL을 참가자가 SQL DB에서 실행**하는 경로를 실제 계정으로 확인합니다. DB 연결 문자열·토큰을 저장소에 넣지 않습니다.
5. `usp_start_review`는 상태와 이력을 한 트랜잭션으로 변경합니다. 이 실습의 팀별 `WHERE` 조회는 권한 분리(RLS)가 아니며, 운영 앱으로 확장할 때는 별도 인증·인가가 필요합니다.

## Purview 실습 준비 (07장)

**기본 실습은 레이블 적용만으로 구성할 수 있습니다.** DLP·카탈로그까지 모두 처음부터 참가자에게 구성시키는 것은 관리자 권한·라이선스·비동기 반영 때문에 재사용성이 낮습니다. 운영할 범위를 사전에 공지합니다.

| 범위 | 준비 사항 | 사전 확인 |
|---|---|---|
| 레이블 적용 | Fabric 정보 보호 설정, 참가자의 Pro/PPU·항목 편집 권한, 레이블 사용 가능한 그룹에 게시. Purview 정보 보호 라이선스는 조직 계약에 맞게 확인 | 실제 참가자 계정으로 `lh_cos`의 레이블 메뉴·저장·재열기 확인 |
| 선택: DLP 정책 팁 확인 | 정책 작성자에 지원 라이선스(M365 E5 / E5 Compliance / E5 Information Protection & Governance / Purview capacities 중 해당 조건)와 공식 문서의 관리 역할 필요. Fabric/Premium 용량 작업 영역만 대상으로 구성 | 신규 테넌트 온보딩에 몇 시간이 걸릴 수 있음. 수업 전에 조건 매치·정책 팁까지 확인 |
| 선택: 카탈로그 자산 검색 | 별도의 Purview 계정·Fabric 연결·스캔·메타데이터 읽기 권한 및 해당 비용 확인 | 검색 가능한 자산을 미리 확보. 레이블 적용에는 카탈로그 스캔 불필요 |

실습 레이블 예시는 `Caldova-R&D-Confidential`입니다. 기존 조직 레이블이 맞으면 재사용하며 참가자에게 임의의 운영 레이블을 만들게 하지 않습니다. 새 레이블 게시·테넌트 설정·정책 전파를 수업 중 대기하는 구성은 피합니다.

**DLP 정책 팁 확인을 위한 정책 구성:**

1. Purview → **Data loss prevention → Policies → Create policy → Custom**을 선택합니다.
2. 위치를 **Fabric and Power BI workspaces**로 하고 **실습 작업 영역만 명시적으로 포함**합니다. 전체 테넌트를 기본 범위로 둔 채 저장하지 않습니다.
3. 조건은 실습 민감도 레이블, 작업은 정책 팁·필요한 알림으로 설정합니다. 접근 차단은 사용하지 않습니다. 구성 모드와 알림 대상은 조직 정책에 맞게 승인받고, 실습 항목에서 정책 팁 표시가 되는지 실제 확인합니다.
4. 별도 리허설에서 Delta 데이터 변경 후 평가되는 흐름을 확인합니다. `01_prepare_data`의 기본 재실행은 중지되고, `reset_ops = True` 초기화는 승인 결과를 삭제합니다. 참가자 환경의 첫 적재는 00장에서 수행하고, 정책 평가를 위해 완료된 승인 데이터를 초기화하지 않습니다.
5. 소유자용 DLP 상세·응답 화면은 지원되는 Admin/Member 계정으로 확인합니다. 06장 DB 생성을 위한 실습 작업 영역의 Member 권한과 Purview의 별도 관리 역할·라이선스를 구분합니다. 모든 참가자에게 Purview 관리자나 작업 영역 Admin을 주지 않습니다.
6. 실습에는 실제 개인정보나 배합 비밀을 넣지 않습니다. 배합비 자체가 민감 정보 유형 탐지에 걸린다고 가정하지 않고 레이블 조건을 사용합니다.

정책 적용·평가가 늦거나 라이선스가 없다면 기본 실습만 진행합니다. 미수행 선택 활동을 수행 완료로 표시하지 않습니다. 실제 데이터 권한과 레이블 분류를 구분하며 모든 내보내기·복사본이 자동 보호된다고 설명하지 않습니다.

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

보관된 정의는 `fabric/ont_cos_base`(이전 과정의 중간 복구 참고 모델), `fabric/ont_cos_reference`(핵심 완성 복구 모델), `fabric/ont_cos_extended`(선택 확장 완성 모델)입니다. **`ont_cos_base`는 기본 배포 대상이 아닙니다.** 준비 Notebook은 참가자가 00장에서 최초 실행합니다. 초기화가 필요한 경우에는 현재 `gold`·`ops` 상태를 확인하고 명시적으로 동의한 뒤 `reset_ops = True`를 사용합니다.

아키텍처는 `tools/build_architecture.py`에서 수정한 뒤 SVG·Excalidraw를 함께 재생성합니다. 직접 편집은 [Microsoft Excalidraw](https://aka.ms/excalidraw)에서 가능하지만 생성기 변경 없이 산출물만 수정하면 재생성 시 덮어씁니다. 아이콘 원본·사용 조건은 [출처 문서](../assets/icon-attribution.md)에 보관합니다.

## 3. 사전 점검 체크리스트

실습 전에 `cos-p001` 같은 작업 영역에서 교재대로 전체를 한 번 실행하고 아래 값을 확인합니다.

| 장 | 확인할 값 |
|---|---|
| 준비 | 빈 Lakehouse·핵심 CSV 11개(선택 확장 28개)·실행 전 Notebook 5개. `gold`·`ops` 실습 테이블과 `ont_cos`·`eh_cos`·`sqldb_cos` 미생성. 참가자별 실습 작업 영역 Member 확인 |
| 00 | 참가자 계정으로 `01_prepare_data` 최초 실행 → `gold` 11개(확장 포함 시 28개), `ops` 결과 테이블 없음. `PO-5501` ETA 11-10·확정. 기본 재실행이 기존 테이블을 쓰기 전에 중지하는지 확인 |
| 01 초안 | 참가자 계정으로 빈 항목 생성 → Plan 원본 조사·초안 검토 → Act 적용 → 저장된 키·바인딩·실제 행 확인 |
| 01 보강 | 생산·개발 일정과 대체 검토 질문으로 빈틈 진단 → Plan 변경안 → Act 적용. 핵심 참고 9개/10개 경로와 `is_active`, `cn_registration` 바인딩·Plan 질의 확인 |
| 02 | Graph Q1 4행 → `is_active` 필터 3행, 생산 계획 `PP-1101`·`PP-1102`·`PP-1103`, `ST-0711` |
| 02 | `02_answers` Q5 지연 전 여유 8·15·64·3일 |
| 03 | Graph 없이 `da_cos`가 Ontology 문맥으로 Lakehouse SQL 실행. 6개 유형·12문항의 답과 근거를 `02_answers`와 대조. 0일 경계·대체 후보의 세 조건·QC 변경·판단 한계 확인 |
| 04 생성 | 참가자 계정으로 Eventhouse·기본 KQL Database를 모두 `eh_cos` 이름으로 생성. `MaterialSupplyEvent` 13개 열·초기 0행, Notebook 쓰기 확인 |
| 04 | `03_supply_change`: `ops.material_impact` 4행 중 영향 3행(-27·-20·-32일), 이벤트 `SUP-20261102-RM-HA-120-r1` open 1행, Teams 메시지 5–10분 |
| 05 | `nb_apply_review` Succeeded, `ops.review_request` 3행, `ops.action_log` 1행, `open → review_requested` |
| 06 | 참가자 계정으로 `sqldb_cos`·Serving 스키마 직접 생성. 요청 3행, 팀별 조회 2/1행, 검토 착수 후 이력 1행. 중복 착수는 오류, 재게시 0행 추가·검토중 상태 유지 |
| 07 기본 | 참가자 계정으로 `lh_cos` 레이블 적용·재열기 |
| 07 선택 활동 | 구성한 범위에 한해 DLP 정책 팁 확인 또는 카탈로그 자산 검색 수행. 이후 Ontology 엔터티 확장과 구분 |
| 07장 이후 선택 확장 | 기존 `ont_cos`를 Agent와 보강(참고 26개/40개). QX1–QX4 결과 2/1/3/3행, 기존 질문 재검증, 기본 영향·승인·SQL 상태 보존 |

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
