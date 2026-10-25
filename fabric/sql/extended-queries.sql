-- Read-only queries for the optional 26-entity profile.
-- Run on lh_cos SQL analytics endpoint, not sqldb_cos.
-- Fixed fictional snapshot: 2026-11-02. QX1-QX4 are separate result sets.

-- QX1: material -> lot -> receipt / inspection / stock -> warehouse -> site -> organization.
SELECT rm.material_code, lot.lot_id, receipt.receipt_id, spec.spec_name,
       supplier.supplier_name, inspection.result, lot.disposition,
       stock.qty_kg, stock.availability, warehouse.warehouse_name,
       site.site_name, org.organization_name
FROM gold.raw_material AS rm
JOIN gold.material_lot AS lot ON lot.material_code = rm.material_code
JOIN gold.material_spec AS spec ON spec.spec_id = lot.spec_id
JOIN gold.supplier AS supplier ON supplier.supplier_id = lot.supplier_id
JOIN gold.goods_receipt AS receipt ON receipt.lot_id = lot.lot_id
JOIN gold.quality_inspection AS inspection ON inspection.lot_id = lot.lot_id
    AND inspection.spec_id = lot.spec_id
JOIN gold.inventory_balance AS stock ON stock.lot_id = lot.lot_id
JOIN gold.warehouse AS warehouse ON warehouse.warehouse_id = stock.warehouse_id
JOIN gold.manufacturing_site AS site ON site.site_id = warehouse.site_id
JOIN gold.organization AS org ON org.organization_id = site.organization_id
WHERE rm.material_code = 'RM-HA-120'
ORDER BY lot.lot_id;

-- QX2: supplier approval and product registration do not approve an alternative material.
SELECT p.product_id, market.market_code, pr.status AS product_registration,
       alt.material_code AS alternative_material, sq.status AS supplier_qualification,
       mr.status AS material_registration
FROM gold.product AS p
JOIN gold.market AS market ON market.market_code = p.market
JOIN gold.product_registration AS pr ON pr.product_id = p.product_id
    AND pr.market_code = market.market_code
JOIN gold.formula_line AS fl ON fl.version_id = p.version_id AND fl.material_code = 'RM-HA-120'
JOIN gold.material_alternative AS mapping ON mapping.material_code = fl.material_code
    AND mapping.approval_status = '승인'
JOIN gold.raw_material AS alt ON alt.material_code = mapping.alt_material_code
JOIN gold.supplier_qualification AS sq ON sq.supplier_id = alt.supplier_id
    AND sq.market_code = market.market_code
JOIN gold.material_registration AS mr ON mr.material_code = alt.material_code
    AND mr.market_code = market.market_code
WHERE p.product_id = 'P-102' AND sq.valid_until >= '2026-11-02'
ORDER BY alt.material_code;

-- QX3: affected candidate plans -> scheduled batches -> line -> site -> organization.
SELECT plan.plan_id, p.product_id, batch.batch_id, fv.version_id,
       line.line_name, site.site_name, org.organization_name
FROM gold.production_plan AS plan
JOIN gold.product AS p ON p.product_id = plan.product_id
JOIN gold.manufacturing_batch AS batch ON batch.plan_id = plan.plan_id
JOIN gold.formula_version AS fv ON fv.version_id = batch.version_id
JOIN gold.production_line AS line ON line.line_id = batch.line_id
JOIN gold.manufacturing_site AS site ON site.site_id = line.site_id
JOIN gold.organization AS org ON org.organization_id = site.organization_id
WHERE EXISTS (
    SELECT 1 FROM gold.formula_line AS fl
    WHERE fl.version_id = fv.version_id AND fl.material_code = 'RM-HA-120'
)
ORDER BY plan.plan_id;

-- QX4: existing change -> project / formula assessment -> responsible team -> organization.
SELECT change.change_id, project.project_id, assessment.assessment_id,
       fv.version_id, team.team_name, org.organization_name, assessment.status
FROM gold.change_request AS change
JOIN gold.dev_project AS project ON project.project_id = change.project_id
JOIN gold.change_assessment AS assessment ON assessment.change_id = change.change_id
JOIN gold.formula_version AS fv ON fv.version_id = assessment.version_id
JOIN gold.team AS team ON team.team_id = assessment.team_id
JOIN gold.organization AS org ON org.organization_id = team.organization_id
WHERE change.material_code IN ('RM-HA-120', 'RM-HA-210')
ORDER BY assessment.assessment_id;
