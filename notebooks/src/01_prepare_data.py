# %% [markdown]
# # 01_prepare_data — 실습 데이터 준비와 초기화
#
# 참가자가 **00장**에서 코드에 포함된 고정 가상 데이터로 `gold` 스키마 테이블을 직접 만듭니다.
# 기본 `reset_ops = False`는 최초 적재용입니다. 기존 실습 테이블이 있으면 쓰기 전에 오류로 중지합니다.
# 초기화에 동의한 경우에만 `reset_ops = True`로 바꿉니다. 선택한 `gold` 테이블을 초기 데이터로 덮어쓰고,
# `ops`의 영향 분석·검토 요청·조치 이력을 지웁니다. 진행 중인 실습이나 07장 이후 모델 확장 중에는 재실행하지 않습니다.
#
# - 기본 Lakehouse: `lh_cos` (스키마 사용)
# - 실제 구매·처방 시스템과 연결되지 않은 **가상 데이터**입니다.
# - `include_extended = True`이면 선택 확장용 17개도 함께 생성합니다(총 28개).
# - 파일 업로드나 외부 데이터 다운로드는 필요하지 않습니다.

# %% [parameters]
include_extended = False
reset_ops = False

# %%
import csv
import io
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


def select_tables(include_extended):
    if not isinstance(include_extended, bool):
        raise ValueError("include_extended는 True 또는 False여야 합니다.")
    return {**TABLES, **EXTENDED_TABLES} if include_extended else TABLES


def check_existing_data(reset_ops):
    if not isinstance(reset_ops, bool):
        raise ValueError("reset_ops는 True 또는 False여야 합니다.")
    if reset_ops:
        return
    names = [f"gold.{table}" for table in (*TABLES, *EXTENDED_TABLES)]
    names += [f"ops.{table}" for table in OPS_TABLES]
    existing = [name for name in names if spark.catalog.tableExists(name)]
    if existing:
        raise ValueError(
            f"기존 실습 테이블이 있어 적재를 중지합니다: {', '.join(existing)}. "
            "현재 결과를 먼저 확인하세요. 초기화에 동의한 경우에만 reset_ops = True로 실행합니다. "
            "초기화는 gold를 덮어쓰고 ops 실습 결과를 삭제합니다."
        )

# %%
# {{SCENARIO_DATA}}

# %%
tables_to_load = select_tables(include_extended)
print(f"데이터 프로필: {len(tables_to_load)}개 테이블")
check_existing_data(reset_ops)

spark.sql("CREATE SCHEMA IF NOT EXISTS gold")
spark.sql("CREATE SCHEMA IF NOT EXISTS ops")

for table, columns in tables_to_load.items():
    reader = csv.DictReader(io.StringIO(SCENARIO_DATA[table]))
    if reader.fieldnames != list(columns):
        raise ValueError(f"{table}: 포함된 데이터의 열과 스키마가 일치하지 않습니다.")
    records = [{column: row[column] or None for column in columns} for row in reader]
    raw = spark.createDataFrame(records, schema=", ".join(f"{column} string" for column in columns))
    df = raw.select([F.col(c).cast(t).alias(c) for c, t in columns.items()])
    if table == "purchase_order":
        df = df.withColumn("original_eta", F.col("eta"))
    df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(f"gold.{table}")
    print(f"gold.{table:<22} {df.count():>3} rows")

# %%
if reset_ops:
    for table in OPS_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS ops.{table}")
    print("ops 스키마 실습 결과 초기화:", ", ".join(OPS_TABLES))

# %% [markdown]
# ## 확인
# 출력의 데이터 프로필과 `gold.<table>`별 행 수를 확인하고 00장의 완료 기준과 대조합니다.
# 핵심 프로필은 11개, `include_extended = True` 프로필은 28개이며 `ops`에는 아직 결과 테이블이 없습니다.
# `purchase_order.original_eta`는 이후 지연을 중복 가산하지 않도록 최초 입고 예정일을 보존합니다.
# `PO-5501`(RM-HA-120)의 입고 예정일은 **2026-11-10, 확정** 상태여야 합니다.

# %%
display(spark.sql("SELECT po_id, material_code, eta, status FROM gold.purchase_order WHERE po_id = 'PO-5501'"))
