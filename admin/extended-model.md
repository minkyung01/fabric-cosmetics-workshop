# 26개 엔터티 확장 환경 준비

[목차](../README.md) \| [관리자 가이드](README.md) \| [미리 보기 제약·호환성](preview-limitations.md)

관리자용 준비 문서입니다. 참가자는 **07장 Purview까지 기본 과정을 마친 뒤** [Ontology 엔터티 확장 선택 실습](../docs/extensions/ontology.md)을 진행합니다.

참가자는 별도 완성 모델을 받는 대신 기존 `ont_cos`를 Agent와 확장합니다. 참고 범위는 **26개 엔터티·40개 관계**, 원본은 핵심 11개 + 추가 17개 = **28개 테이블**입니다. **00장 첫 실행 전에 `include_extended = True`로 설정하고, 모델 확장은 07장 이후로 미룹니다.** 관리자의 기본 준비는 빈 작업 영역과 접근 권한뿐입니다.

## 권장 준비 — 빈 작업 영역에서 참가자가 00장 준비·적재

1. **참가자가 00장을 시작하기 전에** 확장 선택 실습 제공 여부와 동일한 복붙용 코드 버전을 안내합니다.
2. 참가자가 00장에서 `lh_cos`·Notebook 5개 생성 → 코드 붙여넣기·매개변수 셀 지정·기본 연결을 직접 수행합니다. `01_prepare_data`의 첫 실행에서 `include_extended = True`, `reset_ops = False`로 28개 `gold` 테이블을 생성합니다.
3. `ont_cos`는 미생성 상태로 두고, 참가자가 01장에서 핵심 11개 테이블만으로 생성·보강하도록 합니다. 추가 테이블이 존재한다고 초기 모델에 모두 넣게 하지 않습니다.
4. 참가자 계정으로 원본 읽기와 01장 Agent 생성, 07장 완료 후의 확장 흐름을 리허설합니다. API 완성 모델 배포는 이 경로의 선행 조건이 아닙니다.

추가 17개 데이터도 준비 코드에 포함되어 있어 파일을 업로드하지 않습니다. **07장 이후 선택 실습을 시작하려고 준비 Notebook이나 준비 스크립트를 다시 실행하지 않습니다.** 기본 `reset_ops = False`는 기존 실습 테이블이 있으면 쓰기 전에 중지합니다. `reset_ops = True`로 바꾸면 기존 `gold`를 초기 데이터로 덮어쓰고 `ops` 승인 결과도 삭제하므로 모델 확장을 위해 사용하지 않습니다.

추가 데이터가 사전 준비되지 않았다면 선택 실습을 생략하거나 별도 복구 환경에서 진행합니다. 기본 과정의 승인·Serving 상태를 보존한 채 무심코 초기화를 반복하지 않습니다.

## 완성 참고 모델이 필요한 경우에만

비교·복구용 별도 `ont_cos_extended`가 필요하다면 새/기존 Ontology 경험과 REST 정의의 호환성을 [사전 점검](preview-limitations.md#2-새-ontology-경험과-api-배포-정의의-호환성)한 뒤 아래 옵션을 사용합니다. **참가자 선택 실습의 기본 경로는 아니며, 항목 정의 API 배포가 허용된 별도 환경에서만 사용합니다.** 파일 정책을 우회하는 경로로 사용하지 않습니다.

```powershell
python admin/provision.py --capacity <capacity-id> --prefix cos-rehearsal- --participants p001 --prefill-items --extended-ontology --run-prepare --dry-run
python admin/provision.py --capacity <capacity-id> --prefix cos-rehearsal- --participants p001 --prefill-items --extended-ontology --run-prepare
```

이 조합은 **관리자용 새 비교·복구 환경**에서 코드에 포함된 데이터로 28개 테이블 생성과 별도 확장 완성 모델 배포까지 수행하며 기존 핵심 `ont_cos`는 보존합니다. 새 작업 영역에서는 핵심 `ont_cos`를 생성하지 않습니다. 참가자용 기본 준비에는 `--run-prepare`나 완성 모델 배포를 사용하지 않습니다.

이미 준비한 작업 영역은 **`--update-notebooks`도 지정**해 최신 준비 Notebook을 배포해야 합니다. 기존 테이블이 있으면 기본 적재가 중지되므로 위 조합을 완료된 환경에 그대로 재실행하지 않습니다. 이미 원본 28개 테이블이 준비된 환경에서 적재 없이 모델을 배포할 때는 `--run-prepare`만 생략하고 `--prefill-items`는 유지합니다. 이 경로는 Notebook도 갱신할 수 있으므로 모델만 변경하는 동작이 아닙니다. `--skip-prepare`는 미실행 기본값과 같은 이전 명령 호환 옵션입니다. 기존 Ontology는 자동 덮어쓰기·마이그레이션하지 않습니다.

## 수동 준비와 재사용

완성 참고 모델을 수동 배포할 때는 `fabric/ont_cos_extended`를 별도 항목으로 가져옵니다. API 정의가 맞지 않는 새 경험에서는 [엔터티·원본·키 표](../docs/extensions/ontology.md#추가-엔터티와-바인딩)와 `tools/build_ontology.py`의 `EXTENDED_RELATIONSHIPS`를 기준으로 생성합니다. 생성에 실패한 모델을 완료로 표시하지 않습니다. 별도 모델을 쓴다면 `da_cos`의 연결을 조용히 바꾸지 말고 비교용 에이전트를 따로 둡니다.

확장 옵션을 뺐다고 이전 확장 파일·테이블이 자동 삭제되지는 않습니다. 핵심만으로 리허설할 때는 새 작업 영역을 사용합니다. 추가 데이터는 기준일 **2026-11-02의 고정 스냅샷**이며 핵심 Notebook이 갱신하거나 동기화하지 않습니다.

## 준비 완료 확인

- 기본 과정 시작 전 `ont_cos`는 미생성 상태이며, 01장에서는 핵심 모델만 만듭니다. 엔터티 확장은 07장 이후 선택 과정에만 있습니다.
- 참가자용 사전 준비는 빈 작업 영역·Contributor 접근 권한·코드 안내입니다. 별도 리허설에서 참가자의 00장 생성·코드 붙여넣기·실행 후 Lakehouse SQL endpoint로 `gold` 28개를 조회할 수 있는지 확인합니다.
- `fabric/sql/extended-queries.sql`의 QX1–QX4 결과는 각각 **2/1/3/3행**이며 [실습의 대조 결과](../docs/extensions/ontology.md#실습-2-lakehouse-sql로-업무-경로-확인)와 일치합니다.
- 핵심 영향 대상은 `PP-1101`, `PP-1102`, `ST-0711`로 유지됩니다. 추가 재고를 핵심 일정 영향 계산에 자동 합산하지 않습니다.
- 기존 `ont_cos` 확장 전후의 핵심 정의와 같은 데이터 시점의 기존 질문을 비교했습니다. `ops` 승인 결과·SQL 업무 상태가 보존됩니다.
- 참가자에게는 준비 명령 대신 [확장 실습 문서](../docs/extensions/ontology.md)를 안내합니다.
