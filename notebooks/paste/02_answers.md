# 02_answers — 복사할 코드

파일 가져오기가 허용되지 않는 환경의 대체 준비용입니다. 새 Notebook의 첫 코드 블록은 셀 메뉴의 `Toggle parameter cell`로 매개변수 셀로 지정하고, 두 번째 블록은 별도 코드 셀에 넣습니다.

[기본 Lakehouse 연결](../../docs/00-scenario.md#4-notebook에-기본-lakehouse-연결)

## 1. 매개변수 셀

```python
material_code = "RM-HA-120"
qc_lead_days = 7
```

## 2. 실행 코드 셀

```python
from datetime import date


def q(title, sql, question=None):
    print(f"\n### {title}")
    if question is not None:
        print(f"Data Agent에 보낼 질문:\n{question}\n")
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

q("DA01 전체·활성 처방", f"""
SELECT fv.version_id, fv.formula_name, fv.status, fv.is_active,
       CASE WHEN fv.is_active THEN '포함' ELSE '제외' END AS impact_scope,
       CASE WHEN fv.is_active THEN '활성 처방' ELSE '비활성 처방' END AS scope_reason
FROM gold.formula_line fl JOIN gold.formula_version fv ON fl.version_id = fv.version_id
WHERE fl.material_code = '{m}' ORDER BY fv.version_id""",
  question="RM-HA-120을 쓰는 전체 처방 버전과 영향 분석에 포함되는 처방 버전을 대조해줘. version_id·status·is_active·포함/제외 이유를 보여줘.")

q("DA02 경계 판정", f"""
WITH on_time AS ({schedule_sql('2026-11-13', 7)}),
one_day_late AS ({schedule_sql('2026-11-14', 7)})
SELECT * FROM on_time WHERE target_id = 'ST-0711'
UNION ALL
SELECT * FROM one_day_late WHERE target_id = 'ST-0711'
ORDER BY eta""",
  question="ST-0711에서 QC 7일을 적용할 때 RM-HA-120이 2026-11-13에 입고되는 경우와 11-14에 입고되는 경우를 판정해줘. 필요일과 여유일을 계산하고, 여유일이 0이면 영향 대상인지 설명해줘.")

q("DA03 공급사 경로", f"""
SELECT s.supplier_id, s.supplier_name, other.material_code, fv.version_id, p.product_id,
       po.po_id, po.eta AS recorded_eta
FROM gold.raw_material origin JOIN gold.supplier s ON s.supplier_id = origin.supplier_id
JOIN gold.raw_material other ON other.supplier_id = s.supplier_id AND other.material_code <> origin.material_code
JOIN gold.formula_line fl ON fl.material_code = other.material_code
JOIN gold.formula_version fv ON fv.version_id = fl.version_id AND fv.is_active
JOIN gold.product p ON p.version_id = fv.version_id
LEFT JOIN gold.purchase_order po ON po.material_code = other.material_code AND po.supplier_id = s.supplier_id
WHERE origin.material_code = '{m}' ORDER BY p.product_id""",
  question="RM-HA-120의 공급사가 공급하는 다른 원료를 찾고, 그 원료를 쓰는 활성 처방과 제품까지 연결해줘. 같은 공급사라는 이유만으로 그 원료도 지연됐다고 판단해도 되는지 실제 발주 ETA와 구분해줘.")

q("DA04 입고일 비교", f"""
WITH baseline AS ({schedule_sql('2026-11-10', 7)}),
delayed AS ({schedule_sql('2026-12-15', 7)})
SELECT b.target_id, b.owner_id, b.version_id, b.market, b.need_date,
       b.eta AS baseline_eta, b.slack_days AS before_slack, b.is_impacted AS before_impact,
       d.eta AS assumed_eta, d.slack_days AS after_slack, d.is_impacted AS after_impact,
       NOT b.is_impacted AND d.is_impacted AS newly_impacted
FROM baseline b JOIN delayed d ON d.target_id = b.target_id ORDER BY b.target_id""",
  question="RM-HA-120의 입고일을 2026-11-10과 2026-12-15로 각각 가정해 비교해줘. QC는 7일로 고정하고 활성 처방에 연결된 생산 계획·예정 시험별 필요일·여유일·영향 여부와 새로 영향을 받는 대상을 보여줘.")

q("DA05 통합 검토표", f"""
WITH targets AS ({schedule_sql('2026-12-15', 7)})
SELECT d.target_id, d.owner_id, d.market, d.version_id,
       COALESCE(p.product_name, dp.project_name) AS owner_name, pp.qty_ea AS planned_qty_ea,
       po.po_id, s.supplier_id, s.supplier_name, po.eta AS recorded_eta,
       d.eta AS assumed_eta, d.need_date, d.slack_days,
       CASE WHEN d.target_type = '안정성시험' THEN '시험 일정·원료 확보 검토 필요'
            ELSE '생산 일정·원료 확보 검토 필요' END AS review_note
FROM targets d
JOIN gold.raw_material r ON r.material_code = d.material_code
JOIN gold.purchase_order po ON po.material_code = r.material_code
JOIN gold.supplier s ON s.supplier_id = po.supplier_id
LEFT JOIN gold.product p ON p.product_id = d.owner_id AND d.target_type = '생산계획'
LEFT JOIN gold.production_plan pp ON pp.plan_id = d.target_id AND d.target_type = '생산계획'
LEFT JOIN gold.dev_project dp ON dp.project_id = d.owner_id AND d.target_type = '안정성시험'
WHERE d.is_impacted ORDER BY d.target_id""",
  question="RM-HA-120이 2026-12-15에 입고된다고 가정하고 QC 7일을 적용해, 영향받는 생산 계획과 예정 시험을 하나의 검토표로 만들어줘. 제품/과제·시장·처방 버전·원 발주/공급사·필요일·여유일을 연결하고, 일정 조정이나 추가 검토가 필요한 대상을 정리해줘. 시험의 시장은 추정하지 마.")

q("DA06 계획·원료 근거", f"""
WITH targets AS ({schedule_sql('2026-12-15', 7)})
SELECT d.target_id, d.target_type, d.owner_id, d.market, d.version_id, d.need_date, d.slack_days,
       pp.qty_ea AS planned_qty_ea,
       SUM(pp.qty_ea) OVER () AS affected_planned_qty_ea,
       SUM(CASE WHEN d.target_type = '안정성시험' THEN 1 ELSE 0 END) OVER () AS affected_test_count,
       fl.pct_wt AS original_pct_wt, origin.material_code, origin.material_name,
       origin.unit_price_krw AS original_unit_price_krw,
       alt.material_code AS comparison_material_code, alt.material_name AS comparison_material_name,
       alt.unit_price_krw AS comparison_unit_price_krw, alt.cn_registration
FROM targets d
JOIN gold.formula_line fl ON fl.version_id = d.version_id AND fl.material_code = d.material_code
JOIN gold.raw_material origin ON origin.material_code = d.material_code
LEFT JOIN gold.production_plan pp ON pp.plan_id = d.target_id AND d.target_type = '생산계획'
LEFT JOIN gold.raw_material alt ON alt.material_code = 'RM-HA-210'
WHERE d.is_impacted ORDER BY d.target_id""",
  question="RM-HA-120 입고일을 2026-12-15, QC를 7일로 가정할게. RM-HA-210으로 대체하면 영향받는 생산 계획 물량을 전부 생산하고 ST-0711도 일정대로 진행할 수 있나? 계획 수량과 실제 생산 가능 수량을 구분하고, 총 추가 비용까지 확정할 수 있는지 확인되는 사실과 부족한 근거를 농도·제형 환산·공정 검증 관점에서 설명해줘.")
```
