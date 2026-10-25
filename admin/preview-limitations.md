# Fabric 미리 보기 기능 — 제약과 사전 점검

[목차](../README.md) \| [관리자 가이드](README.md)

공식 문서 확인 기준은 **2026-10-25**입니다. 미리 보기의 UI·API·지원 범위는 변하므로 행사 전에 실제 테넌트와 참가자 계정으로 다시 확인합니다. 아래는 관리자·교재 유지보수자용이며 참가자가 테넌트 설정을 바꾸라는 뜻이 아닙니다.

## 1. Ontology와 Graph를 같은 것으로 설명하지 않기

**Lakehouse 직접 바인딩만으로 Ontology를 사용할 수 있습니다.** Ontology는 업무 대상·속성·관계·규칙·원본 매핑의 문맥 계층이며 일반적인 질의 실행 엔진이나 별도의 필수 데이터 저장소가 아닙니다. 소비자가 바인딩 정보를 사용해 실제 원본에 질의합니다. 스키마 관계 그림과 인스턴스 데이터의 Graph materialization도 다릅니다.

이 키트는 핵심 9개 엔터티와 선택 확장 26개 엔터티를 모두 `lh_cos.gold`에 바인딩합니다. Data Agent 기본 경로는 Ontology 문맥 → Lakehouse SQL입니다. 다단계 의존성·경로 자체를 탐색할 때 Graph를 선택적으로 만듭니다. 02장을 생략해도 03–07장을 진행할 수 있습니다.

## 2. 새 Ontology 경험과 API 배포 정의의 호환성

| 구분 | 공식 문서의 현재 동작 | 키트 운영 시 조치 |
|---|---|---|
| 새 UI | 새 경험이 기본이며 UI에서 기존 경험을 새로 만들 수 없음 | 화면·메뉴가 교재와 같은지 확인하고 수동 생성/바인딩 경로를 리허설 |
| 기존 경험 | API·CI/CD로 생성 가능하지만 **2027-01-31 종료 예정** | 기존 `entityType/dataBinding/relationshipType/contextualization` v1.0.0 정의를 새 경험의 모든 기능과 호환된다고 간주하지 않음 |
| 마이그레이션 | 기존 항목을 덮어쓰지 않고 새 항목의 **복사본** 생성 | 새 항목 ID와 원본·키·관계를 확인하고 downstream 에이전트·연결을 다시 지정 |
| 새 모델 기능 | 네임스페이스·상속·규칙·메트릭·다중 바인딩 등은 별도 확인 필요 | 이 키트는 단일 테이블 바인딩·명시적 키·기본 속성만 사용. 새 기능 자동 배포를 주장하지 않음 |

`admin/provision.py`는 저장소의 정의를 REST API로 제출하며 **새 경험으로 자동 마이그레이션하지 않습니다.** 핵심·확장 모델 모두 먼저 테스트 작업 영역에 배포해 열기·키·데이터 바인딩을 확인합니다. 기존 경험 의존 경로를 종료일 이후 그대로 재사용하지 않습니다.

API 정의를 수용하지 않는 환경은 오류를 무시하거나 빈 모델을 완성으로 표시하지 않습니다. [핵심 모델 표](../docs/01-ontology.md)와 [확장 모델 표](extended-model.md)를 기준으로 새 경험에서 엔터티와 Lakehouse 바인딩을 수동 생성하고, 관계 정의는 `tools/build_ontology.py`를 기준으로 연결합니다. 마이그레이션한 에이전트·규칙/Activator 알림은 연결·재생성 여부를 별도 점검합니다.

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

## 4. Data Agent

- Ontology는 **컨텍스트 원본**입니다. 실제 실행은 바인딩된 원본의 SQL/KQL/DAX이며 요청 사용자 권한을 사용합니다. Graph model을 별도로 연결한 경우에만 해당 원본의 GQL 경로와 구분합니다.
- 새 Ontology 문맥 경험은 preview runtime을 사전 확인합니다. 원본별 설명·질의 지침·예제는 지원되는 기반 원본을 마운트해 설정하며 Ontology로 역기록되지 않습니다.
- 문맥 자동 갱신은 **10분 주기**입니다. 모델 편집 직후에는 **Refresh**와 내려받은 문맥·실행 단계로 확인합니다.
- 초기 경험은 **Ontology 안의 엔터티 선택을 지원하지 않습니다.** 확장 26개 중 9개만 노출할 수 있다고 설명하지 않습니다. `ont_cos`와 `ont_cos_extended`를 별도 에이전트로 비교합니다.
- Data Agent는 원본을 최대 5개 연결합니다. 에이전트를 공유해도 기반 데이터 권한은 자동 부여되지 않습니다. Graph 원본도 노드·에지별 스키마 선택을 지원하지 않습니다.
- 잘못된 자연어 답은 성공으로 간주하지 않습니다. 핵심 질문은 `02_answers`, 확장 질문은 `extended-queries.sql`의 ID·행 수·상태와 비교합니다. Graph/SQL 원본 선택과 생성 질의를 기록합니다.

## 5. Operations Agent·Teams·승인 액션

- **유료 Fabric 용량**이 필요하고 Trial은 지원하지 않습니다. 테넌트 AI 설정, 지역별 AI 처리·저장 정책, Teams 앱·계정 허용을 미리 점검합니다. `F64`는 이 키트의 운영 권장안이지 모든 참가자 수에서 보장되는 공식 최소 용량이 아닙니다.
- 원본으로 Eventhouse 또는 Ontology를 지원하지만, 이 키트의 감시는 계산 결과를 담은 **Eventhouse**를 사용합니다. Ontology 직접 감시로 자동 바뀌지 않습니다.
- 규칙 질의는 **5분 주기**입니다. **Is open**은 상태가 유지되는 동안 반복될 수 있으므로 **Becomes open** 전이를 확인합니다. 프롬프트만 믿지 말고 생성 질의의 이벤트별 최신 상태·조건을 점검합니다.
- Agent ID가 있어도 실행은 **작성자 권한의 delegated/OBO** 경로입니다. Teams 수신자의 승인으로 실행 권한이 그 수신자로 바뀌지 않습니다. Notebook·Lakehouse·Eventhouse 권한을 작성자 기준으로 최소화합니다.
- 활동 화면은 현재 **Activity log**로 안내됩니다. 실습 UI와 이름이 다르면 실제 실행 상태·규칙·액션 기록을 확인합니다.
- `requested_by`는 Notebook 실행 사용자이지 Teams 승인자 증빙이 아닙니다. 실제 승인 감사는 Teams/에이전트 실행 기록과 조직 감사 정책을 별도로 확인합니다.

## 6. SQL Serving·Purview와 확인 범위

SQL DB는 Admin/Member가 사전 준비합니다. Lakehouse의 읽기 전용 SQL analytics endpoint와 쓰기 가능한 `sqldb_cos`를 혼동하지 않습니다. 게시 SQL 수동 실행은 자동 동기화·CDC가 아니며 팀별 WHERE 필터는 RLS가 아닙니다.

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
