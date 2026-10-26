# 관리자 준비 가이드

[목차](../README.md)

Workshop 환경을 준비하고 정리하는 관리자용 문서입니다. 참가자는 보지 않아도 됩니다. 예시는 `p001` 기준이며 참가자마다 `pNNN`을 바꿔 반복합니다. 데이터 구조와 정답은 [데이터 설계](data-design.md)를 봅니다.

**사전 필독:** [미리 보기 제약·호환성](preview-limitations.md). Ontology 새/기존 경험과 API 정의 호환성, **2027-01-31 기존 경험 종료**, Graph 선택 투영·적격성, Data Agent 문맥 갱신·권한, Operations Agent 감시·실행 권한을 확인합니다. [엔터티 확장 선택 실습](extended-model.md)을 제공한다면 00장 첫 실행 전에 `include_extended = True`로 설정하도록 안내하고, 모델 확장은 07장 Purview 완료 이후에만 진행합니다.

## 준비할 리소스

| 리소스 | 값 |
|---|---|
| Microsoft Fabric 용량 | **유료 F 용량**. Operations agent는 Trial 용량을 지원하지 않습니다. 12명 동시 실습 기준 F64 이상 권장 |
| 참가자 작업 영역 | 용량이 할당된 `cos-pNNN`에 **Notebook 5개만 준비**. 참가자에게 **본인 실습 작업 영역의 Contributor** 부여 |
| Lakehouse·데이터 | 참가자가 00장에서 스키마 지원 `lh_cos` 생성 → 코드에 포함된 고정 데이터로 `gold` 11개(선택 확장 포함 시 28개) 생성 |
| Notebook | 관리자가 모든 참가자 작업 영역에 `.ipynb` 5개를 미리 가져옴. 실행하지 않으며 기본 Lakehouse는 참가자가 연결 |
| Eventhouse | 사전 생성하지 않음. 참가자가 04장에서 `eh_cos` 생성, 같은 이름의 기본 KQL Database 자동 생성·이벤트 테이블 구성 |
| Ontology | 기본 준비에서는 **생성하지 않음**. 참가자가 01장에서 핵심 `ont_cos` 생성·보강. 07장 이후 선택 실습은 같은 항목을 확장하며 별도 완성 모델은 비교·복구용 |
| Microsoft Teams | 앱 **Fabric Operations Agent** 허용. 참가자는 Fabric과 **같은 계정**으로 Teams에 로그인 |
| SQL database | 사전 생성하지 않음. 참가자가 06장에서 본인 실습 작업 영역에 `sqldb_cos`와 Serving 스키마 직접 생성 |
| Microsoft Purview (07장) | 참가자 Pro/PPU·레이블 사용 권한·게시 정책. 선택 활동인 DLP 정책 팁 확인·카탈로그 자산 검색은 아래 별도 조건 확인 |

용량·테넌트 기능·Teams 앱·Purview 레이블/정책과 라이선스를 준비합니다. [실습 파일 ZIP](https://raw.githubusercontent.com/minkyung01/fabric-cosmetics-workshop/main/downloads/workshop-files.zip)의 `notebooks` 폴더에서 `.ipynb` 5개를 사용합니다. Lakehouse·데이터·Ontology·Eventhouse·SQL DB는 참가자가 직접 만듭니다.

**고객사 파일 정책:** Notebook 가져오기는 조직에서 허용된 관리자 환경에서 미리 수행합니다. 참가자는 파일을 업로드하거나 Notebook 코드를 복사하지 않으며, 준비 Notebook도 외부 파일을 다운로드하지 않습니다. 항목 정의 API를 파일 정책의 우회 수단으로 사용하지 않습니다. 가져오기 자체가 허용되지 않으면 `notebooks/paste`의 코드를 사용해 관리자가 대체 준비하고 매개변수 셀을 지정합니다.

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

## 2. 참가자 작업 영역과 Notebook 준비

`admin/provision.py`의 **기본 실행은 작업 영역 생성·용량 지정·참가자 접근 권한만 준비**합니다. 이후 관리자가 포털에서 Notebook 5개를 가져옵니다. 기본 스크립트는 실습 항목을 만들거나 변경하지 않으며 관리자 계정의 Azure CLI 로그인을 사용합니다.

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
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv --role Contributor --dry-run
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv --role Contributor
    ```

4. 각 작업 영역에서 **Import → Notebook**으로 `notebooks` 폴더의 `.ipynb` 5개를 가져옵니다. 이름은 `01_prepare_data`, `02_answers`, `03_supply_change`, `nb_apply_review`, `04_publish_serving`으로 유지합니다. **Notebook을 실행하거나 Lakehouse를 사전 생성하지 않습니다.**

**확인할 결과:** 스크립트의 `create workspace`·`assign Contributor …`·`workspace-only` 출력 후 수동 가져오기를 마치면, 각 작업 영역에 Notebook 5개가 보입니다. `nb_apply_review`의 매개변수 셀에 `event_id`, `material_code`, `eventhouse_name`이 있는지 확인합니다. `--users`를 생략하면 접근 권한은 별도로 부여합니다.

**참가자 권한:** 기본은 `Contributor`입니다. Member를 전체 과정의 필수 권한으로 고정하지 않습니다. SQL DB 권한 문서의 안내 차이와 실제 계정 사전 점검은 [아래 SQL 준비](#sql-serving-db-준비-06장)를 참고합니다. 기존 역할은 자동 승격·강등하지 않으므로 이미 Member/Admin인 계정이나 그룹 상속 권한은 따로 검토합니다. 운영 작업 영역이나 테넌트 권한은 늘리지 않습니다.

**기존 환경 재사용:** 기본 재실행은 CSV·Notebook·기존 항목·`gold`·`ops` 상태를 변경하지 않습니다. 준비된 Notebook을 중복 가져오거나 덮어쓰지 않고 버전·매개변수 셀을 확인합니다. 진행 중인 데이터가 있다면 삭제하지 말고 별도 실습 환경을 제공합니다. 기존 작업 영역의 용량은 포털에서 확인합니다.

**수동 준비:** 참가자별 작업 영역 생성 → 유료 F 용량 할당 → Contributor 부여 → Notebook 5개 가져오기. 참가자는 Lakehouse 생성·기본 연결·데이터 생성을 수행합니다. 동일한 Notebook 버전과 `include_extended` 설정을 안내합니다.

### 선택: 관리자 리허설·복구용 항목 사전 준비

Lakehouse·자체 데이터가 포함된 Notebook의 항목 정의 배포는 **`--prefill-items`를 명시할 때만** 실행하며 CSV를 업로드하지 않습니다. 참가자 기본 준비에는 사용하지 않습니다. 조직에서 API 배포를 허용한 별도 리허설·복구 환경에서만 사용합니다.

```powershell
python admin/provision.py --capacity <capacity-id> --prefix cos-rehearsal- --participants p001 --prefill-items --dry-run
python admin/provision.py --capacity <capacity-id> --prefix cos-rehearsal- --participants p001 --prefill-items
```

이 옵션만으로는 테이블을 적재하지 않습니다. `--run-prepare`를 추가할 때만 `01_prepare_data`를 실행하고, 완성 복구 모델도 필요하면 `--reference-ontology`를 추가합니다. 기존 준비 Notebook이 있으면 관리자 적재·확장 복구 경로에 `--update-notebooks`도 필요합니다. 기본 `reset_ops = False`는 기존 실습 테이블이 있으면 중지하므로 이 옵션을 강제 초기화로 쓰지 않습니다.

완성 복구 모델은 바인딩할 원본 테이블이 먼저 있어야 합니다. 새 복구 환경은 `--prefill-items --run-prepare --reference-ontology`를 함께 사용하고, 이미 적재된 원본이 있으면 적재 옵션을 생략합니다.

기존 Notebook은 `--update-notebooks`를 명시할 때만 교체합니다. 참가자 편집 내용을 먼저 보존하고, 테이블을 보존하려면 `--run-prepare`는 붙이지 않습니다. 이전 CSV 기반 테이블에는 `purchase_order.original_eta`가 없으므로 Notebook만 갱신해 호환된다고 가정하지 않습니다. 진행 중인 실습은 보존하고 별도 환경에서 최신 00장부터 준비합니다. 기존 `ont_cos`·`eh_cos`는 자동 삭제·초기화하지 않습니다.

| 옵션 | 용도 |
|---|---|
| `--prefill-items` | 승인된 관리자 리허설·복구 환경에 Lakehouse·자체 데이터를 포함한 Notebook을 배포. 생략하면 작업 영역·접근 권한만 준비 |
| `--reference-ontology` | `ont_cos`가 없을 때 완성 모델(`fabric/ont_cos_reference`)을 배포하는 **복구 경로**. 이미 있으면 보존하며 덮어쓰지 않음. Agent 생성 실습의 기본 준비 옵션이 아님 |
| `--extended-ontology` | 준비 Notebook을 `include_extended = True`로 설정하고 비교·복구용 별도 `ont_cos_extended` 완성 모델을 배포. 기존 작업 영역은 `--update-notebooks`도 필요([확장 가이드](extended-model.md)). |
| `--run-prepare` | 관리자 리허설·복구 환경에서만 `01_prepare_data` 실행을 명시적으로 요청. 참가자 기본 준비에는 사용하지 않음 |
| `--skip-prepare` | 이전 명령 호환용. 미실행이 이미 기본값이며 `--run-prepare`와 함께 사용할 수 없음 |
| `--update-notebooks` | 이미 있는 Notebook을 저장소 최신 버전으로 덮어씁니다. |
| `--prefix` | 작업 영역 이름 접두사(기본 `cos-`) |
| `--role` | 신규 참가자 역할 할당(기본 `Contributor`). 기존 역할은 자동 변경하지 않음 |
| `--tenant` | 여러 테넌트에 로그인한 경우 토큰을 받을 테넌트 |

`--run-prepare`·`--update-notebooks`·`--reference-ontology`·`--extended-ontology`는 **`--prefill-items`와 함께 사용해야 하며**, 빠뜨리면 변경 전에 인수 오류로 중지합니다. `--skip-prepare`만 이전 명령 호환용으로 단독 사용해도 아무 항목을 만들지 않습니다.

**01장 복구:** Agent 오류로 진행이 막혔다면 현재 정의·항목 ID와 작업 내용을 먼저 보존합니다. 호환성을 확인한 `fabric/ont_cos_reference`를 별도 복구 작업 영역에 배포하거나, 현재 항목에서 누락 부분을 수동 보완합니다. 복구 작업 영역도 Lakehouse 등 필요한 원본이 있어야 하며 API 배포 시 `{{WORKSPACE_ID}}`, `{{LAKEHOUSE_ID}}`를 해당 원본 ID로 치환합니다. 다른 Ontology 항목을 사용하면 이후 Graph·Data Agent 연결을 다시 확인합니다. `--reference-ontology`로 기존 `ont_cos`를 교체할 수는 없으며, 복구 모델 사용을 Agent 생성 완료로 표시하지 않습니다.

## Spark 세션 시작 점검

`Connecting`이 3분 지속됐다는 사실만으로 실패라고 판단하지 않습니다. [공식 Spark compute 문서](https://learn.microsoft.com/en-us/fabric/data-engineering/spark-compute)에 따르면 추가 라이브러리·사용자 지정 Spark 속성 없이 가용한 Starter pool을 쓰면 보통 5–10초지만, 온디맨드 클러스터 준비는 2–5분이 걸릴 수 있습니다. Starter pool 용량은 보장되지 않으며 환경 라이브러리 준비 시간은 별도로 추가될 수 있습니다.

1. **Workspace settings → Data Engineering/Science → Spark settings → Pool**에서 기본 풀과 노드 크기를 확인합니다. Starter pool은 Medium 노드만 지원하며 사용자 지정 풀·컴퓨트 설정은 시작 시간을 늘릴 수 있습니다.
2. Notebook의 **Environment**에서 실제 기본 환경·추가 라이브러리·Spark 속성을 확인합니다. 화면에 `Workspace default`가 표시된다고 가벼운 기본 환경이나 Starter pool을 보장하지는 않습니다.
3. **Tenant Private Links·Managed VNets**가 적용된 작업 영역은 Starter pool을 지원하지 않습니다. 이 경우 온디맨드 시작 대기를 일정에 반영하며, 속도를 위해 조직의 보안 설정을 해제하지 않습니다.
4. 장시간 같은 상태이거나 여러 참가자가 함께 지연되면 세션 정보·세션 ID·시작 시각·오류, 용량의 사용량·스로틀링과 서비스 상태를 확인합니다. 데이터 생성이 시작됐는지 확인하지 않고 준비 Notebook을 재실행하지 않습니다.

리허설에서는 **세션 준비 시간과 코드 실행 시간을 구분**해 기록합니다. 참가자는 00장에서 `01_prepare_data`에만 Lakehouse를 연결·저장한 뒤 **Connect**로 세션을 시작하고, 연결 완료 후 **Run all**을 누릅니다. 나머지 Notebook은 해당 장에서 Lakehouse를 연결합니다. 승인 액션용 `nb_apply_review`는 04장 Action 구성 전에 연결·저장하고 05장 승인 후 실행합니다.

## SQL Serving DB 준비 (06장)

1. 참가자별 **실습 작업 영역의 Contributor**를 기본으로 SQL database 생성 가능 여부를 확인합니다. 참가자용 `sqldb_cos`와 Serving 스키마는 사전 생성하지 않습니다.
2. 별도 리허설 작업 영역에서 실제 참가자와 같은 권한으로 [06장](../docs/06-serving-db.md)의 DB 생성 → [serving.sql](../fabric/sql/serving.sql) 실행 → SELECT·프로시저 실행을 확인합니다. 항목 생성과 SQL 실행 권한을 실제 계정으로 점검하며, Purview 관리자 권한으로 대체하지 않습니다.
3. 기존 DB를 재사용하는 복구 경로에서는 원본·항목 접근과 필요한 SQL 권한을 조직 절차에 따라 확인합니다. 이 경로를 참가자가 DB부터 직접 생성한 것으로 표시하지 않으며, 기존 요청·상태·이력을 삭제하지 않습니다.
4. `04_publish_serving`은 SQL 연결·전송을 하지 않습니다. 출력된 **게시 SQL을 참가자가 SQL DB에서 실행**하는 경로를 실제 계정으로 확인합니다. DB 연결 문자열·토큰을 저장소에 넣지 않습니다.
5. `usp_start_review`는 상태와 이력을 한 트랜잭션으로 변경합니다. 이 실습의 팀별 `WHERE` 조회는 권한 분리(RLS)가 아니며, 운영 앱으로 확장할 때는 별도 인증·인가가 필요합니다.

**권한 안내의 근거와 차이:** [작업 영역 역할 표](https://learn.microsoft.com/en-us/fabric/fundamentals/roles-workspaces)는 Contributor의 database 항목 생성·수정을 허용하고, [SQL DB 생성 API](https://learn.microsoft.com/en-us/rest/api/fabric/sqldatabase/items/create-sql-database)는 호출자에게 Contributor 역할을 요구합니다. [SQL DB 권한 문서](https://learn.microsoft.com/en-us/fabric/database/sql/authorization)도 Contributor의 전체 관리·데이터 접근을 설명합니다. 반면 [포털 생성 가이드](https://learn.microsoft.com/en-us/fabric/database/sql/create)의 전제에는 Admin/Member가 표기되어 있어 **공식 문서 간 안내가 상충합니다**. 따라서 Member 필수라고 단정하지 않으며, 포털 생성부터 SQL 실행까지 **실제 테넌트·참가자와 같은 Contributor 계정으로 사전 리허설**합니다. 거부되면 오류와 기능 지원·테넌트 설정·역할을 확인하고 조직 승인 절차로 해결합니다. API 권한만으로 포털 동작을 보장하거나 자동 승격하지 않으며, 오프라인 테스트로 실제 생성 성공을 검증했다고 표시하지 않습니다.

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
5. 소유자용 DLP 상세·응답 화면은 지원되는 별도 Admin/Member 계정으로 확인합니다. 참가자의 기본 Contributor 권한으로 이 화면까지 보장하지 않으며, 선택 활동의 화면 확인을 위해 모든 참가자를 승격하지 않습니다. Purview의 별도 관리 역할·라이선스도 구분합니다.
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

`build_notebooks.py`는 관리용 CSV를 준비 코드에 포함하고, Notebook 5개·복붙용 `notebooks/paste/*.md` 5개·**`downloads/workshop-files.zip`을 함께 재생성**합니다. CSV나 Notebook 원본이 바뀌면 다시 실행합니다. ZIP에는 CSV 28개·`.ipynb` 5개·복붙용 코드 문서 5개를 넣습니다. `python tools/build_notebooks.py --check`로 모든 산출물의 최신 여부를 확인합니다. 데이터는 ID·관계·날짜가 고정되며 무작위 생성하지 않습니다.

Notebook·다운로드 ZIP·Ontology·아키텍처 산출물의 최신 여부, 문서 링크·Lesson 순서, CSV와 기대 영향 계산, 게시 SQL 생성 등을 오프라인으로 점검합니다. **Fabric 배포·SQL 엔진 동작·Teams 승인·Purview 정책 평가를 대신하지 않습니다.** 실제 테넌트 사전 점검을 별도로 수행합니다.

보관된 정의는 `fabric/ont_cos_base`(이전 과정의 중간 복구 참고 모델), `fabric/ont_cos_reference`(핵심 완성 복구 모델), `fabric/ont_cos_extended`(선택 확장 완성 모델)입니다. **`ont_cos_base`는 기본 배포 대상이 아닙니다.** 준비 Notebook은 참가자가 00장에서 최초 실행합니다. 초기화가 필요한 경우에는 현재 `gold`·`ops` 상태를 확인하고 명시적으로 동의한 뒤 `reset_ops = True`를 사용합니다.

아키텍처는 `tools/build_architecture.py`에서 수정한 뒤 SVG·Excalidraw를 함께 재생성합니다. 직접 편집은 [Microsoft Excalidraw](https://aka.ms/excalidraw)에서 가능하지만 생성기 변경 없이 산출물만 수정하면 재생성 시 덮어씁니다. 아이콘 원본·사용 조건은 [출처 문서](../assets/icon-attribution.md)에 보관합니다.

## 3. 사전 점검 체크리스트

실습 전에 **별도 리허설 작업 영역**에서 참가자와 같은 Contributor 계정으로 교재 전체를 한 번 실행하고 아래 값을 확인합니다. 참가자용 작업 영역은 **Notebook 5개만 준비된 상태**로 남깁니다.

| 장 | 확인할 값 |
|---|---|
| 준비 | 유료 F 용량·Contributor 접근 권한·테넌트/Teams/Purview 공통 조건. Notebook 5개를 모든 참가자 작업 영역에 가져왔으며 Lakehouse·데이터는 미생성 |
| 00 | Notebook 5개 확인 → 스키마 지원 `lh_cos` 생성 → `01_prepare_data`에만 기본 연결 → 최초 실행. `gold` 11개/28개, `ops` 결과 테이블 없음. `PO-5501` ETA·original_eta 모두 11-10·확정. 기본 재실행이 쓰기 전에 중지하는지 확인 |
| 01 초안 | 참가자 계정으로 빈 항목 생성 → 짧은 업무 질문으로 Plan 초안 생성 → 최초 제안 기록·참고 설계와 대조 → 누락 시 보완·재검토 → Act 적용 → 저장된 키·바인딩·실제 행 확인 |
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
