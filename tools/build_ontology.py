"""Generate the ontology definitions in fabric/ from one compact spec.

Run: python tools/build_ontology.py          (writes fabric/ont_cos_base and fabric/ont_cos_reference)
     python tools/build_ontology.py --check  (fails if the folders are out of date)

ont_cos_base       what participants start with in chapter 01: no uses_material / alternative_to relationships,
                   no is_active / cn_registration properties.
ont_cos_reference  the completed model (fallback when the UI steps cannot be finished).

IDs are derived deterministically from names, so re-running produces identical files.
Placeholders {{WORKSPACE_ID}} and {{LAKEHOUSE_ID}} are replaced by admin/provision.py at deploy time.
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

BASE_MISSING_RELATIONSHIPS = {"uses_material", "alternative_to"}
BASE_MISSING_PROPERTIES = {("FormulaVersion", "is_active"), ("RawMaterial", "cn_registration")}


def num_id(*parts):
    return str(int(hashlib.sha256("/".join(parts).encode()).hexdigest()[:15], 16))


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


def build(folder, base):
    files = {Path("definition.json"): {}}
    for name, (table, key, display, description, synonyms, props) in ENTITIES.items():
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
    for name, (src, dst, table, src_col, dst_col, description) in RELATIONSHIPS.items():
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
                                      "targetPropertyId": num_id("property", src, ENTITIES[src][1])}],
            "targetKeyRefBindings": [{"sourceColumnName": dst_col,
                                      "targetPropertyId": num_id("property", dst, ENTITIES[dst][1])}]}
    return {folder / path: json.dumps(data, indent=2) + "\n" for path, data in files.items()}


def main():
    check = "--check" in sys.argv
    stale = []
    for folder, base in ((FABRIC / "ont_cos_base", True), (FABRIC / "ont_cos_reference", False)):
        expected = build(folder, base)
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
