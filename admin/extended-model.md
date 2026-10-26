# 26개 엔터티 확장 환경 준비

[목차](../README.md) \| [관리자 가이드](README.md) \| [미리 보기 제약·호환성](preview-limitations.md)

관리자용 준비 문서입니다. 참가자가 수행할 조회·질문·Graph 탐색은 [26개 엔터티 확장 실습](../docs/extensions/ontology.md)에 분리되어 있습니다.

핵심 `ont_cos`를 유지하면서 원료 로트·품질·재고·등록·설비·검토 담당을 연결하는 별도 `ont_cos_extended`를 추가합니다. 완성 모델은 **26개 엔터티·40개 관계**, 원본은 핵심 11개 + 추가 17개 = **28개 테이블**입니다.

## 사전 조건과 배포

**먼저 핵심 환경을 리허설합니다.** 새/기존 Ontology 경험과 REST 정의의 호환성을 [사전 점검](preview-limitations.md#2-새-ontology-경험과-api-배포-정의의-호환성)한 뒤 다음 옵션을 사용합니다.

```powershell
python admin/provision.py --capacity <capacity-id> --participants p001 --extended-ontology --dry-run
python admin/provision.py --capacity <capacity-id> --participants p001 --extended-ontology
```

기존 핵심 `ont_cos`는 보존하고 별도 확장 완성 모델만 추가합니다. 새 작업 영역에서는 핵심 `ont_cos`를 생성하지 않으며 참가자가 01장에서 만듭니다. 원본 CSV 11개에 `data/extended`의 17개를 더해 **같은 `Files/workshop/data` 폴더**에 업로드합니다. `01_prepare_data`는 확장 파일이 모두 있을 때 28개 테이블을 생성하며 일부만 있으면 오류로 중지합니다.

이미 준비한 작업 영역은 **`--update-notebooks`도 지정**해 새 준비 Notebook을 가져와야 합니다. 다시 실행하면 기본 `reset_ops = True`에 따라 승인 결과가 초기화되므로 **승인 실습 전**에 준비합니다. 기존 Ontology 항목은 자동 덮어쓰기·마이그레이션하지 않습니다. `--skip-prepare`를 지정했다면 `01_prepare_data`를 직접 실행해 확장 테이블을 확인한 후 바인딩을 사용합니다.

## 수동 준비와 재사용

수동 준비는 두 CSV 폴더의 파일을 모두 같은 목적지에 올리고 `01_prepare_data`를 실행한 뒤 `fabric/ont_cos_extended`를 별도 항목으로 배포합니다. API 정의가 맞지 않는 새 경험에서는 [엔터티·원본·키 표](../docs/extensions/ontology.md#추가-엔터티와-바인딩)와 `tools/build_ontology.py`의 `EXTENDED_RELATIONSHIPS`를 기준으로 수동 생성합니다. 생성에 실패한 모델을 완료로 표시하지 않습니다.

확장 옵션을 뺐다고 이전 확장 파일·테이블이 자동 삭제되지는 않습니다. 핵심만으로 리허설할 때는 새 작업 영역을 사용합니다. 추가 데이터는 기준일 **2026-11-02의 고정 스냅샷**이며 핵심 Notebook이 갱신하거나 동기화하지 않습니다.

## 준비 완료 확인

- 기존 `ont_cos`는 변경되지 않았으며, 새 작업 영역에서는 01장 생성용으로 미생성 상태입니다. 별도 `ont_cos_extended`에서 엔터티 26개·관계 40개·원본 바인딩을 확인했습니다.
- 참가자 계정의 Lakehouse SQL endpoint에서 `gold` 테이블 28개를 조회할 수 있습니다.
- `fabric/sql/extended-queries.sql`의 QX1–QX4 결과는 각각 **2/1/3/3행**이며 [실습의 대조 결과](../docs/extensions/ontology.md#실습-1-lakehouse-sql로-업무-경로-확인)와 일치합니다.
- 핵심 영향 대상은 `PP-1101`, `PP-1102`, `ST-0711`로 유지됩니다. 추가 재고를 핵심 일정 영향 계산에 자동 합산하지 않습니다.
- 참가자에게는 준비 명령 대신 [확장 실습 문서](../docs/extensions/ontology.md)를 안내합니다.
