# %% [markdown]
# # 02_answers — Graph·Data Agent 질문의 정답 확인
#
# 2장(Graph)과 3장(Data Agent)에서 얻은 결과를 `gold` 테이블에 대한 Spark SQL로 다시 계산해 비교합니다.
# 같은 질문을 **경로 탐색(Graph)**, **자연어(Data Agent)**, **명시적 질의(이 Notebook)** 세 가지로 풀어 보는 것이 목적입니다.

# %% [parameters]
material_code = "RM-HA-120"
qc_lead_days = 7

# %%
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

# %% [markdown]
# ## Q1. 이 원료를 쓰는 처방 버전은? (상태 무관)
# 기대: 4개 버전 — `FV-CRM-01-02`(폐기), `FV-CRM-01-03`, `FV-TON-02-01`, `FV-AMP-03-02`

# %%
q("Q1 처방 버전", f"""
SELECT fv.version_id, fv.formula_name, fv.status, fv.is_active, fl.pct_wt
FROM gold.formula_line fl JOIN gold.formula_version fv ON fl.version_id = fv.version_id
WHERE fl.material_code = '{m}' ORDER BY fv.version_id""")

# %% [markdown]
# ## Q2. 업무 규칙 적용 — 폐기 버전 제외 후 연결된 제품·개발 과제는?
# 기대: 제품 `P-101`, `P-102`, `P-301` / 개발 과제 `DP-2026-07` (폐기 버전 `FV-CRM-01-02`는 제외)

# %%
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

# %% [markdown]
# ## Q3. 대체 원료와 승인 상태
# 기대: `RM-HA-210` 승인(리드타임 10일, CN 등록 필요), `RM-HA-305` 검토중(리드타임 42일)

# %%
q("Q3 대체 원료", f"""
SELECT a.alt_material_code, r.material_name, a.approval_status, r.lead_time_days, r.cn_registration,
       s.supplier_name, a.condition_note
FROM gold.material_alternative a
JOIN gold.raw_material r ON r.material_code = a.alt_material_code
JOIN gold.supplier s ON s.supplier_id = r.supplier_id
WHERE a.material_code = '{m}' ORDER BY a.alt_material_code""")

# %% [markdown]
# ## Q4. 공급사 관점 — 같은 공급사의 다른 원료를 쓰는 현행·개발중 처방은?
# 기대: 공급사 `SUP-02`(Aqua Derm Chemicals)는 `RM-PHE-002`도 공급 → `FV-CRM-01-03`, `FV-AMP-03-02`

# %%
q("Q4 같은 공급사 원료", f"""
SELECT r2.material_code, r2.material_name, fv.version_id, fv.formula_name
FROM gold.raw_material r1
JOIN gold.raw_material r2 ON r2.supplier_id = r1.supplier_id AND r2.material_code <> r1.material_code
JOIN gold.formula_line fl ON fl.material_code = r2.material_code
JOIN gold.formula_version fv ON fv.version_id = fl.version_id AND fv.is_active
WHERE r1.material_code = '{m}' ORDER BY fv.version_id""")

# %% [markdown]
# ## Q5. 원료 필요일과 입고 예정일 (현재 발주 기준)
# 원료 필요일 = 생산 계획일 또는 안정성 시험 배치일 − QC 리드타임(7일). 여유일 = 필요일 − 입고 예정일.
# 지연 반영 전 기대: 모든 대상의 여유일 ≥ 0 (PP-1101 8일, PP-1102 15일, PP-1103 64일, ST-0711 3일)

# %%
q("Q5 필요일 대비 여유", schedule_sql() + " ORDER BY target_id")

# %% [markdown]
# ## Q6. 지연 반영 후 영향 분석 결과 (`03_supply_change` 실행 후)
# 기대: 영향 3건 — `PP-1101`(-27일), `PP-1102`(-20일), `ST-0711`(-32일). `PP-1103`은 여유 29일로 영향 없음.

# %%
if spark.catalog.tableExists("ops.material_impact"):
    q("Q6 영향 분석", "SELECT * FROM ops.material_impact ORDER BY target_id")
else:
    print("ops.material_impact가 아직 없습니다. 4장에서 03_supply_change를 실행한 뒤 다시 확인하세요.")

# %% [markdown]
# ## 03장 DA01–DA12의 근거 확인
#
# Q1은 DA01·DA06의 처방 상태, Q3은 DA02·DA06의 대체 후보 상태를 확인합니다.
# 아래는 용어·관계·조건·What-if·통합 질문의 추가 근거입니다. 문항 ID는 Notebook Q번호와 다릅니다.
# 모든 추가 질의는 읽기 전용이며, `03_supply_change`나 `ops` 테이블 없이 실행합니다.
# DA03·DA09–DA11은 질문에 고정한 날짜·QC로 계산하므로 현재 발주 ETA와 혼동하지 않습니다.
# 정답 대조는 기본 매개변수 `material_code=RM-HA-120`, `qc_lead_days=7`로 진행합니다.

# %% [markdown]
# ### DA05. 성분과 원료 — DA12의 단가 근거도 확인
# 기대: ING-HA 아래 서로 다른 원료 3개, 공급사 SUP-02/SUP-01/SUP-04.
# 단가가 있어도 1% 용액과 파우더의 소요량을 그대로 치환하거나 총 비용을 확정할 수는 없습니다.

# %%
q("DA05 성분과 원료", f"""
SELECT i.ingredient_id, i.inci_name, r.material_code, r.material_name, r.unit_price_krw,
       s.supplier_id, s.supplier_name
FROM gold.raw_material origin
JOIN gold.ingredient i ON i.ingredient_id = origin.ingredient_id
JOIN gold.raw_material r ON r.ingredient_id = i.ingredient_id
JOIN gold.supplier s ON s.supplier_id = r.supplier_id
WHERE origin.material_code = '{m}' ORDER BY r.material_code""")

# %% [markdown]
# ### DA07. 생산과 시험의 두 업무 경로
# 저장 방향: PP-1102 → P-102 → FV-CRM-01-03 → RM-HA-120,
# ST-0711 → FV-TON-02-01 → RM-HA-120 및 ST-0711 → DP-2026-07.
# 실제 관계 이름·저장 방향은 01장의 정의와 대조합니다.

# %%
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

# %% [markdown]
# ### DA08. 같은 공급사 → 다른 원료 → 활성 처방 → 제품
# 기대: RM-PHE-002, FV-CRM-01-03/FV-AMP-03-02, P-101/P-102/P-301의 3행.
# PO-5505의 ETA는 2026-11-10입니다. 연결 관계가 추가 지연의 증거는 아닙니다.

# %%
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

# %% [markdown]
# ### DA04. CN 계획에 대한 대체 후보의 세 조건
# 기대: PP-1102 필요일 11-25. RM-HA-210은 승인/일정 통과·CN 미충족,
# RM-HA-305는 CN만 통과합니다. 세 조건을 모두 통과하는 후보는 없습니다.

# %%
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

# %% [markdown]
# ### DA03. 여유일 0의 경계
# 기대: ST-0711 필요일 11-13, 입고 11-13은 여유 0·영향 없음, 11-14는 -1·영향 있음.

# %%
q("DA03 경계 판정", f"""
WITH on_time AS ({schedule_sql('2026-11-13', 7)}),
one_day_late AS ({schedule_sql('2026-11-14', 7)})
SELECT * FROM on_time WHERE target_id = 'ST-0711'
UNION ALL
SELECT * FROM one_day_late WHERE target_id = 'ST-0711'
ORDER BY eta""")

# %% [markdown]
# ### DA09. 입고일만 바꾸기 — 원본 갱신 없이 비교
# 기대: PP-1101/PP-1102/PP-1103/ST-0711 여유일 8/15/64/3 → -27/-20/29/-32.

# %%
q("DA09 입고일 비교", f"""
WITH baseline AS ({schedule_sql('2026-11-10', 7)}),
delayed AS ({schedule_sql('2026-12-15', 7)})
SELECT b.target_id, b.owner_id, b.version_id, b.market, b.need_date,
       b.eta AS baseline_eta, b.slack_days AS before_slack, b.is_impacted AS before_impact,
       d.eta AS assumed_eta, d.slack_days AS after_slack, d.is_impacted AS after_impact
FROM baseline b JOIN delayed d ON d.target_id = b.target_id ORDER BY b.target_id""")

# %% [markdown]
# ### DA10. QC만 바꾸기 — 입고일은 11-20 고정
# 기대: QC 7일 → 14일에 PP-1102가 새 영향. PP-1103은 여유 47일로 영향 없음.

# %%
q("DA10 QC 비교", f"""
WITH qc7 AS ({schedule_sql('2026-11-20', 7)}),
qc14 AS ({schedule_sql('2026-11-20', 14)})
SELECT a.target_id, a.eta, a.need_date AS need_qc7, a.slack_days AS slack_qc7,
       a.is_impacted AS impact_qc7, b.need_date AS need_qc14, b.slack_days AS slack_qc14,
       b.is_impacted AS impact_qc14
FROM qc7 a JOIN qc14 b ON b.target_id = a.target_id ORDER BY a.target_id""")

# %% [markdown]
# ### DA11. 여러 데이터를 연결한 검토표
# 기대: PP-1101·PP-1102·ST-0711의 3행. 원본 ETA와 가정 ETA를 분리합니다.
# 대체 후보는 사용 승인 결론이 아닙니다. DA04의 일정 조건과 공정 검토도 함께 봅니다.

# %%
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

# %% [markdown]
# ### DA12. 판단 한계
# DA05의 원료 단가, Q1의 배합비, DA11의 계획 수량과 일정은 확인할 수 있습니다.
# 영향받는 생산 계획은 30,000개 + 20,000개 = 50,000개이며, 시험은 별도 1건입니다.
# 그러나 총 비용·생산 가능 수량·품질/공정 검증 완료를 확정하는 질의는 만들지 않습니다.
# 농도·제형 환산, 생산 단위별 실제 소요량, 할당 가능한 재고, 추가 공정 비용·검증 결과가 부족합니다.
# 데이터가 없는 값을 0으로 채우거나, 영향받는 계획 수량을 곧바로 생산 가능 수량으로 보고하지 않습니다.
