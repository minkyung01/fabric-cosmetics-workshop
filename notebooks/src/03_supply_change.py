# %% [markdown]
# # 03_supply_change — 원료 공급 지연 반영과 영향 분석
#
# 공급사가 알려 온 **입고 지연**을 실습 데이터에 반영하고, 영향받는 생산 계획·개발 과제를 계산해 Eventhouse로 보냅니다.
#
# 1. `gold.purchase_order`의 해당 원료 발주 입고 예정일을 늦추고 상태를 `지연`으로 바꿉니다.
# 2. 원료 필요일(생산 계획일·안정성 시험 배치일 − QC 리드타임)과 새 입고 예정일을 비교해 `ops.material_impact`를 만듭니다.
# 3. 영향 대상이 있으면 Eventhouse `eh_cos`의 `MaterialSupplyEvent`에 `open` 상태 이벤트 1건을 추가합니다.
#
# 영향 분석은 **이 Notebook의 명시적인 계산**으로 정하고, Operations agent는 그 결과를 근거로 알리고 제안합니다.
# 이 Notebook은 실제 구매·처방을 바꾸지 않습니다.
#
# **시작 전:** 4장에서 `MaterialSupplyEvent` 테이블을 만들고 Operations agent를 **Start**한 다음 실행합니다.

# %% [parameters]
material_code = "RM-HA-120"
delay_days = 35
as_of_date = "2026-11-02"
qc_lead_days = 7
run_tag = "r1"
eventhouse_name = "eh_cos"
send_to_eventhouse = True

# %% [markdown]
# ## 1. 공급 지연 반영
#
# **예상 결과:** `PO-5501 RM-HA-120 2026-11-10 → 2026-12-15 (지연 35일)` 한 줄이 나옵니다.
# 같은 Notebook을 다시 실행해도 원래 입고 예정일(`01_prepare_data`가 만든 값) 기준으로 계산하므로 지연이 두 번 쌓이지 않습니다.

# %%
from datetime import date, timedelta
from pyspark.sql import functions as F

AS_OF = date.fromisoformat(as_of_date)
purchase_orders = spark.table("gold.purchase_order")
if "original_eta" not in purchase_orders.columns:
    raise ValueError(
        "gold.purchase_order에 original_eta가 없습니다. 00장의 최신 준비 코드와 테이블 스키마를 확인하세요. "
        "진행 중인 실습을 초기화하지 말고 관리자와 확인하세요."
    )
original = (purchase_orders.where(F.col("material_code") == material_code)
            .select("po_id", "original_eta").collect())
if not original:
    raise ValueError(f"{material_code} 발주가 없습니다. 원료 코드를 확인하세요.")
if any(not isinstance(row.original_eta, date) for row in original):
    raise ValueError("original_eta에 최초 입고 예정일(date)이 있어야 합니다. 지연 반영 전에 원본 테이블을 확인하세요.")
orig_eta = {r.po_id: r.original_eta for r in original}

delayed = F.col("po_id").isin(list(orig_eta))
mapping = F.create_map([x for k, v in orig_eta.items() for x in (F.lit(k), F.lit(v))])
po_new = (spark.table("gold.purchase_order")
          .withColumn("eta", F.when(delayed, F.date_add(mapping[F.col("po_id")], int(delay_days))).otherwise(F.col("eta")))
          .withColumn("status", F.when(delayed, F.lit("지연")).otherwise(F.col("status"))))
po_new.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.purchase_order_tmp")
spark.table("gold.purchase_order_tmp").write.mode("overwrite").saveAsTable("gold.purchase_order")
spark.sql("DROP TABLE IF EXISTS gold.purchase_order_tmp")

for po_id, eta in orig_eta.items():
    print(f"{po_id} {material_code} {eta} → {eta + timedelta(days=int(delay_days))} (지연 {delay_days}일)")

# %% [markdown]
# ## 2. 영향 분석 (`ops.material_impact`)
#
# | 열 | 뜻 |
# |---|---|
# | `need_date` | 원료 필요일 = 생산 계획일 또는 안정성 시험 배치일 − QC 리드타임(기본 7일) |
# | `slack_days` | 필요일 − 새 입고 예정일. 음수면 원료가 늦게 들어옴 |
# | `impacted` | `slack_days < 0` |
# | `suggestion` | 승인된 대체 원료가 제때 들어오고 판매 시장에 쓸 수 있는지에 따른 검토 제안 |
#
# 업무 규칙: 폐기 버전(`is_active = false`)은 제외하고, 안정성 시험은 `예정` 상태만 봅니다.
#
# **예상 결과:** 4행 중 `impacted = true` 3행 — `PP-1101`(-27일), `PP-1102`(-20일), `ST-0711`(-32일). `PP-1103`은 여유 29일.

# %%
event_id = f"SUP-{AS_OF:%Y%m%d}-{material_code}-{run_tag}"
new_eta = min(orig_eta.values()) + timedelta(days=int(delay_days))
G = lambda t: spark.table(f"gold.{t}")

active = G("formula_version").where("is_active")
uses = G("formula_line").where(F.col("material_code") == material_code).select("version_id")
plans = (G("production_plan").join(G("product"), "product_id").join(active.select("version_id"), "version_id")
         .select(F.lit("생산계획").alias("target_type"), F.col("plan_id").alias("target_id"), "product_id",
                 F.lit(None).cast("string").alias("project_id"), "market", "version_id",
                 F.col("planned_date").alias("demand_date")))
tests = (G("stability_test").where("status = '예정'").join(active.select("version_id"), "version_id")
         .select(F.lit("안정성시험").alias("target_type"), F.col("test_id").alias("target_id"),
                 F.lit(None).cast("string").alias("product_id"), "project_id",
                 F.lit(None).cast("string").alias("market"), "version_id", F.col("batch_date").alias("demand_date")))
demand = plans.unionByName(tests).join(uses, "version_id")

alts = (G("material_alternative").where((F.col("material_code") == material_code) & (F.col("approval_status") == "승인"))
        .join(G("raw_material").withColumnRenamed("material_code", "alt_material_code"), "alt_material_code")
        .select("alt_material_code", "lead_time_days", "cn_registration").orderBy("lead_time_days").limit(1).collect())
alt = alts[0] if alts else None
alt_eta = AS_OF + timedelta(days=int(alt.lead_time_days)) if alt else None

impact = (demand.withColumn("need_date", F.date_sub("demand_date", int(qc_lead_days)))
          .withColumn("new_eta", F.lit(new_eta))
          .withColumn("slack_days", F.datediff("need_date", "new_eta"))
          .withColumn("impacted", F.col("slack_days") < 0))
if alt:
    alt_in_time = F.lit(alt_eta) <= F.col("need_date")
    market_ok = (F.coalesce(F.col("market"), F.lit("KR")) != "CN") | F.lit(alt.cn_registration == "완료")
    impact = (impact.withColumn("alt_material_code", F.lit(alt.alt_material_code))
              .withColumn("alt_eta", F.lit(alt_eta))
              .withColumn("suggestion", F.when(~F.col("impacted"), F.lit("조치 불필요(여유 있음)"))
                          .when(alt_in_time & market_ok, F.lit(f"{alt.alt_material_code} 대체 사용 검토"))
                          .when(alt_in_time, F.lit(f"{alt.alt_material_code} CN 등록 필요 — 등록 또는 일정 조정 검토"))
                          .otherwise(F.lit("일정 조정 검토(제때 들어오는 승인 대체 원료 없음)"))))
else:
    impact = (impact.withColumn("alt_material_code", F.lit(None).cast("string")).withColumn("alt_eta", F.lit(None).cast("date"))
              .withColumn("suggestion", F.when(F.col("impacted"), F.lit("일정 조정 검토(승인 대체 원료 없음)"))
                          .otherwise(F.lit("조치 불필요(여유 있음)"))))
impact = (impact.withColumn("event_id", F.lit(event_id)).withColumn("material_code", F.lit(material_code))
          .select("event_id", "material_code", "target_type", "target_id", "product_id", "project_id", "market", "version_id",
                  "demand_date", "need_date", "new_eta", "slack_days", "impacted", "alt_material_code", "alt_eta", "suggestion"))

spark.sql("CREATE SCHEMA IF NOT EXISTS ops")
if spark.catalog.tableExists("ops.material_impact"):
    impact = impact.unionByName(spark.table("ops.material_impact").where(F.col("event_id") != event_id))
impact.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("ops.material_impact")
current = spark.table("ops.material_impact").where(F.col("event_id") == event_id).orderBy("target_id")
display(current)
targets = current.where("impacted").collect()
print(f"{event_id}: 영향 {len(targets)}건")

# %% [markdown]
# ## 3. Eventhouse로 보내기
#
# 같은 작업 영역에서 이름으로 Eventhouse `eh_cos`를 찾아 `MaterialSupplyEvent`에 `open` 행을 추가합니다.
# 같은 `event_id`가 이미 있으면 다시 보내지 않습니다. 새 이벤트로 실습을 반복하려면 `run_tag`를 `r2`처럼 바꿉니다.
#
# **예상 결과:** `SUP-20261102-RM-HA-120-r1: MaterialSupplyEvent에 open 추가`와 1행짜리 표가 나옵니다.

# %%
import pandas as pd
import requests
import sempy.fabric as fabric

workspace_id = fabric.get_workspace_id()
eventhouses = fabric.FabricRestClient().get(f"v1/workspaces/{workspace_id}/eventhouses").json()["value"]
matches = [e for e in eventhouses if e["displayName"] == eventhouse_name]
if len(matches) != 1:
    raise ValueError(f"현재 작업 영역에 {eventhouse_name} Eventhouse가 정확히 1개 있어야 합니다. 4장 1단계를 확인하세요.")
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


material = G("raw_material").where(F.col("material_code") == material_code).join(G("supplier"), "supplier_id").first()
summary = "; ".join(f"{t.target_id}({t.product_id or t.project_id}, {t.slack_days}일, {t.suggestion})" for t in targets)

if send_to_eventhouse:
    if kusto("mgmt", ".show tables | where TableName == 'MaterialSupplyEvent'").empty:
        raise ValueError("MaterialSupplyEvent 테이블이 없습니다. 4장 2단계에서 테이블을 먼저 만드세요.")
    exists = kusto("query", f"MaterialSupplyEvent | where event_id == {kql_text(event_id)} | count")["Count"][0] > 0
    if not targets:
        print("영향 대상이 없어 이벤트를 보내지 않았습니다.")
    elif exists:
        print(f"{event_id}: 이미 보낸 이벤트입니다. 새 이벤트로 실습을 반복하려면 run_tag를 바꾸세요.")
    else:
        kusto("mgmt", f""".set-or-append MaterialSupplyEvent <|
print event_id = {kql_text(event_id)}, event_time = now(), event_status = 'open',
      material_code = {kql_text(material_code)}, material_name = {kql_text(material.material_name)},
      supplier_name = {kql_text(material.supplier_name)}, original_eta = datetime({min(orig_eta.values())}),
      new_eta = datetime({new_eta}), delay_days = toint({int(delay_days)}), impacted_count = toint({len(targets)}),
      impacted_targets = {kql_text(summary)}, updated_by = {kql_text('03_supply_change')},
      note = {kql_text('영향 분석 완료. 담당자 승인 시 검토 요청 등록')}""")
        print(f"{event_id}: MaterialSupplyEvent에 open 추가")
    display(kusto("query", "MaterialSupplyEvent | project event_time, event_id, event_status, material_code, new_eta, "
                           "impacted_count, impacted_targets | order by event_time asc"))
