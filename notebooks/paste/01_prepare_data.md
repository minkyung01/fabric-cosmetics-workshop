# 01_prepare_data — 복사할 코드

파일 가져오기가 허용되지 않는 환경의 대체 준비용입니다. 새 Notebook의 첫 코드 블록은 셀 메뉴의 `Toggle parameter cell`로 매개변수 셀로 지정하고, 두 번째 블록은 별도 코드 셀에 넣습니다.

[기본 Lakehouse 연결](../../docs/00-scenario.md#4-notebook에-기본-lakehouse-연결)

## 1. 매개변수 셀

```python
include_extended = False
reset_ops = False
```

## 2. 실행 코드 셀

```python
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

SCENARIO_DATA = {
    "dev_project": "project_id,project_name,version_id,stage,owner,target_launch\nDP-2026-07,하이드라 토너 출시,FV-TON-02-01,안정성시험,처방개발2팀,2027-04-01\n",
    "formula_line": "line_id,version_id,material_code,pct_wt\nFL-001,FV-CRM-01-02,RM-HA-120,1.5\nFL-002,FV-CRM-01-02,RM-GLY-001,5.0\nFL-003,FV-CRM-01-02,RM-PHE-002,0.5\nFL-004,FV-CRM-01-03,RM-HA-120,2.0\nFL-005,FV-CRM-01-03,RM-GLY-001,5.0\nFL-006,FV-CRM-01-03,RM-PAN-050,1.0\nFL-007,FV-CRM-01-03,RM-PHE-002,0.5\nFL-008,FV-TON-02-01,RM-HA-120,3.0\nFL-009,FV-TON-02-01,RM-NIA-010,2.0\nFL-010,FV-TON-02-01,RM-GLY-001,3.0\nFL-011,FV-AMP-03-02,RM-HA-120,1.0\nFL-012,FV-AMP-03-02,RM-CEN-030,2.0\nFL-013,FV-AMP-03-02,RM-PHE-002,0.5\nFL-014,FV-LOT-04-01,RM-NIA-010,4.0\nFL-015,FV-LOT-04-01,RM-GLY-001,4.0\n",
    "formula_version": "version_id,formula_id,formula_name,version_no,status,is_active,approved_date\nFV-CRM-01-02,F-CRM-01,수분 장벽 크림,2,폐기,false,2024-03-15\nFV-CRM-01-03,F-CRM-01,수분 장벽 크림,3,현행,true,2025-09-01\nFV-TON-02-01,F-TON-02,하이드라 토너,1,개발중,true,\nFV-AMP-03-02,F-AMP-03,시카 앰플,2,현행,true,2025-05-20\nFV-LOT-04-01,F-LOT-04,데일리 로션,1,현행,true,2024-11-11\n",
    "ingredient": "ingredient_id,inci_name,korean_name,function\nING-HA,Sodium Hyaluronate,소듐하이알루로네이트,보습\nING-NIA,Niacinamide,나이아신아마이드,미백 기능성\nING-GLY,Glycerin,글리세린,보습\nING-PAN,Panthenol,판테놀,진정\nING-CEN,Centella Asiatica Extract,병풀추출물,진정\nING-PHE,Phenoxyethanol,페녹시에탄올,보존\n",
    "material_alternative": "alt_id,material_code,alt_material_code,approval_status,condition_note\nALT-001,RM-HA-120,RM-HA-210,승인,파우더 용해 공정 추가 필요\nALT-002,RM-HA-120,RM-HA-305,검토중,점도 차이로 처방 조정 필요\nALT-003,RM-PHE-002,RM-GLY-001,반려,보존력 부족\n",
    "product": "product_id,product_name,version_id,market,sales_status\nP-101,수분 장벽 크림 50ml,FV-CRM-01-03,KR,판매중\nP-102,수분 장벽 크림 50ml (중국),FV-CRM-01-03,CN,판매중\nP-301,시카 앰플 30ml,FV-AMP-03-02,KR,판매중\nP-401,데일리 로션 200ml,FV-LOT-04-01,KR,판매중\n",
    "production_plan": "plan_id,product_id,planned_date,qty_ea\nPP-1101,P-101,2026-11-25,30000\nPP-1102,P-102,2026-12-02,20000\nPP-1103,P-301,2027-01-20,15000\nPP-1104,P-401,2026-11-16,40000\n",
    "purchase_order": "po_id,material_code,supplier_id,qty_kg,order_date,eta,status\nPO-5501,RM-HA-120,SUP-02,120.0,2026-10-13,2026-11-10,확정\nPO-5502,RM-GLY-001,SUP-03,800.0,2026-10-27,2026-11-06,확정\nPO-5503,RM-NIA-010,SUP-03,60.0,2026-10-26,2026-11-09,확정\nPO-5504,RM-CEN-030,SUP-01,40.0,2026-10-30,2026-11-20,확정\nPO-5505,RM-PHE-002,SUP-02,25.0,2026-10-20,2026-11-10,확정\nPO-5506,RM-PAN-050,SUP-01,30.0,2026-10-28,2026-11-11,확정\n",
    "raw_material": "material_code,material_name,ingredient_id,supplier_id,lead_time_days,unit_price_krw,cn_registration\nRM-HA-120,소듐하이알루로네이트 1% 용액(저분자),ING-HA,SUP-02,28,185000,완료\nRM-HA-210,소듐하이알루로네이트 파우더,ING-HA,SUP-01,10,240000,필요\nRM-HA-305,소듐하이알루로네이트 1% 용액(고분자),ING-HA,SUP-04,42,172000,완료\nRM-NIA-010,나이아신아마이드 99%,ING-NIA,SUP-03,14,52000,완료\nRM-GLY-001,글리세린 99.5%,ING-GLY,SUP-03,7,4200,완료\nRM-PAN-050,D-판테놀 75%,ING-PAN,SUP-01,14,61000,완료\nRM-CEN-030,병풀추출물 30%,ING-CEN,SUP-01,21,98000,완료\nRM-PHE-002,페녹시에탄올,ING-PHE,SUP-02,21,15000,완료\n",
    "stability_test": "test_id,version_id,project_id,batch_date,condition,status\nST-0711,FV-TON-02-01,DP-2026-07,2026-11-20,40℃/75%RH 12주,예정\n",
    "supplier": "supplier_id,supplier_name,country,risk_grade\nSUP-01,한빛바이오,KR,낮음\nSUP-02,Aqua Derm Chemicals,FR,보통\nSUP-03,그린팜소재,KR,낮음\nSUP-04,Nordic Actives,SE,보통\n",
    "change_assessment": "assessment_id,change_id,version_id,team_id,status\nCA-01,CH-01,FV-CRM-01-03,TEAM-PLAN,대기\nCA-02,CH-01,FV-TON-02-01,TEAM-FORM,진행중\nCA-03,CH-02,FV-TON-02-01,TEAM-REG,등록확인\n",
    "change_request": "change_id,material_code,project_id,team_id,status\nCH-01,RM-HA-120,DP-2026-07,TEAM-FORM,검토중\nCH-02,RM-HA-210,DP-2026-07,TEAM-REG,검토중\n",
    "goods_receipt": "receipt_id,po_id,lot_id,received_date,qty_kg\nGR-01,PO-5501,LOT-120-A,2026-10-30,8.0\nGR-02,PO-5501,LOT-120-B,2026-10-31,5.0\n",
    "inventory_balance": "balance_id,lot_id,warehouse_id,qty_kg,availability\nINV-01,LOT-120-A,WH-01,8.0,가용\nINV-02,LOT-120-B,WH-01,5.0,격리\nINV-03,LOT-210-A,WH-02,20.0,가용\nINV-04,LOT-210-A,WH-01,10.0,가용\n",
    "manufacturing_batch": "batch_id,plan_id,line_id,version_id,status\nBATCH-01,PP-1101,LINE-01,FV-CRM-01-03,예정\nBATCH-02,PP-1102,LINE-02,FV-CRM-01-03,예정\nBATCH-03,PP-1103,LINE-01,FV-AMP-03-02,예정\n",
    "manufacturing_site": "site_id,organization_id,site_name\nSITE-01,ORG-OPS,인천 제조소\nSITE-02,ORG-OPS,오산 제조소\n",
    "market": "market_code,market_name\nKR,한국\nCN,중국\n",
    "material_lot": "lot_id,material_code,supplier_id,spec_id,expiry_date,disposition\nLOT-120-A,RM-HA-120,SUP-02,SPEC-120,2027-10-01,사용가능\nLOT-120-B,RM-HA-120,SUP-02,SPEC-120,2027-10-01,격리\nLOT-210-A,RM-HA-210,SUP-01,SPEC-210,2027-09-01,사용가능\n",
    "material_registration": "registration_id,material_code,market_code,status\nMR-120-CN,RM-HA-120,CN,완료\nMR-210-CN,RM-HA-210,CN,필요\nMR-210-KR,RM-HA-210,KR,완료\nMR-305-CN,RM-HA-305,CN,완료\n",
    "material_spec": "spec_id,material_code,spec_name\nSPEC-120,RM-HA-120,표준 보습 원료 규격\nSPEC-210,RM-HA-210,대체 보습 원료 규격\nSPEC-305,RM-HA-305,고순도 보습 원료 규격\n",
    "organization": "organization_id,organization_name\nORG-RD,Caldova 연구개발\nORG-OPS,Caldova 생산운영\n",
    "product_registration": "registration_id,product_id,market_code,status\nPR-101-KR,P-101,KR,완료\nPR-102-CN,P-102,CN,완료\nPR-301-KR,P-301,KR,완료\n",
    "production_line": "line_id,site_id,line_name\nLINE-01,SITE-01,크림·앰플 라인\nLINE-02,SITE-02,수출 제품 라인\n",
    "quality_inspection": "inspection_id,lot_id,spec_id,result,inspected_date\nQI-01,LOT-120-A,SPEC-120,적합,2026-11-01\nQI-02,LOT-120-B,SPEC-120,부적합,2026-11-01\nQI-03,LOT-210-A,SPEC-210,적합,2026-10-20\n",
    "supplier_qualification": "qualification_id,supplier_id,market_code,status,valid_until\nSQ-01,SUP-01,CN,승인,2027-12-31\nSQ-02,SUP-02,CN,승인,2027-06-30\nSQ-03,SUP-04,CN,검토중,2026-12-31\n",
    "team": "team_id,organization_id,team_name\nTEAM-FORM,ORG-RD,처방개발\nTEAM-REG,ORG-RD,등록검토\nTEAM-PLAN,ORG-OPS,구매·생산계획\n",
    "warehouse": "warehouse_id,site_id,warehouse_name\nWH-01,SITE-01,인천 원료 창고\nWH-02,SITE-02,오산 원료 창고\n"
}

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

if reset_ops:
    for table in OPS_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS ops.{table}")
    print("ops 스키마 실습 결과 초기화:", ", ".join(OPS_TABLES))

display(spark.sql("SELECT po_id, material_code, eta, status FROM gold.purchase_order WHERE po_id = 'PO-5501'"))
```
