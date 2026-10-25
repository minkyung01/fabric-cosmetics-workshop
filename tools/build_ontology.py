"""Generate the ontology definitions in fabric/ from one compact spec.

Run: python tools/build_ontology.py          (writes fabric/ont_cos_base, ont_cos_reference and ont_cos_extended)
     python tools/build_ontology.py --check  (fails if the folders are out of date)

ont_cos_base       what participants start with in chapter 01: no uses_material / alternative_to relationships,
                   no is_active / cn_registration properties.
ont_cos_reference  the completed model (fallback when the UI steps cannot be finished).
ont_cos_extended   opt-in completed model: 26 entities / 40 relationships over 28 tables.

IDs are derived deterministically from names, so re-running produces identical files.
Placeholders {{WORKSPACE_ID}} and {{LAKEHOUSE_ID}} are replaced by admin/provision.py at deploy time.
These v1.0.0 definitions require the old/new experience preflight in admin/preview-limitations.md.
"""
import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FABRIC = ROOT / "fabric"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/ontology/{}/1.0.0/schema.json"
NS = uuid.UUID("6f1c2b8e-3d7a-4c1e-9b8a-2a5d0e7c4f10")
WS, LH, SOURCE_SCHEMA = "{{WORKSPACE_ID}}", "{{LAKEHOUSE_ID}}", "gold"

# entity: (table, key, display, description, synonyms, [(column, type, description)])
ENTITIES = {
    "Ingredient": ("ingredient", "ingredient_id", "korean_name", "화장품 성분(INCI 기준). 여러 원료가 같은 성분을 가질 수 있다.",
                   ["성분", "INCI"], [
        ("ingredient_id", "String", "성분 ID"), ("inci_name", "String", "INCI 명칭"),
        ("korean_name", "String", "성분 한글명"), ("function", "String", "주요 기능")]),
    "Supplier": ("supplier", "supplier_id", "supplier_name", "원료 공급사", ["공급사", "벤더"], [
        ("supplier_id", "String", "공급사 ID"), ("supplier_name", "String", "공급사명"),
        ("country", "String", "국가 코드"), ("risk_grade", "String", "공급 리스크 등급(사내 평가)")]),
    "RawMaterial": ("raw_material", "material_code", "material_name",
                    "구매 단위의 원료. 같은 성분이라도 공급사·규격이 다르면 다른 원료다.", ["원료", "원재료", "RM"], [
        ("material_code", "String", "원료 코드"), ("material_name", "String", "원료명"),
        ("ingredient_id", "String", "성분 ID"), ("supplier_id", "String", "공급사 ID"),
        ("lead_time_days", "BigInt", "발주부터 입고까지 리드타임(일)"), ("unit_price_krw", "BigInt", "kg당 단가(원)"),
        ("cn_registration", "String", "중국 시장 원료 등록 상태(사내 가상 기준). 완료일 때만 CN 판매 제품에 사용")]),
    "FormulaVersion": ("formula_version", "version_id", "version_id",
                       "처방의 특정 버전. 제품과 개발 과제는 처방 버전을 가리킨다.", ["처방", "처방 버전", "포뮬러"], [
        ("version_id", "String", "처방 버전 ID"), ("formula_id", "String", "처방 ID"),
        ("formula_name", "String", "처방명"), ("version_no", "BigInt", "버전 번호"),
        ("status", "String", "현행·개발중·폐기"),
        ("is_active", "Boolean", "영향 분석 대상 여부. 현행·개발중이면 true, 폐기면 false"),
        ("approved_date", "DateTime", "처방 승인일(개발중이면 비어 있음)")]),
    "Product": ("product", "product_id", "product_name", "판매 제품(SKU). 시장별로 다른 제품 ID를 가진다.", ["제품", "SKU"], [
        ("product_id", "String", "제품 ID"), ("product_name", "String", "제품명"),
        ("version_id", "String", "현재 처방 버전 ID"), ("market", "String", "판매 시장(KR, CN)"),
        ("sales_status", "String", "판매 상태")]),
    "DevProject": ("dev_project", "project_id", "project_name", "신제품 개발 과제", ["개발 과제", "프로젝트"], [
        ("project_id", "String", "개발 과제 ID"), ("project_name", "String", "과제명"),
        ("version_id", "String", "개발 중인 처방 버전 ID"), ("stage", "String", "현재 단계"),
        ("owner", "String", "담당 조직"), ("target_launch", "DateTime", "목표 출시일")]),
    "StabilityTest": ("stability_test", "test_id", "test_id", "처방 버전의 안정성 시험. 배치일에 원료가 필요하다.",
                      ["안정성 시험", "시험"], [
        ("test_id", "String", "시험 ID"), ("version_id", "String", "시험 대상 처방 버전 ID"),
        ("project_id", "String", "개발 과제 ID"), ("batch_date", "DateTime", "시험 배치 제조일"),
        ("condition", "String", "시험 조건"), ("status", "String", "예정·진행·완료")]),
    "ProductionPlan": ("production_plan", "plan_id", "plan_id", "제품 생산 계획. 계획일에 원료가 필요하다.", ["생산 계획"], [
        ("plan_id", "String", "생산 계획 ID"), ("product_id", "String", "제품 ID"),
        ("planned_date", "DateTime", "생산 계획일"), ("qty_ea", "BigInt", "계획 수량(개)")]),
    "PurchaseOrder": ("purchase_order", "po_id", "po_id", "원료 구매 발주", ["발주", "PO"], [
        ("po_id", "String", "발주 ID"), ("material_code", "String", "원료 코드"),
        ("supplier_id", "String", "공급사 ID"), ("qty_kg", "Double", "발주량(kg)"),
        ("order_date", "DateTime", "발주일"), ("eta", "DateTime", "입고 예정일"),
        ("status", "String", "확정·지연·입고")]),
}

# relationship: (source entity, target entity, table, source column, target column, description)
RELATIONSHIPS = {
    "has_ingredient": ("RawMaterial", "Ingredient", "raw_material", "material_code", "ingredient_id", "원료에 들어 있는 성분"),
    "supplied_by": ("RawMaterial", "Supplier", "raw_material", "material_code", "supplier_id", "원료를 공급하는 공급사"),
    "uses_material": ("FormulaVersion", "RawMaterial", "formula_line", "version_id", "material_code", "처방 버전이 사용하는 원료"),
    "made_with": ("Product", "FormulaVersion", "product", "product_id", "version_id", "제품의 현재 처방 버전"),
    "develops": ("DevProject", "FormulaVersion", "dev_project", "project_id", "version_id", "개발 과제가 개발 중인 처방 버전"),
    "tests_version": ("StabilityTest", "FormulaVersion", "stability_test", "test_id", "version_id", "안정성 시험 대상 처방 버전"),
    "for_project": ("StabilityTest", "DevProject", "stability_test", "test_id", "project_id", "안정성 시험이 속한 개발 과제"),
    "produces": ("ProductionPlan", "Product", "production_plan", "plan_id", "product_id", "생산 계획이 만드는 제품"),
    "orders": ("PurchaseOrder", "RawMaterial", "purchase_order", "po_id", "material_code", "발주한 원료"),
    "alternative_to": ("RawMaterial", "RawMaterial", "material_alternative", "material_code", "alt_material_code",
                       "대체 가능 원료 후보. 승인 상태는 material_alternative.approval_status에서 확인"),
}

EXTENDED_ENTITIES = {
    "Organization": ("organization", "organization_id", "organization_name", "업무 조직", ["조직"], [
        ("organization_id", "String", "조직 ID"), ("organization_name", "String", "조직명")]),
    "Team": ("team", "team_id", "team_name", "변경 검토를 담당하는 팀", ["담당 팀"], [
        ("team_id", "String", "팀 ID"), ("organization_id", "String", "소속 조직 ID"),
        ("team_name", "String", "팀명")]),
    "SupplierQualification": ("supplier_qualification", "qualification_id", "qualification_id",
        "공급사의 시장별 사내 자격 평가. 원료 등록이나 대체 승인과 다르다.", ["공급사 자격"], [
        ("qualification_id", "String", "자격 평가 ID"), ("supplier_id", "String", "공급사 ID"),
        ("market_code", "String", "평가 시장"), ("status", "String", "승인·검토중"),
        ("valid_until", "DateTime", "자격 유효 기한")]),
    "MaterialSpec": ("material_spec", "spec_id", "spec_name", "원료별 품질 규격", ["원료 규격"], [
        ("spec_id", "String", "규격 ID"), ("material_code", "String", "원료 코드"),
        ("spec_name", "String", "규격명")]),
    "MaterialLot": ("material_lot", "lot_id", "lot_id", "원료 입고 로트. 같은 원료라도 사용 가능 상태가 다르다.",
        ["원료 로트"], [
        ("lot_id", "String", "로트 ID"), ("material_code", "String", "원료 코드"),
        ("supplier_id", "String", "공급사 ID"), ("spec_id", "String", "규격 ID"),
        ("expiry_date", "DateTime", "사용 기한"), ("disposition", "String", "사용가능·격리")]),
    "GoodsReceipt": ("goods_receipt", "receipt_id", "receipt_id", "구매 발주의 부분 입고 이력", ["입고"], [
        ("receipt_id", "String", "입고 ID"), ("po_id", "String", "발주 ID"), ("lot_id", "String", "로트 ID"),
        ("received_date", "DateTime", "입고일"), ("qty_kg", "Double", "입고량 kg")]),
    "QualityInspection": ("quality_inspection", "inspection_id", "inspection_id", "규격을 기준으로 수행한 로트 검사",
        ["품질검사"], [
        ("inspection_id", "String", "검사 ID"), ("lot_id", "String", "로트 ID"),
        ("spec_id", "String", "규격 ID"), ("result", "String", "적합·부적합"),
        ("inspected_date", "DateTime", "검사일")]),
    "Warehouse": ("warehouse", "warehouse_id", "warehouse_name", "제조소 내 원료 창고", ["창고"], [
        ("warehouse_id", "String", "창고 ID"), ("site_id", "String", "제조소 ID"),
        ("warehouse_name", "String", "창고명")]),
    "InventoryBalance": ("inventory_balance", "balance_id", "balance_id",
        "기준일의 로트·창고별 재고 스냅샷. 핵심 일정 영향 계산에는 합산하지 않는다.", ["재고"], [
        ("balance_id", "String", "재고 잔량 ID"), ("lot_id", "String", "로트 ID"),
        ("warehouse_id", "String", "창고 ID"), ("qty_kg", "Double", "잔량 kg"),
        ("availability", "String", "가용·격리")]),
    "ManufacturingSite": ("manufacturing_site", "site_id", "site_name", "생산 운영 조직의 제조소", ["제조소"], [
        ("site_id", "String", "제조소 ID"), ("organization_id", "String", "조직 ID"),
        ("site_name", "String", "제조소명")]),
    "ProductionLine": ("production_line", "line_id", "line_name", "제조소의 생산 라인", ["생산 라인"], [
        ("line_id", "String", "라인 ID"), ("site_id", "String", "제조소 ID"), ("line_name", "String", "라인명")]),
    "ManufacturingBatch": ("manufacturing_batch", "batch_id", "batch_id", "생산 계획을 처방·설비에 연결한 제조 배치",
        ["제조 배치"], [
        ("batch_id", "String", "배치 ID"), ("plan_id", "String", "생산 계획 ID"),
        ("line_id", "String", "라인 ID"), ("version_id", "String", "처방 버전 ID"), ("status", "String", "배치 상태")]),
    "Market": ("market", "market_code", "market_name", "제품 판매·원료 등록을 구분하는 시장", ["시장"], [
        ("market_code", "String", "시장 코드"), ("market_name", "String", "시장명")]),
    "MaterialRegistration": ("material_registration", "registration_id", "registration_id",
        "원료의 시장별 가상 등록 상태. 실제 법규 정보가 아니다.", ["원료 등록"], [
        ("registration_id", "String", "등록 ID"), ("material_code", "String", "원료 코드"),
        ("market_code", "String", "시장 코드"), ("status", "String", "완료·필요")]),
    "ProductRegistration": ("product_registration", "registration_id", "registration_id",
        "제품의 시장별 가상 등록 상태. 원료 등록을 대신하지 않는다.", ["제품 등록"], [
        ("registration_id", "String", "등록 ID"), ("product_id", "String", "제품 ID"),
        ("market_code", "String", "시장 코드"), ("status", "String", "등록 상태")]),
    "ChangeRequest": ("change_request", "change_id", "change_id",
        "기준일 이전부터 존재하는 변경 검토. 승인 액션의 ops.review_request와 별개이다.", ["기존 변경 건"], [
        ("change_id", "String", "변경 ID"), ("material_code", "String", "원료 코드"),
        ("project_id", "String", "개발 과제 ID"), ("team_id", "String", "주관 팀 ID"),
        ("status", "String", "변경 검토 상태")]),
    "ChangeAssessment": ("change_assessment", "assessment_id", "assessment_id", "변경 건별 처방 평가와 담당 팀",
        ["변경 평가"], [
        ("assessment_id", "String", "평가 ID"), ("change_id", "String", "변경 ID"),
        ("version_id", "String", "처방 버전 ID"), ("team_id", "String", "평가 담당 팀 ID"),
        ("status", "String", "평가 상태")]),
}

EXTENDED_RELATIONSHIPS = {
    "team_in_org": ("Team", "Organization", "team", "team_id", "organization_id", "팀의 소속 조직"),
    "site_in_org": ("ManufacturingSite", "Organization", "manufacturing_site", "site_id", "organization_id", "제조소 운영 조직"),
    "line_at_site": ("ProductionLine", "ManufacturingSite", "production_line", "line_id", "site_id", "생산 라인의 제조소"),
    "warehouse_at_site": ("Warehouse", "ManufacturingSite", "warehouse", "warehouse_id", "site_id", "창고의 제조소"),
    "qualifies_supplier": ("SupplierQualification", "Supplier", "supplier_qualification", "qualification_id", "supplier_id", "평가 대상 공급사"),
    "qualification_market": ("SupplierQualification", "Market", "supplier_qualification", "qualification_id", "market_code", "자격 평가 시장"),
    "specifies_material": ("MaterialSpec", "RawMaterial", "material_spec", "spec_id", "material_code", "규격 대상 원료"),
    "lot_of_material": ("MaterialLot", "RawMaterial", "material_lot", "lot_id", "material_code", "로트의 원료"),
    "lot_from_supplier": ("MaterialLot", "Supplier", "material_lot", "lot_id", "supplier_id", "로트의 공급사"),
    "lot_has_spec": ("MaterialLot", "MaterialSpec", "material_lot", "lot_id", "spec_id", "로트의 품질 규격"),
    "receipt_for_order": ("GoodsReceipt", "PurchaseOrder", "goods_receipt", "receipt_id", "po_id", "부분 입고의 발주"),
    "receives_lot": ("GoodsReceipt", "MaterialLot", "goods_receipt", "receipt_id", "lot_id", "입고 로트"),
    "inspects_lot": ("QualityInspection", "MaterialLot", "quality_inspection", "inspection_id", "lot_id", "검사 대상 로트"),
    "inspection_uses_spec": ("QualityInspection", "MaterialSpec", "quality_inspection", "inspection_id", "spec_id", "검사 기준 규격"),
    "inventory_of_lot": ("InventoryBalance", "MaterialLot", "inventory_balance", "balance_id", "lot_id", "재고의 로트"),
    "stored_in": ("InventoryBalance", "Warehouse", "inventory_balance", "balance_id", "warehouse_id", "재고 보관 창고"),
    "batch_for_plan": ("ManufacturingBatch", "ProductionPlan", "manufacturing_batch", "batch_id", "plan_id", "배치의 생산 계획"),
    "batch_on_line": ("ManufacturingBatch", "ProductionLine", "manufacturing_batch", "batch_id", "line_id", "배치의 생산 라인"),
    "batch_uses_version": ("ManufacturingBatch", "FormulaVersion", "manufacturing_batch", "batch_id", "version_id", "배치의 처방 버전"),
    "sold_in_market": ("Product", "Market", "product", "product_id", "market", "제품의 판매 시장"),
    "registers_material": ("MaterialRegistration", "RawMaterial", "material_registration", "registration_id", "material_code", "등록 대상 원료"),
    "material_registered_in": ("MaterialRegistration", "Market", "material_registration", "registration_id", "market_code", "원료 등록 시장"),
    "registers_product": ("ProductRegistration", "Product", "product_registration", "registration_id", "product_id", "등록 대상 제품"),
    "product_registered_in": ("ProductRegistration", "Market", "product_registration", "registration_id", "market_code", "제품 등록 시장"),
    "change_of_material": ("ChangeRequest", "RawMaterial", "change_request", "change_id", "material_code", "변경 대상 원료"),
    "change_for_project": ("ChangeRequest", "DevProject", "change_request", "change_id", "project_id", "변경 검토의 과제"),
    "change_owned_by": ("ChangeRequest", "Team", "change_request", "change_id", "team_id", "변경 주관 팀"),
    "assesses_change": ("ChangeAssessment", "ChangeRequest", "change_assessment", "assessment_id", "change_id", "평가의 변경 건"),
    "assesses_version": ("ChangeAssessment", "FormulaVersion", "change_assessment", "assessment_id", "version_id", "평가 대상 처방"),
    "assessment_owned_by": ("ChangeAssessment", "Team", "change_assessment", "assessment_id", "team_id", "평가 담당 팀"),
}

BASE_MISSING_RELATIONSHIPS = {"uses_material", "alternative_to"}
BASE_MISSING_PROPERTIES = {("FormulaVersion", "is_active"), ("RawMaterial", "cn_registration")}


def num_id(*parts):
    return str(int(hashlib.sha256("/".join(parts).encode()).hexdigest()[:15], 16))


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


def build(folder, base, extended=False):
    entities = {**ENTITIES, **EXTENDED_ENTITIES} if extended else ENTITIES
    relationships = {**RELATIONSHIPS, **EXTENDED_RELATIONSHIPS} if extended else RELATIONSHIPS
    files = {Path("definition.json"): {}}
    for name, (table, key, display, description, synonyms, props) in entities.items():
        eid = num_id("entity", name)
        props = [p for p in props if not (base and (name, p[0]) in BASE_MISSING_PROPERTIES)]
        pid = {col: num_id("property", name, col) for col, _, _ in props}
        files[Path("EntityTypes", eid, "definition.json")] = {
            "$schema": SCHEMA.format("entityType"), "id": eid, "namespace": "usertypes", "baseEntityTypeId": None,
            "name": name, "entityIdParts": [pid[key]], "displayNamePropertyId": pid[display],
            "namespaceType": "Custom", "visibility": "Visible",
            "properties": [{"id": pid[col], "name": col, "redefines": None, "baseTypeNamespaceType": None,
                            "valueType": vtype, "semanticEnrichment": {"description": desc, "customAttributes": {}}}
                           for col, vtype, desc in props],
            "timeseriesProperties": [],
            "semanticEnrichment": {"synonyms": synonyms, "description": description, "customAttributes": {}},
            "untypedProperties": []}
        binding = uid("binding", name)
        files[Path("EntityTypes", eid, "DataBindings", f"{binding}.json")] = {
            "$schema": SCHEMA.format("dataBinding"), "id": binding,
            "dataBindingConfiguration": {
                "dataBindingType": "NonTimeSeries",
                "propertyBindings": [{"sourceColumnName": col, "targetPropertyId": pid[col]} for col, _, _ in props],
                "sourceTableProperties": {"sourceType": "LakehouseTable", "workspaceId": WS, "itemId": LH,
                                          "sourceTableName": table, "sourceSchema": SOURCE_SCHEMA}}}
    for name, (src, dst, table, src_col, dst_col, description) in relationships.items():
        if base and name in BASE_MISSING_RELATIONSHIPS:
            continue
        rid = num_id("relationship", name)
        files[Path("RelationshipTypes", rid, "definition.json")] = {
            "$schema": SCHEMA.format("relationshipType"), "namespace": "usertypes", "id": rid, "name": name,
            "namespaceType": "Custom", "source": {"entityTypeId": num_id("entity", src)},
            "target": {"entityTypeId": num_id("entity", dst)},
            "semanticEnrichment": {"description": description, "customAttributes": {}}}
        ctx = uid("contextualization", name)
        files[Path("RelationshipTypes", rid, "Contextualizations", f"{ctx}.json")] = {
            "$schema": SCHEMA.format("contextualization"), "id": ctx,
            "dataBindingTable": {"workspaceId": WS, "itemId": LH, "sourceTableName": table,
                                 "sourceSchema": SOURCE_SCHEMA, "sourceType": "LakehouseTable"},
            "sourceKeyRefBindings": [{"sourceColumnName": src_col,
                                      "targetPropertyId": num_id("property", src, entities[src][1])}],
            "targetKeyRefBindings": [{"sourceColumnName": dst_col,
                                      "targetPropertyId": num_id("property", dst, entities[dst][1])}]}
    return {folder / path: json.dumps(data, indent=2) + "\n" for path, data in files.items()}


def main():
    check = "--check" in sys.argv
    stale = []
    for name, base, extended in (("ont_cos_base", True, False), ("ont_cos_reference", False, False),
                                 ("ont_cos_extended", False, True)):
        folder = FABRIC / name
        expected = build(folder, base, extended)
        if check:
            actual = {p: p.read_text(encoding="utf-8") for p in folder.rglob("*.json")} if folder.exists() else {}
            if actual != expected:
                stale.append(folder.name)
            continue
        if folder.exists():
            shutil.rmtree(folder)
        for path, text in expected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        print(f"built {folder.relative_to(ROOT)} ({sum(1 for p in expected if p.parent.parent.name == 'EntityTypes')} entities)")
    if stale:
        sys.exit("Out of date (run python tools/build_ontology.py): " + ", ".join(stale))


if __name__ == "__main__":
    main()
