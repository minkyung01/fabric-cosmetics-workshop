# 04_publish_serving — 복사할 코드

파일 가져오기가 허용되지 않는 환경의 대체 준비용입니다. 새 Notebook의 첫 코드 블록은 셀 메뉴의 `Toggle parameter cell`로 매개변수 셀로 지정하고, 두 번째 블록은 별도 코드 셀에 넣습니다.

[기본 Lakehouse 연결](../../docs/00-scenario.md#4-notebook에-기본-lakehouse-연결)

## 1. 매개변수 셀

```python
event_id = "SUP-20261102-RM-HA-120-r1"
```

## 2. 실행 코드 셀

```python
import json
from datetime import datetime
from pyspark.sql import functions as F


def build_publish_sql(event, records, approved_count):
    if not event or not records or len(records) != approved_count:
        raise ValueError("이벤트·검토 요청과 승인 조치의 건수가 일치해야 합니다.")
    fields = (
        "request_id", "material_code", "target_type", "target_id", "assignee_team",
        "slack_days", "suggestion", "request_status", "requested_by", "requested_at",
    )
    payload, seen = [], set()
    for record in records:
        if record["event_id"] != event or record["request_status"] != "요청됨":
            raise ValueError("동일 이벤트의 승인된 요청 스냅샷만 게시할 수 있습니다.")
        if record["request_id"] != f"RR-{event}-{record['target_id']}":
            raise ValueError("검토 요청 ID가 이벤트·대상과 일치하지 않습니다.")
        if record["request_id"] in seen:
            raise ValueError("게시할 검토 요청 ID가 중복됩니다.")
        seen.add(record["request_id"])
        row = {field: record[field] for field in fields}
        if not isinstance(row["requested_at"], datetime):
            raise ValueError("requested_at은 승인 Notebook이 기록한 timestamp여야 합니다.")
        row["requested_at"] = row["requested_at"].isoformat(timespec="microseconds")
        payload.append(row)
    requests_json = json.dumps(payload, ensure_ascii=False)
    literal = lambda value: "N'" + value.replace("'", "''") + "'"
    return (
        "EXEC serving.usp_publish_reviews\n"
        f"    @event_id = {literal(event)},\n"
        f"    @expected_count = {len(payload)},\n"
        f"    @requests = {literal(requests_json)};\n"
    )

for table in ("ops.review_request", "ops.action_log"):
    if not spark.catalog.tableExists(table):
        raise ValueError(f"{table}이 없습니다. nb_apply_review를 먼저 승인·실행하세요.")
requests_df = spark.table("ops.review_request").where(F.col("event_id") == event_id).orderBy("target_id")
actions = (spark.table("ops.action_log")
           .where((F.col("event_id") == event_id) & (F.col("action") == "review_requested"))
           .orderBy(F.col("action_at").desc()).limit(1).collect())
if not actions:
    raise ValueError(f"{event_id}의 승인 조치가 없습니다. 승인 전에는 게시하지 않습니다.")
records = [row.asDict() for row in requests_df.collect()]
publish_sql = build_publish_sql(event_id, records, actions[0].request_count)
display(requests_df.select("request_id", "target_id", "assignee_team", "request_status", "suggestion"))

print(publish_sql)
print("-- 다음 단계: 위 EXEC 명령을 sqldb_cos에서 실행한 뒤 Lesson 06의 조회·상태 변경을 진행하세요.")
```
