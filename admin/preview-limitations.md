# Fabric 미리 보기 기능 — 제약과 사전 점검

[목차](../README.md) \| [관리자 가이드](README.md)

공식 문서 확인 기준은 **2026-10-26**입니다. 미리 보기의 UI·API·지원 범위는 변하므로 행사 전에 실제 테넌트와 참가자 계정으로 다시 확인합니다. 아래는 관리자·교재 유지보수자용이며 참가자가 테넌트 설정을 바꾸라는 뜻이 아닙니다.

## 1. Ontology와 Graph를 같은 것으로 설명하지 않기

**Lakehouse 직접 바인딩만으로 Ontology를 사용할 수 있습니다.** Ontology는 업무 대상·속성·관계·규칙·원본 매핑의 문맥 계층이며 일반적인 질의 실행 엔진이나 별도의 필수 데이터 저장소가 아닙니다. 소비자가 바인딩 정보를 사용해 실제 원본에 질의합니다. 스키마 관계 그림과 인스턴스 데이터의 Graph materialization도 다릅니다.

이 키트는 핵심 9개 엔터티와 선택 확장 26개 엔터티를 모두 `lh_cos.gold`에 바인딩합니다. Data Agent 기본 경로는 Ontology 문맥 → Lakehouse SQL입니다. 다단계 의존성·경로 자체를 탐색할 때 Graph를 선택적으로 만듭니다. 02장을 생략해도 03–07장을 진행할 수 있습니다.

## 2. 새 Ontology 경험과 API 배포 정의의 호환성

| 구분 | 공식 문서의 현재 동작 | 키트 운영 시 조치 |
|---|---|---|
| 새 UI | 새 경험이 기본이며 UI에서 기존 경험을 새로 만들 수 없음 | 기본 과정은 참가자가 새 빈 항목에서 Agent로 생성·보강. 실제 계정으로 원본 조사·미리 보기·Act 저장·Instances를 리허설 |
| 기존 경험 | API·CI/CD로 생성 가능하지만 **2027-01-31 종료 예정** | 기존 `entityType/dataBinding/relationshipType/contextualization` v1.0.0 정의를 새 경험의 모든 기능과 호환된다고 간주하지 않음 |
| 마이그레이션 | 기존 항목을 덮어쓰지 않고 새 항목의 **복사본** 생성 | 새 항목 ID와 원본·키·관계를 확인하고 downstream 에이전트·연결을 다시 지정 |
| 새 모델 기능 | 네임스페이스·상속·규칙·메트릭·다중 바인딩 등은 별도 확인 필요 | 이 키트는 단일 테이블 바인딩·명시적 키·기본 속성만 사용. 새 기능 자동 배포를 주장하지 않음 |

`admin/provision.py`의 **기본 실행은 작업 영역·접근 권한만 준비하며 Ontology를 만들지 않습니다.** 관리자 리허설·복구용 `--prefill-items`에 `--reference-ontology` 또는 `--extended-ontology`를 함께 명시했을 때만 저장소의 해당 정의를 REST API로 제출하며 **새 경험으로 자동 마이그레이션하지 않습니다.** 복구·확장 모델은 먼저 테스트 작업 영역에 배포해 열기·키·데이터 바인딩을 확인합니다. 기존 경험 의존 경로를 종료일 이후 그대로 재사용하지 않습니다.

API 정의를 수용하지 않는 환경은 오류를 무시하거나 빈 모델을 완성으로 표시하지 않습니다. [핵심 모델 표](../docs/01-ontology.md)와 [확장 모델 표](../docs/extensions/ontology.md#추가-엔터티와-바인딩)를 기준으로 새 경험에서 엔터티와 Lakehouse 바인딩을 수동 생성하고, 관계 정의는 `tools/build_ontology.py`를 기준으로 연결합니다. 마이그레이션한 에이전트·규칙/Activator 알림은 연결·재생성 여부를 별도 점검합니다.

## 3. 엔터티 개수보다 원본·투영·컨텍스트 제약을 확인

공식 문서에서 **25개 수준의 엔터티를 막는 소규모 상한은 확인하지 못했습니다.** 그렇다고 모든 테넌트에서 임의의 모델 크기·성능·정확도를 보장하는 것은 아닙니다. 확장 모델은 구조와 업무 경로를 보여 주는 소량 데이터이지 부하 시험이 아닙니다.

| 영역 | 구분해야 할 제약 | 운영 방법 |
|---|---|---|
| Ontology 바인딩 | 새 경험은 Lakehouse 외 원본과 다중 바인딩 등을 지원 | 원본 지원 = 모든 소비자·Graph에서 실행 가능이라는 뜻이 아님 |
| Graph 투영 | 키·엔터티/관계 매핑 필요. 현재 엔터티/관계별 단일 기반 테이블, Lakehouse·미러링 Delta 원본 중심 | 새 경험에서 키 없는 엔터티를 만들 수 있어도 Graph 적격성을 별도로 검사 |
| Graph 미지원/변환 | 의미 체계 모델 바인딩 엔터티는 투영 불가. 일부 형식·상속에 제한, 네임스페이스는 레이블 접두사에 반영 | Eligibility 상세와 실제 Graph 레이블을 확인. 예제 GQL도 실제 이름에 맞춤 |
| Graph 범위 | 전체 Ontology가 아닌 연결된 일부만 materialize 가능 | 먼저 핵심 9개·10개 관계만 투영. 확장은 필요한 경로만 선택 |
| Graph 갱신 | 원본 데이터 변경이 즉시 스냅샷에 반영되지 않음 | 원본 변경 후 Graph 항목 **… → Schedule → Refresh now**, 스키마 변경은 재투영 여부 확인 |
| Graph 조회 | 결과 64MB·중간 결과 128MB, 잘린 결과를 이어 받을 continuation token 없음. Query API 타임아웃 20분 | 조건·반환 열·범위를 줄이고 잘린 결과를 전체 결과로 해석하지 않음 |
| Graph 탐색 UI | 가변 길이 경로 빌더는 최대 8홉 | GQL 편집기 자체의 일괄 8홉 제한으로 설명하지 않음 |
| Graph 쓰기 | GQL DML/DDL 미지원 | 업무 갱신은 Notebook·SQL DB 등 원본에서 수행 |

## 4. Ontology Agent와 Data Agent

**Ontology Agent의 Plan 모드**는 발견·초안·검증·설명·원본 질의를 지원하지만 Ontology·작업 영역을 변경하지 않습니다. 설명이나 읽기 질의를 위해 Act로 전환시키지 않습니다. 적용할 변경을 검토한 뒤에만 Act를 사용합니다. 원본 접근은 사용자 권한을 따르며, 한 대화는 한 작업 영역의 한 Ontology를 대상으로 합니다. 핵심·확장 Ontology를 가로지르는 질의를 지원한다고 설명하지 않습니다.

01장은 **빈 항목의 생성 흐름과 기존 모델의 개선 흐름을 모두** 실습합니다. 첫 요청은 `lh_cos.gold`와 업무 질문에 더해, 배합 행·배합비 관리를 제외하고 `gold.formula_line`을 매핑으로 쓰는 `FormulaVersion → RawMaterial` 직접 관계를 명시합니다. 전체 엔터티 목록은 미리 지정하지 않되, 이 관계의 방향·키 매핑과 확인 가능한 원본 열·샘플 근거를 요청합니다. Agent의 도구에 따라 전체 필터·조인 질의가 불가능할 수 있으므로, 샘플에서 미확인인 제품을 “없음”으로 바꾸거나 전체 건수·키 중복·참조 누락 0건을 완료 조건으로 요구하지 않습니다. 미실행 데이터 검증과 미확인 설계 바인딩을 구분하며, 후자는 해결 전 승인하지 않습니다. 전체 처방 조회는 01장 6단계의 `02_answers` Q1에서 확인합니다. 초안을 기록한 뒤 핵심 7개 테이블의 참고 설계와 대조하고, 누락이나 범위 차이가 있으면 보완합니다. `FormulaLine → FormulaVersion` 방향 자체는 오류가 아니며, 양끝 속성·원본 바인딩 검토와 이번 실습의 단순화 기준을 구분합니다. 이후 일정·대체 검토에서는 나머지 핵심 4개 테이블을 추가하며, 선택 확장 17개·`ops`·Eventhouse는 모델 범위에서 제외합니다. AI가 고른 이름·개수·관계 방향은 고정 출력이 아니므로 초안의 질문별 원본 근거를 검토하고, 01장 5단계의 핵심 경로·이름·방향을 후속 GQL과 맞춥니다. 기존 ID와 바인딩을 보존하는 변경안인지 확인한 뒤 적용합니다. Agent의 샘플 해석과 모델에 경로가 저장되어 있는 것은 별개입니다.

미리 보기 버튼·표현은 UI에 따라 다를 수 있습니다. 텍스트 계획만 있는 경우 캔버스 미리 보기가 열린 것으로 설명하지 않습니다. 검증 실패·원본 읽기 오류가 남아 있으면 적용하지 않으며, 완료 문구 대신 저장된 정의와 실제 행으로 점검합니다. 새 항목을 만들지 못하는 환경은 API 완성 모델로 복구할 수 있더라도 Agent 생성 실습 완료로 보고하지 않습니다.

Ontology Agent의 기본 반환 한도는 SQL/KQL/GQL 1,000행, DAX 200행입니다. 응답이 전체 데이터라고 가정하지 말고 실제 질의·반환 범위를 확인합니다. 이번 실습의 4행 결과는 이 한도 안이며 `02_answers`와 대조합니다. 공식 근거는 [Ontology Agent의 Plan/Act·설명·질의·권한](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent)입니다.

**별도 Data Agent 항목의 제약**은 다음과 같습니다.

- Ontology는 **컨텍스트 원본**입니다. 실제 실행은 바인딩된 원본의 SQL/KQL/DAX이며 요청 사용자 권한을 사용합니다. Graph model을 별도로 연결한 경우에만 해당 원본의 GQL 경로와 구분합니다.
- 새 Ontology 문맥 경험은 preview runtime을 사전 확인합니다. 원본별 설명·질의 지침·예제는 지원되는 기반 원본을 마운트해 설정하며 Ontology로 역기록되지 않습니다.
- 문맥 자동 갱신은 **10분 주기**입니다. 모델 편집 직후에는 **Refresh**와 내려받은 문맥·실행 단계로 확인합니다.
- 초기 경험은 **Ontology 안의 엔터티 선택을 지원하지 않습니다.** 확장 26개 중 9개만 노출할 수 있다고 설명하지 않습니다. 기존 `ont_cos`의 확장은 07장 완료 이후 선택 실습에서만 수행하며, `da_cos` 문맥을 Refresh하고 같은 데이터 시점의 기존 질문을 재검증합니다. 별도 완성 모델은 비교·복구용이지 기본 실습의 필수 항목이 아닙니다.
- Data Agent는 원본을 최대 5개 연결합니다. 에이전트를 공유해도 기반 데이터 권한은 자동 부여되지 않습니다. Graph 원본도 노드·에지별 스키마 선택을 지원하지 않습니다.
- 잘못된 자연어 답은 성공으로 간주하지 않습니다. 핵심 질문은 `02_answers`, 확장 질문은 `extended-queries.sql`의 ID·행 수·상태와 비교합니다. Graph/SQL 원본 선택과 생성 질의를 기록합니다.

## 5. Operations Agent·Teams·승인 액션

- **유료 Fabric 용량**이 필요하고 Trial은 지원하지 않습니다. 테넌트 AI 설정, 지역별 AI 처리·저장 정책, Teams 앱·계정 허용을 미리 점검합니다. `F64`는 이 키트의 운영 권장안이지 모든 참가자 수에서 보장되는 공식 최소 용량이 아닙니다.
- 원본으로 Eventhouse 또는 Ontology를 지원하지만, 이 키트의 감시는 계산 결과를 담은 **Eventhouse**를 사용합니다. Ontology 직접 감시로 자동 바뀌지 않습니다.
- **Operations Agent의 지침과 업무 목표는 현재 영어만 지원**합니다. 04장의 영문 지침에서 한국어 알림 출력을 요청합니다. 실습 환경에서 한국어 알림 본문·규칙 설명 수신을 확인했으며, 제목·기본 레이블·버튼은 영어로 남을 수 있습니다.
- 규칙 질의는 **5분 주기**입니다. 기본 예시는 문자열 상태를 질의 계산 필드 `open_flag`의 0/1로 매핑한 **Crosses above 0.5**이며, 문자열의 **Changes to open**·불리언의 **Becomes true** 등 동등한 전환 조건도 가능합니다. 조건 이름보다 새 이벤트의 첫 `open` 감지와 같은 `event_id`의 상태 유지 중 반복 알림 여부를 확인합니다. **Is above** 같은 상태 조건과 반복 설정, 생성 질의의 이벤트별 최신 상태·조회 시간 범위·승인 액션을 점검합니다. 용어집 생성만으로 실제 알림 동작이 검증된 것은 아닙니다.
- Agent ID가 있어도 실행은 **작성자 권한의 delegated/OBO** 경로입니다. Teams 수신자의 승인으로 실행 권한이 그 수신자로 바뀌지 않습니다. Notebook·Lakehouse·Eventhouse 권한을 작성자 기준으로 최소화합니다.
- 활동 화면은 현재 **Activity log**로 안내됩니다. 실습 UI와 이름이 다르면 실제 실행 상태·규칙·액션 기록을 확인합니다.
- `requested_by`는 Notebook 실행 사용자이지 Teams 승인자 증빙이 아닙니다. 실제 승인 감사는 Teams/에이전트 실행 기록과 조직 감사 정책을 별도로 확인합니다.
- 승인 후 기록 확인은 `lh_cos`에 연결된 Notebook의 **읽기 전용 Spark SQL 조회**를 기본으로 합니다. 실습에서 `ops.review_request`가 Spark에서는 조회되지만 SQL 분석 엔드포인트에서는 `Invalid object name`이 발생했습니다. 승인 실패와 구분하고, SQL 메타데이터 동기화·노출 상태를 별도 확인합니다. 원인을 동기화 지연으로 단정하거나 확인을 위해 승인 Notebook을 재실행하지 않습니다.

## 6. SQL Serving·Purview와 확인 범위

SQL DB와 Serving 스키마는 참가자가 06장에서 직접 만듭니다. **기본 역할은 Contributor**입니다. 작업 영역 역할 표·SQL DB 생성 API는 Contributor를 허용하지만 포털 생성 가이드는 Admin/Member로 표기되어 있으므로, [공식 근거와 안내 차이](README.md#sql-serving-db-준비-06장)를 확인하고 실제 테넌트의 같은 권한 계정으로 DB 생성·SQL 실행을 리허설합니다. Member를 일괄 필수로 고정하거나 테넌트·Purview 관리자 권한을 부여하는 것으로 대체하지 않습니다. Lakehouse의 읽기 전용 SQL analytics endpoint와 쓰기 가능한 `sqldb_cos`를 혼동하지 않습니다. 게시 SQL 수동 실행은 자동 동기화·CDC가 아니며 팀별 WHERE 필터는 RLS가 아닙니다.

Purview 기본 실습은 게시된 레이블 적용입니다. Pro/PPU·레이블 게시/사용 권한·편집 권한을 실제 계정으로 확인합니다. DLP·카탈로그는 별도 라이선스·관리 역할·대상 범위·비동기 정책 평가/스캔이 필요하므로 사전 구성된 경우에만 수행합니다. 레이블·Ontology 설명이 접근 권한을 대신하지 않습니다.

로컬 점검은 JSON 구조·바인딩·참조 무결성·예제 조회 정답·생성물 일치를 확인합니다. **실제 Fabric API 수용 여부, 새 경험 마이그레이션, 에이전트 질의 정확도·성능, SQL 엔진, Teams 승인, Purview 정책 동작은 별도 테넌트 리허설 대상**입니다. 핵심 경로가 통과하지 않으면 확장 모델로 범위를 넓히지 않습니다.

## 공식 근거

- [Ontology 개요·새/기존 경험·마이그레이션](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview)
- [Ontology 데이터 바인딩](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-bind-data)
- [선택 Graph materialization·적격성·갱신](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-graph)
- [Graph 제한사항](https://learn.microsoft.com/en-us/fabric/graph/limitations)
- [Data Agent의 Ontology 문맥·갱신·권한](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-ontology-sources)
- [Data Agent 지원 원본·구성 범위](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-add-datasources)
- [Operations Agent 요구 사항·감시·권한](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent)
- [Operations Agent 승인 액션](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/operations-agent-actions)
- [민감도 레이블 적용 조건](https://learn.microsoft.com/en-us/fabric/fundamentals/apply-sensitivity-labels)
- [DLP 정책 구성](https://learn.microsoft.com/en-us/fabric/governance/data-loss-prevention-configure)
