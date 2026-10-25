# %% [markdown]
# # nb_apply_review — 승인된 원료 변경 검토 요청 기록
#
# Operations agent의 제안을 담당자가 Teams에서 **승인**하면 이 Notebook이 실행됩니다. 손으로 실행해도 결과는 같습니다.
#
# 1. Eventhouse `MaterialSupplyEvent`에서 이벤트의 최신 상태가 `open`인지 확인합니다.
# 2. `ops.material_impact`의 영향 대상마다 **원료 변경 검토 요청**을 `ops.review_request`에 등록합니다.
# 3. 조치 이력을 `ops.action_log`에 남기고, Eventhouse에 `review_requested` 상태 행을 추가합니다.
#
# 이 Notebook은 **구매 발주나 처방을 바꾸지 않습니다.** 검토 요청과 이력만 기록하고, 실제 변경은 담당 부서의 검토 절차를 따릅니다.
# 승인된 액션은 Operations agent를 만든 사람의 권한으로 실행됩니다.

# %% [parameters]
event_id = ""
material_code = ""
eventhouse_name = "eh_cos"

# %%
import pandas as pd
import requests
import sempy.fabric as fabric
from pyspark.sql import functions as F

if not event_id:
    raise ValueError("event_id 파라미터가 비어 있습니다. Operations agent 액션의 파라미터 설정을 확인하세요.")

approver = notebookutils.runtime.context.get("userName") or "unknown"
workspace_id = fabric.get_workspace_id()
eventhouses = fabric.FabricRestClient().get(f"v1/workspaces/{workspace_id}/eventhouses").json()["value"]
matches = [e for e in eventhouses if e["displayName"] == eventhouse_name]
if len(matches) != 1:
    raise ValueError(f"현재 작업 영역에 {eventhouse_name} Eventhouse가 정확히 1개 있어야 합니다.")
kusto_uri = matches[0]["properties"]["queryServiceUri"]
headers = {"Authorization": "Bearer " + notebookutils.credentials.getToken("kusto")}


def kql_text(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'" if value is not None else "''"


def kusto(endpoint, command):
    response = requests.post(f"{kusto_uri}/v1/rest/{endpoint}", headers=headers,
                             json={"db": eventhouse_name, "csl": command}, timeout=60)
    response.raise_for_status()
    result = response.json()
    if result.get("Exceptions"):
        raise RuntimeError(f"Kusto 요청 실패: {result['Exceptions']}")
    table = result["Tables"][0]
    return pd.DataFrame(table["Rows"], columns=[c["ColumnName"] for c in table["Columns"]])

# %% [markdown]
# ## 1. 이벤트 상태 확인
#
# **예상 결과:** `SUP-20261102-RM-HA-120-r1: 최신 상태 open` — 이미 `review_requested`면 아무것도 기록하지 않고 끝냅니다(중복 승인 방지).

# %%
latest = kusto("query", f"""MaterialSupplyEvent | where event_id == {kql_text(event_id)}
| summarize arg_max(event_time, *) by event_id""")
if latest.empty:
    raise ValueError(f"{event_id} 이벤트가 MaterialSupplyEvent에 없습니다.")
event = latest.iloc[0]
if material_code and material_code != event["material_code"]:
    raise ValueError(f"파라미터 원료({material_code})와 이벤트 원료({event['material_code']})가 다릅니다.")
material_code = event["material_code"]
status = event["event_status"]
print(f"{event_id}: 최신 상태 {status}")
already_done = status != "open"

# %% [markdown]
# ## 2. 검토 요청 등록 (`ops.review_request`)
#
# 영향 대상마다 1건씩 등록합니다. 생산 계획은 구매·생산 담당에게, 안정성 시험은 개발 과제 담당에게 요청합니다.
#
# **예상 결과:** 3행 — `RR-...-PP-1101`, `RR-...-PP-1102`, `RR-...-ST-0711`, 상태 `요청됨`.
# requested_by는 Notebook 실행 사용자이며 Teams 승인자 증빙은 아닙니다.

# %%
if not already_done:
    impact = spark.table("ops.material_impact").where((F.col("event_id") == event_id) & F.col("impacted"))
    if impact.count() == 0:
        raise ValueError(f"{event_id}의 영향 대상이 ops.material_impact에 없습니다. 03_supply_change를 먼저 실행하세요.")
    requests_df = (impact.select(
        F.concat(F.lit("RR-"), F.col("event_id"), F.lit("-"), F.col("target_id")).alias("request_id"),
        "event_id", "material_code", "target_type", "target_id", "product_id", "project_id", "version_id",
        F.when(F.col("target_type") == "생산계획", F.lit("구매·생산계획")).otherwise(F.lit("처방개발")).alias("assignee_team"),
        F.lit("원료 변경 검토").alias("request_type"), "slack_days", "suggestion",
        F.lit("요청됨").alias("request_status"), F.lit(approver).alias("requested_by"),
        F.current_timestamp().alias("requested_at")))
    if spark.catalog.tableExists("ops.review_request"):
        requests_df = requests_df.join(spark.table("ops.review_request").select("request_id"), "request_id", "left_anti")
        requests_df.write.mode("append").saveAsTable("ops.review_request")
    else:
        requests_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("ops.review_request")
display(spark.table("ops.review_request").where(F.col("event_id") == event_id).orderBy("target_id"))

# %% [markdown]
# ## 3. 조치 이력과 Eventhouse 상태
#
# **예상 결과:** `ops.action_log`에 `review_requested` 1행, Eventhouse에 같은 이벤트의 `review_requested` 행이 추가됩니다.

# %%
if not already_done:
    count = spark.table("ops.review_request").where(F.col("event_id") == event_id).count()
    note = f"검토 요청 {count}건 등록. 구매 발주·처방 변경 없음"
    log = spark.createDataFrame([(event_id, material_code, "review_requested", count, approver, note)],
                                "event_id string, material_code string, action string, request_count int, "
                                "action_by string, note string").withColumn("action_at", F.current_timestamp())
    log.write.mode("append").option("mergeSchema", "true").saveAsTable("ops.action_log")
    kusto("mgmt", f""".set-or-append MaterialSupplyEvent <|
print event_id = {kql_text(event_id)}, event_time = now(), event_status = 'review_requested',
      material_code = {kql_text(material_code)}, material_name = {kql_text(event['material_name'])},
      supplier_name = {kql_text(event['supplier_name'])}, original_eta = datetime({str(event['original_eta'])[:10]}),
      new_eta = datetime({str(event['new_eta'])[:10]}), delay_days = toint({int(event['delay_days'])}),
      impacted_count = toint({int(event['impacted_count'])}), impacted_targets = {kql_text(event['impacted_targets'])},
      updated_by = {kql_text(approver)}, note = {kql_text(note)}""")
    print(f"{event_id}: review_requested 기록 ({count}건)")

display(spark.table("ops.action_log").where(F.col("event_id") == event_id))
display(kusto("query", f"MaterialSupplyEvent | where event_id == {kql_text(event_id)} "
                       "| project event_time, event_status, updated_by, note | order by event_time asc"))
