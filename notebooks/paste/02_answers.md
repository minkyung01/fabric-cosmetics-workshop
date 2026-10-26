# 02_answers — 복사할 코드

[Notebook 생성·셀 설정](../../docs/00-scenario.md#4-notebook-5개-만들기와-코드-붙여넣기)

## 1. 매개변수 셀

```python
material_code = "RM-HA-120"
qc_lead_days = 7
```

## 2. 실행 코드 셀

```python
from datetime import date


def q(title, sql):
    print(f"\n### {title}")
    display(spark.sql(sql))

m = material_code.replace("'", "''")


def schedule_sql(eta=None, qc_days=None):
    qc = int(qc_lead_days if qc_days is None else qc_days)
    eta_query = (
        f"SELECT MIN(eta) AS eta FROM gold.purchase_order WHERE material_code = '{m}' GROUP BY material_code"
        if eta is None else f"SELECT to_date('{date.fromisoformat(eta).isoformat()}') AS eta"
    )
    return f"""
WITH demand AS (
  SELECT '생산계획' AS target_type, pp.plan_id AS target_id, p.product_id, CAST(NULL AS STRING) AS project_id,
         p.market, fv.version_id, pp.planned_date AS demand_date
  FROM gold.production_plan pp JOIN gold.product p ON p.product_id = pp.product_id
  JOIN gold.formula_version fv ON fv.version_id = p.version_id AND fv.is_active
  UNION ALL
  SELECT '안정성시험', st.test_id, NULL, st.project_id, NULL, fv.version_id, st.batch_date
  FROM gold.stability_test st JOIN gold.formula_version fv ON fv.version_id = st.version_id AND fv.is_active
  WHERE st.status = '예정'
), eta AS ({eta_query})
SELECT d.target_type, d.target_id, COALESCE(d.product_id, d.project_id) AS owner_id, d.market,
       d.version_id, fl.material_code, date_sub(d.demand_date, {qc}) AS need_date, e.eta,
       datediff(date_sub(d.demand_date, {qc}), e.eta) AS slack_days,
       datediff(date_sub(d.demand_date, {qc}), e.eta) < 0 AS is_impacted
FROM demand d JOIN gold.formula_line fl ON fl.version_id = d.version_id AND fl.material_code = '{m}'
CROSS JOIN eta e"""

q("Q1 처방 버전", f"""
SELECT fv.version_id, fv.formula_name, fv.status, fv.is_active, fl.pct_wt
FROM gold.formula_line fl JOIN gold.formula_version fv ON fl.version_id = fv.version_id
WHERE fl.material_code = '{m}' ORDER BY fv.version_id""")

q("Q2 영향 후보", f"""
SELECT '제품' AS target_type, p.product_id AS target_id, p.product_name AS name, p.market, fv.version_id
FROM gold.formula_line fl
JOIN gold.formula_version fv ON fl.version_id = fv.version_id AND fv.is_active
JOIN gold.product p ON p.version_id = fv.version_id
WHERE fl.material_code = '{m}'
UNION ALL
SELECT '개발과제', d.project_id, d.project_name, NULL, fv.version_id
FROM gold.formula_line fl
JOIN gold.formula_version fv ON fl.version_id = fv.version_id AND fv.is_active
JOIN gold.dev_project d ON d.version_id = fv.version_id
WHERE fl.material_code = '{m}'
ORDER BY target_type, target_id""")

q("Q3 대체 원료", f"""
SELECT a.alt_material_code, r.material_name, a.approval_status, r.lead_time_days, r.cn_registration,
       s.supplier_name, a.condition_note
FROM gold.material_alternative a
JOIN gold.raw_material r ON r.material_code = a.alt_material_code
JOIN gold.supplier s ON s.supplier_id = r.supplier_id
WHERE a.material_code = '{m}' ORDER BY a.alt_material_code""")

q("Q4 같은 공급사 원료", f"""
SELECT r2.material_code, r2.material_name, fv.version_id, fv.formula_name
FROM gold.raw_material r1
JOIN gold.raw_material r2 ON r2.supplier_id = r1.supplier_id AND r2.material_code <> r1.material_code
JOIN gold.formula_line fl ON fl.material_code = r2.material_code
JOIN gold.formula_version fv ON fv.version_id = fl.version_id AND fv.is_active
WHERE r1.material_code = '{m}' ORDER BY fv.version_id""")

q("Q5 필요일 대비 여유", schedule_sql() + " ORDER BY target_id")

if spark.catalog.tableExists("ops.material_impact"):
    q("Q6 영향 분석", "SELECT * FROM ops.material_impact ORDER BY target_id")
else:
    print("ops.material_impact가 아직 없습니다. 4장에서 03_supply_change를 실행한 뒤 다시 확인하세요.")

q("DA05 성분과 원료", f"""
SELECT i.ingredient_id, i.inci_name, r.material_code, r.material_name, r.unit_price_krw,
       s.supplier_id, s.supplier_name
FROM gold.raw_material origin
JOIN gold.ingredient i ON i.ingredient_id = origin.ingredient_id
JOIN gold.raw_material r ON r.ingredient_id = i.ingredient_id
JOIN gold.supplier s ON s.supplier_id = r.supplier_id
WHERE origin.material_code = '{m}' ORDER BY r.material_code""")

q("DA07 업무 경로", f"""
SELECT pp.plan_id AS target_id, p.product_id, fv.version_id, fl.material_code,
       CAST(NULL AS STRING) AS project_id
FROM gold.production_plan pp JOIN gold.product p ON p.product_id = pp.product_id
JOIN gold.formula_version fv ON fv.version_id = p.version_id AND fv.is_active
JOIN gold.formula_line fl ON fl.version_id = fv.version_id AND fl.material_code = '{m}'
WHERE pp.plan_id = 'PP-1102'
UNION ALL
SELECT st.test_id, NULL, fv.version_id, fl.material_code, dp.project_id
FROM gold.stability_test st
JOIN gold.formula_version fv ON fv.version_id = st.version_id AND fv.is_active
JOIN gold.formula_line fl ON fl.version_id = fv.version_id AND fl.material_code = '{m}'
JOIN gold.dev_project dp ON dp.project_id = st.project_id
WHERE st.test_id = 'ST-0711' AND st.status = '예정'
ORDER BY target_id""")

q("DA08 공급사 경로", f"""
SELECT s.supplier_id, s.supplier_name, other.material_code, fv.version_id, p.product_id,
       po.po_id, po.eta AS recorded_eta
FROM gold.raw_material origin JOIN gold.supplier s ON s.supplier_id = origin.supplier_id
JOIN gold.raw_material other ON other.supplier_id = s.supplier_id AND other.material_code <> origin.material_code
JOIN gold.formula_line fl ON fl.material_code = other.material_code
JOIN gold.formula_version fv ON fv.version_id = fl.version_id AND fv.is_active
JOIN gold.product p ON p.version_id = fv.version_id
LEFT JOIN gold.purchase_order po ON po.material_code = other.material_code AND po.supplier_id = s.supplier_id
WHERE origin.material_code = '{m}' ORDER BY p.product_id""")

q("DA04 후보 조건", f"""
WITH targets AS ({schedule_sql('2026-12-15', 7)}),
candidates AS (
  SELECT d.target_id, d.market, d.need_date, a.alt_material_code, a.approval_status,
         r.cn_registration, r.lead_time_days, a.condition_note,
         date_add(to_date('2026-11-02'), CAST(r.lead_time_days AS INT)) AS assumed_eta
  FROM targets d
  JOIN gold.material_alternative a ON a.material_code = d.material_code
  JOIN gold.raw_material r ON r.material_code = a.alt_material_code
  WHERE d.target_id = 'PP-1102'
)
SELECT *, datediff(need_date, assumed_eta) AS slack_days,
       approval_status = '승인' AS approval_ok, assumed_eta <= need_date AS schedule_ok,
       cn_registration = '완료' AS cn_ok,
       approval_status = '승인' AND assumed_eta <= need_date AND cn_registration = '완료' AS all_ok
FROM candidates ORDER BY alt_material_code""")

q("DA03 경계 판정", f"""
WITH on_time AS ({schedule_sql('2026-11-13', 7)}),
one_day_late AS ({schedule_sql('2026-11-14', 7)})
SELECT * FROM on_time WHERE target_id = 'ST-0711'
UNION ALL
SELECT * FROM one_day_late WHERE target_id = 'ST-0711'
ORDER BY eta""")

q("DA09 입고일 비교", f"""
WITH baseline AS ({schedule_sql('2026-11-10', 7)}),
delayed AS ({schedule_sql('2026-12-15', 7)})
SELECT b.target_id, b.owner_id, b.version_id, b.market, b.need_date,
       b.eta AS baseline_eta, b.slack_days AS before_slack, b.is_impacted AS before_impact,
       d.eta AS assumed_eta, d.slack_days AS after_slack, d.is_impacted AS after_impact
FROM baseline b JOIN delayed d ON d.target_id = b.target_id ORDER BY b.target_id""")

q("DA10 QC 비교", f"""
WITH qc7 AS ({schedule_sql('2026-11-20', 7)}),
qc14 AS ({schedule_sql('2026-11-20', 14)})
SELECT a.target_id, a.eta, a.need_date AS need_qc7, a.slack_days AS slack_qc7,
       a.is_impacted AS impact_qc7, b.need_date AS need_qc14, b.slack_days AS slack_qc14,
       b.is_impacted AS impact_qc14
FROM qc7 a JOIN qc14 b ON b.target_id = a.target_id ORDER BY a.target_id""")

q("DA11 통합 검토표", f"""
WITH targets AS ({schedule_sql('2026-12-15', 7)})
SELECT d.target_id, d.owner_id, d.market, d.version_id,
       COALESCE(p.product_name, dp.project_name) AS owner_name, pp.qty_ea AS planned_qty_ea,
       po.po_id, s.supplier_id, s.supplier_name, po.eta AS recorded_eta,
       d.eta AS assumed_eta, d.need_date, d.slack_days, a.alt_material_code,
       alt.cn_registration, a.condition_note,
       CASE WHEN a.alt_material_code IS NULL THEN '승인 후보 없음'
            WHEN d.market = 'CN' AND (alt.cn_registration IS NULL OR alt.cn_registration <> '완료')
                 THEN 'CN 등록 검토 필요'
            WHEN d.market IS NULL THEN '시장 미연결; 용해 공정 등 검토 필요'
            ELSE '용해 공정 등 검토 필요' END AS review_note
FROM targets d
JOIN gold.raw_material r ON r.material_code = d.material_code
JOIN gold.purchase_order po ON po.material_code = r.material_code
JOIN gold.supplier s ON s.supplier_id = po.supplier_id
LEFT JOIN gold.product p ON p.product_id = d.owner_id AND d.target_type = '생산계획'
LEFT JOIN gold.production_plan pp ON pp.plan_id = d.target_id AND d.target_type = '생산계획'
LEFT JOIN gold.dev_project dp ON dp.project_id = d.owner_id AND d.target_type = '안정성시험'
LEFT JOIN gold.material_alternative a ON a.material_code = r.material_code AND a.approval_status = '승인'
LEFT JOIN gold.raw_material alt ON alt.material_code = a.alt_material_code
WHERE d.is_impacted ORDER BY d.target_id""")
```
