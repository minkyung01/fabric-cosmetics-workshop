# %% [markdown]
# # 04_publish_serving — 승인 결과를 SQL Serving DB에 게시
#
# `nb_apply_review`가 기록한 검토 요청을 읽어 SQL 게시 명령을 만듭니다.
# **출력된 명령을 SQL database `sqldb_cos`의 쿼리 편집기에 붙여 넣고 실행**해야 게시됩니다.
# DB 연결·자동 동기화는 하지 않습니다. 비밀번호·토큰·배합비는 SQL에 넣지 않습니다.
# 먼저 `fabric/sql/serving.sql`로 테이블·프로시저를 준비합니다.

# %% [parameters]
event_id = "SUP-20261102-RM-HA-120-r1"

# %%
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

# %% [markdown]
# ## 1. 승인 결과 확인
#
# `ops.action_log`의 승인 조치와 요청 건수를 확인합니다.
# **예상 결과:** 이벤트 `r1`의 검토 요청 3건. 아직 승인하지 않았다면 오류로 중단합니다.

# %%
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

# %% [markdown]
# ## 2. SQL 생성 — DB에서 실행해야 게시 완료
#
# 아래 출력 전체를 `sqldb_cos`의 **SQL database 쿼리 편집기**에 붙여 넣고 실행합니다.
# SQL analytics endpoint는 읽기 전용이므로 쓰기 대상이 아닙니다.
# **예상 결과:** 최초 실행 `inserted_count = 3`, 같은 SQL 재실행 `inserted_count = 0`.
# Serving DB에서 바꾼 검토 상태는 재게시로 덮어쓰지 않습니다.

# %%
print(publish_sql)
print("-- 다음 단계: 위 EXEC 명령을 sqldb_cos에서 실행한 뒤 Lesson 06의 조회·상태 변경을 진행하세요.")
