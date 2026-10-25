# %% [markdown]
# # 02_answers — Graph·Data Agent 질문의 정답 확인
#
# 2장(Graph)과 3장(Data Agent)에서 얻은 결과를 `gold` 테이블에 대한 Spark SQL로 다시 계산해 비교합니다.
# 같은 질문을 **경로 탐색(Graph)**, **자연어(Data Agent)**, **명시적 질의(이 Notebook)** 세 가지로 풀어 보는 것이 목적입니다.

# %% [parameters]
material_code = "RM-HA-120"
qc_lead_days = 7

# %%
def q(title, sql):
    print(f"\n### {title}")
    display(spark.sql(sql))

m = material_code.replace("'", "''")

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
q("Q5 필요일 대비 여유", f"""
WITH demand AS (
  SELECT '생산계획' AS target_type, pp.plan_id AS target_id, p.product_id, CAST(NULL AS STRING) AS project_id,
         p.market, fv.version_id, pp.planned_date AS demand_date
  FROM gold.production_plan pp JOIN gold.product p ON p.product_id = pp.product_id
  JOIN gold.formula_version fv ON fv.version_id = p.version_id AND fv.is_active
  UNION ALL
  SELECT '안정성시험', st.test_id, NULL, st.project_id, NULL, fv.version_id, st.batch_date
  FROM gold.stability_test st JOIN gold.formula_version fv ON fv.version_id = st.version_id AND fv.is_active
  WHERE st.status = '예정'
), eta AS (
  SELECT material_code, MIN(eta) AS eta FROM gold.purchase_order WHERE material_code = '{m}' GROUP BY material_code
)
SELECT d.target_type, d.target_id, COALESCE(d.product_id, d.project_id) AS owner_id, d.market,
       date_sub(d.demand_date, {int(qc_lead_days)}) AS need_date, e.eta,
       datediff(date_sub(d.demand_date, {int(qc_lead_days)}), e.eta) AS slack_days
FROM demand d JOIN gold.formula_line fl ON fl.version_id = d.version_id AND fl.material_code = '{m}'
CROSS JOIN eta e ORDER BY d.target_id""")

# %% [markdown]
# ## Q6. 지연 반영 후 영향 분석 결과 (`03_supply_change` 실행 후)
# 기대: 영향 3건 — `PP-1101`(-27일), `PP-1102`(-20일), `ST-0711`(-32일). `PP-1103`은 여유 29일로 영향 없음.

# %%
if spark.catalog.tableExists("ops.material_impact"):
    q("Q6 영향 분석", "SELECT * FROM ops.material_impact ORDER BY target_id")
else:
    print("ops.material_impact가 아직 없습니다. 4장에서 03_supply_change를 실행한 뒤 다시 확인하세요.")
