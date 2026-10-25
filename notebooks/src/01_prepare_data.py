# %% [markdown]
# # 01_prepare_data — 실습 데이터 준비와 초기화
#
# `Files/workshop/data/*.csv`(가상 데이터)를 읽어 `gold` 스키마 테이블을 만듭니다.
# 다시 실행하면 `gold`를 초기 상태로 되돌리고 `ops` 스키마의 실습 결과(영향 분석·검토 요청·조치 이력)를 지웁니다.
# 기본 과정에서는 00장에서 준비된 데이터를 확인합니다. 초기화가 필요할 때만 안내에 따라 실행하며, 진행 중인 실습 결과를 보존해야 한다면 실행하지 않습니다.
#
# - 기본 Lakehouse: `lh_cos` (스키마 사용)
# - 실제 구매·처방 시스템과 연결되지 않은 **가상 데이터**입니다.
# - 확장 CSV 17개를 같은 폴더에 모두 올린 경우에만 확장 테이블도 생성합니다(총 28개).

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
EXTENDED_TABLES = {
    "organization": {"organization_id": "string", "organization_name": "string"},
    "team": {"team_id": "string", "organization_id": "string", "team_name": "string"},
    "supplier_qualification": {"qualification_id": "string", "supplier_id": "string", "market_code": "string",
                               "status": "string", "valid_until": "date"},
    "material_spec": {"spec_id": "string", "material_code": "string", "spec_name": "string"},
    "material_lot": {"lot_id": "string", "material_code": "string", "supplier_id": "string", "spec_id": "string",
                     "expiry_date": "date", "disposition": "string"},
    "goods_receipt": {"receipt_id": "string", "po_id": "string", "lot_id": "string", "received_date": "date",
                      "qty_kg": "double"},
    "quality_inspection": {"inspection_id": "string", "lot_id": "string", "spec_id": "string",
                           "result": "string", "inspected_date": "date"},
    "warehouse": {"warehouse_id": "string", "site_id": "string", "warehouse_name": "string"},
    "inventory_balance": {"balance_id": "string", "lot_id": "string", "warehouse_id": "string",
                          "qty_kg": "double", "availability": "string"},
    "manufacturing_site": {"site_id": "string", "organization_id": "string", "site_name": "string"},
    "production_line": {"line_id": "string", "site_id": "string", "line_name": "string"},
    "manufacturing_batch": {"batch_id": "string", "plan_id": "string", "line_id": "string",
                            "version_id": "string", "status": "string"},
    "market": {"market_code": "string", "market_name": "string"},
    "material_registration": {"registration_id": "string", "material_code": "string", "market_code": "string",
                              "status": "string"},
    "product_registration": {"registration_id": "string", "product_id": "string", "market_code": "string",
                             "status": "string"},
    "change_request": {"change_id": "string", "material_code": "string", "project_id": "string",
                       "team_id": "string", "status": "string"},
    "change_assessment": {"assessment_id": "string", "change_id": "string", "version_id": "string",
                          "team_id": "string", "status": "string"},
}
OPS_TABLES = ["material_impact", "review_request", "action_log"]


def select_tables(available):
    missing_core = {f"{table}.csv" for table in TABLES} - available
    if missing_core:
        raise ValueError(f"핵심 CSV 누락: {sorted(missing_core)}")
    extended_files = {f"{table}.csv" for table in EXTENDED_TABLES}
    has_extended = bool(available & extended_files)
    if has_extended and not extended_files <= available:
        raise ValueError(f"확장 CSV는 17개를 모두 올려야 합니다. 누락: {sorted(extended_files - available)}")
    return {**TABLES, **EXTENDED_TABLES} if has_extended else TABLES

# %%
from notebookutils import fs

tables_to_load = select_tables({entry.name for entry in fs.ls(data_folder)})
print(f"데이터 프로필: {len(tables_to_load)}개 테이블")

spark.sql("CREATE SCHEMA IF NOT EXISTS gold")
spark.sql("CREATE SCHEMA IF NOT EXISTS ops")

for table, columns in tables_to_load.items():
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
