# %% [markdown]
# # 01_prepare_data — 실습 데이터 준비 (관리자 사전 실행)
#
# `Files/workshop/data/*.csv`(가상 데이터)를 읽어 `gold` 스키마 테이블을 만듭니다.
# 다시 실행하면 `gold`를 초기 상태로 되돌리고 `ops` 스키마의 실습 결과(영향 분석·검토 요청·조치 이력)를 지웁니다.
#
# - 기본 Lakehouse: `lh_cos` (스키마 사용)
# - 실제 구매·처방 시스템과 연결되지 않은 **가상 데이터**입니다.

# %% [parameters]
data_folder = "Files/workshop/data"
reset_ops = True

# %%
from pyspark.sql import functions as F

TABLES = {
    "ingredient": {"ingredient_id": "string", "inci_name": "string", "korean_name": "string", "function": "string"},
    "supplier": {"supplier_id": "string", "supplier_name": "string", "country": "string", "risk_grade": "string"},
    "raw_material": {"material_code": "string", "material_name": "string", "ingredient_id": "string",
                     "supplier_id": "string", "lead_time_days": "bigint", "unit_price_krw": "bigint",
                     "cn_registration": "string"},
    "material_alternative": {"alt_id": "string", "material_code": "string", "alt_material_code": "string",
                             "approval_status": "string", "condition_note": "string"},
    "formula_version": {"version_id": "string", "formula_id": "string", "formula_name": "string",
                        "version_no": "bigint", "status": "string", "is_active": "boolean", "approved_date": "date"},
    "formula_line": {"line_id": "string", "version_id": "string", "material_code": "string", "pct_wt": "double"},
    "product": {"product_id": "string", "product_name": "string", "version_id": "string", "market": "string",
                "sales_status": "string"},
    "dev_project": {"project_id": "string", "project_name": "string", "version_id": "string", "stage": "string",
                    "owner": "string", "target_launch": "date"},
    "stability_test": {"test_id": "string", "version_id": "string", "project_id": "string", "batch_date": "date",
                       "condition": "string", "status": "string"},
    "production_plan": {"plan_id": "string", "product_id": "string", "planned_date": "date", "qty_ea": "bigint"},
    "purchase_order": {"po_id": "string", "material_code": "string", "supplier_id": "string", "qty_kg": "double",
                       "order_date": "date", "eta": "date", "status": "string"},
}
OPS_TABLES = ["material_impact", "review_request", "action_log"]

# %%
spark.sql("CREATE SCHEMA IF NOT EXISTS gold")
spark.sql("CREATE SCHEMA IF NOT EXISTS ops")

for table, columns in TABLES.items():
    raw = spark.read.option("header", True).option("encoding", "UTF-8").csv(f"{data_folder}/{table}.csv")
    missing = set(columns) - set(raw.columns)
    if missing:
        raise ValueError(f"{table}.csv에 없는 열: {sorted(missing)}")
    df = raw.select([F.col(c).cast(t).alias(c) for c, t in columns.items()])
    df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(f"gold.{table}")
    print(f"gold.{table:<22} {df.count():>3} rows")

# %%
if reset_ops:
    for table in OPS_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS ops.{table}")
    print("ops 스키마 실습 결과 초기화:", ", ".join(OPS_TABLES))

# %% [markdown]
# ## 확인
# 아래 결과가 `admin/data-design.md`의 행 수와 같아야 합니다.
# `PO-5501`(RM-HA-120)의 입고 예정일은 **2026-11-10, 확정** 상태여야 합니다.

# %%
display(spark.sql("SELECT po_id, material_code, eta, status FROM gold.purchase_order WHERE po_id = 'PO-5501'"))
