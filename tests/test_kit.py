"""Offline consistency checks for the workshop kit. Run: python -m unittest discover -s tests -v"""
import ast
import base64
import csv
import json
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = sorted((ROOT / "docs").glob("*.md"))
NOTEBOOKS = ["01_prepare_data", "02_answers", "03_supply_change", "nb_apply_review", "04_publish_serving"]
PLACEHOLDERS = ("{{WORKSPACE_ID}}", "{{LAKEHOUSE_ID}}")


def notebook(name):
    return json.loads((ROOT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))


def code(name):
    return "\n".join("".join(c["source"]) for c in notebook(name)["cells"] if c["cell_type"] == "code")


def rows(table):
    with open(DATA / f"{table}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class Notebooks(unittest.TestCase):
    def test_built_from_sources(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "build_notebooks.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_expected_set(self):
        self.assertEqual(sorted(p.stem for p in (ROOT / "notebooks").glob("*.ipynb")), sorted(NOTEBOOKS))

    def test_provision_imports_all_notebooks(self):
        tree = ast.parse((ROOT / "admin" / "provision.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "NOTEBOOKS")
        self.assertEqual(sorted(ast.literal_eval(node.value)), sorted(NOTEBOOKS))

    def test_code_compiles_and_has_one_parameter_cell(self):
        for name in NOTEBOOKS:
            with self.subTest(name):
                cells = notebook(name)["cells"]
                params = [c for c in cells if "parameters" in c["metadata"].get("tags", [])]
                self.assertEqual(len(params), 1)
                for cell in cells:
                    if cell["cell_type"] == "code":
                        compile("".join(cell["source"]), name, "exec")

    def test_no_bound_lakehouse_or_tenant_ids(self):
        for name in NOTEBOOKS:
            text = (ROOT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8")
            self.assertNotIn("default_lakehouse", text, name)
            self.assertIsNone(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text), name)

    def test_action_parameters(self):
        params = "".join(next(c for c in notebook("nb_apply_review")["cells"]
                              if "parameters" in c["metadata"].get("tags", []))["source"])
        self.assertEqual(re.findall(r"^(\w+) =", params, re.M), ["event_id", "material_code", "eventhouse_name"])

    def test_eventhouse_columns_match_docs(self):
        doc = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        table = re.search(r"\.create-merge table MaterialSupplyEvent \((.*?)\)\n", doc, re.S).group(1)
        columns = [line.strip().split(":")[0] for line in table.strip().splitlines()]
        self.assertEqual(len(columns), 13)
        for name in ("03_supply_change", "nb_apply_review"):
            command = re.search(r"\.set-or-append MaterialSupplyEvent <\|\nprint (.*?)\"\"\"", code(name), re.S).group(1)
            self.assertEqual(re.findall(r"(\w+) = ", command), columns, name)


class Data(unittest.TestCase):
    def tables(self):
        tree = ast.parse((ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "TABLES")
        return ast.literal_eval(node.value)

    def test_csv_headers_match_prepare_notebook(self):
        tables = self.tables()
        self.assertEqual(sorted(tables), sorted(p.stem for p in DATA.glob("*.csv")))
        for table, columns in tables.items():
            with open(DATA / f"{table}.csv", encoding="utf-8", newline="") as f:
                self.assertEqual(next(csv.reader(f)), list(columns), table)

    def test_csv_utf8_without_bom_and_lf(self):
        for path in DATA.glob("*.csv"):
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path.name)
            self.assertNotIn(b"\r\n", raw, path.name)

    def test_row_counts_match_data_design(self):
        doc = (ROOT / "admin" / "data-design.md").read_text(encoding="utf-8")
        for table, count in re.findall(r"^\| `(\w+)` \| (\d+) \| `", doc, re.M):
            self.assertEqual(len(rows(table)), int(count), table)

    def test_impact_scenario(self):
        as_of, delay, qc = date(2026, 11, 2), 35, 7
        material = "RM-HA-120"
        active = {r["version_id"] for r in rows("formula_version") if r["is_active"] == "true"}
        uses = {r["version_id"] for r in rows("formula_line") if r["material_code"] == material} & active
        products = {r["product_id"]: r for r in rows("product")}
        demand = [(r["plan_id"], date.fromisoformat(r["planned_date"]), products[r["product_id"]]["market"])
                  for r in rows("production_plan") if products[r["product_id"]]["version_id"] in uses]
        demand += [(r["test_id"], date.fromisoformat(r["batch_date"]), "KR")
                   for r in rows("stability_test") if r["status"] == "예정" and r["version_id"] in uses]
        eta = min(date.fromisoformat(r["eta"]) for r in rows("purchase_order") if r["material_code"] == material)
        before = {t: (d - timedelta(days=qc) - eta).days for t, d, _ in demand}
        after = {t: (d - timedelta(days=qc) - eta - timedelta(days=delay)).days for t, d, _ in demand}
        self.assertEqual(before, {"PP-1101": 8, "PP-1102": 15, "PP-1103": 64, "ST-0711": 3})
        self.assertEqual(after, {"PP-1101": -27, "PP-1102": -20, "PP-1103": 29, "ST-0711": -32})
        self.assertEqual(sorted(t for t, s in after.items() if s < 0), ["PP-1101", "PP-1102", "ST-0711"])

        raw = {r["material_code"]: r for r in rows("raw_material")}
        approved = [r["alt_material_code"] for r in rows("material_alternative")
                    if r["material_code"] == material and r["approval_status"] == "승인"]
        self.assertEqual(approved, ["RM-HA-210"])
        alt_eta = as_of + timedelta(days=int(raw["RM-HA-210"]["lead_time_days"]))
        self.assertTrue(all(alt_eta <= d - timedelta(days=qc) for _, d, _ in demand))
        self.assertEqual(raw["RM-HA-210"]["cn_registration"], "필요")
        self.assertEqual({m for t, _, m in demand if after[t] < 0}, {"KR", "CN"})


class Docs(unittest.TestCase):
    def test_chapters_linked_from_readme(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for doc in DOCS:
            self.assertIn(f"docs/{doc.name}", readme)

    def test_relative_links_resolve(self):
        for md in [ROOT / "README.md", *DOCS, *sorted((ROOT / "admin").glob("*.md")),
                   ROOT / "assets" / "icon-attribution.md"]:
            text = md.read_text(encoding="utf-8")
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if link.startswith(("http", "#", "mailto:")):
                    continue
                path = (md.parent / link.split("#")[0]).resolve()
                self.assertTrue(path.exists(), f"{md.name}: {link}")

    def test_chapter_navigation(self):
        for i, doc in enumerate(DOCS):
            lines = doc.read_text(encoding="utf-8").splitlines()
            self.assertTrue(lines[0].startswith(f"# {doc.name[:2]}."), doc.name)
            self.assertIn("[목차](../README.md)", lines[2], doc.name)
            if i > 0:
                self.assertIn(f"이전: [", lines[2], doc.name)
                self.assertIn(f"({DOCS[i - 1].name})", lines[2], doc.name)
            if i < len(DOCS) - 1:
                self.assertIn(f"다음: [", lines[2], doc.name)
                self.assertIn(f"({DOCS[i + 1].name})", lines[2], doc.name)

    def test_notebook_names_in_docs_exist(self):
        for md in [ROOT / "README.md", *DOCS, *sorted((ROOT / "admin").glob("*.md"))]:
            for name in re.findall(r"`(\d\d_[a-z_]+|nb_[a-z_]+)`", md.read_text(encoding="utf-8")):
                self.assertIn(name, NOTEBOOKS, f"{md.name}: {name}")

    def test_reusable_lesson_index(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        index = readme.split("## 진행 순서\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| Lesson(장) | 내용 |", index)
        self.assertNotRegex(index, r"오전|휴식|\d+시간|\d+분|진행 방식")
        self.assertNotIn("python -m unittest", readme)
        self.assertIn("## 로컬 점검", (ROOT / "admin" / "README.md").read_text(encoding="utf-8"))
        self.assertEqual([doc.name[:2] for doc in DOCS], [f"{i:02}" for i in range(9)])

    def test_scenario_uses_caldova(self):
        for md in [ROOT / "README.md", *DOCS, ROOT / "admin" / "data-design.md"]:
            text = md.read_text(encoding="utf-8")
            self.assertNotIn("Contoso 코스메틱", text, md.name)
        self.assertIn("Caldova 코스메틱", (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8"))


class Serving(unittest.TestCase):
    def setUp(self):
        # Load the actual notebook helper without importing Fabric/Spark locally.
        source = (ROOT / "notebooks" / "src" / "04_publish_serving.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_publish_sql")
        namespace = {"json": json, "datetime": datetime}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), source, "exec"), namespace)
        self.publish = namespace["build_publish_sql"]
        self.event = "SUP-20261102-RM-HA-120-r1"
        self.records = [
            {
                "request_id": f"RR-{self.event}-{target}", "event_id": self.event,
                "material_code": "RM-HA-120", "target_type": kind, "target_id": target,
                "assignee_team": team, "slack_days": slack, "suggestion": suggestion,
                "request_status": "요청됨", "requested_by": "executor@example.com",
                "requested_at": datetime(2026, 11, 2, 9, 30),
            }
            for target, kind, team, slack, suggestion in [
                ("PP-1101", "생산계획", "구매·생산계획", -27, "RM-HA-210 대체 사용 검토"),
                ("PP-1102", "생산계획", "구매·생산계획", -20, "RM-HA-210 CN 등록 필요 — 등록 또는 일정 조정 검토"),
                ("ST-0711", "안정성시험", "처방개발", -32, "RM-HA-210 대체 사용 검토"),
            ]
        ]

    def decode_payload(self, sql):
        payload = re.search(r"@requests = N'(.*)';\n$", sql, re.S).group(1)
        return json.loads(payload.replace("''", "'"))

    def test_publish_exact_approved_rows(self):
        sql = self.publish(self.event, self.records, 3)
        self.assertIn("@expected_count = 3", sql)
        payload = self.decode_payload(sql)
        self.assertEqual([r["target_id"] for r in payload], ["PP-1101", "PP-1102", "ST-0711"])
        self.assertEqual([r["slack_days"] for r in payload], [-27, -20, -32])
        self.assertEqual(payload[0]["requested_at"], "2026-11-02T09:30:00.000000")
        self.assertNotIn("pct_wt", sql)
        self.assertNotIn("product_id", payload[0])
        schema = (ROOT / "fabric" / "sql" / "serving.sql").read_text(encoding="utf-8")
        columns = re.search(r"FROM OPENJSON\(@requests\) WITH \((.*?)\n    \);", schema, re.S).group(1)
        self.assertEqual(set(re.findall(r"^\s+(\w+)\s+(?:nvarchar|int|datetime2)", columns, re.M)),
                         set(payload[0]))

    def test_sql_literal_roundtrips_quotes_unicode_and_newlines(self):
        self.records[0]["suggestion"] = "O'Brien의 '대체' 원료\n역슬래시 \\ 점검"
        self.records[0]["requested_by"] = "o'brien@example.com"
        sql = self.publish(self.event, self.records, 3)
        self.assertIn("O''Brien", sql)
        self.assertEqual(self.decode_payload(sql)[0]["suggestion"], self.records[0]["suggestion"])
        self.assertEqual(self.decode_payload(sql)[0]["requested_by"], "o'brien@example.com")

    def test_missing_or_mismatched_approval_is_rejected(self):
        for event, records, count in [
            ("", self.records, 3), (self.event, [], 0), (self.event, self.records, 2),
            ("wrong-event", self.records, 3),
        ]:
            with self.subTest(event=event, count=count), self.assertRaises(ValueError):
                self.publish(event, records, count)

    def test_duplicate_and_invalid_requests_are_rejected(self):
        with self.assertRaises(ValueError):
            self.publish(self.event, [self.records[0], self.records[0]], 2)
        for field, value in [("request_id", "wrong-id"), ("request_status", "검토중"), ("requested_at", None)]:
            record = dict(self.records[0], **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.publish(self.event, [record], 1)

    def test_sql_guards_republication_and_workflow_transaction(self):
        # Static contracts only; the administrator must execute Lesson 06 in SQL database.
        sql = (ROOT / "fabric" / "sql" / "serving.sql").read_text(encoding="utf-8")
        publish, start = sql.split("CREATE OR ALTER PROCEDURE serving.usp_start_review", 1)
        self.assertIn("WHERE NOT EXISTS", publish)
        self.assertIn("UPDLOCK, HOLDLOCK", publish)
        self.assertNotIn("UPDATE serving.review_request", publish)
        self.assertIn("request_id nvarchar(200) NOT NULL PRIMARY KEY", sql)
        self.assertIn("SET XACT_ABORT ON", start)
        self.assertIn("BEGIN TRANSACTION", start)
        self.assertIn("AND request_status = N'요청됨'", start)
        self.assertIn("IF @@ROWCOUNT <> 1", start)
        self.assertIn("INSERT INTO serving.workflow_history", start)
        self.assertIn("ORIGINAL_LOGIN()", start)
        self.assertLess(start.index("INSERT INTO serving.workflow_history"), start.index("COMMIT;"))
        self.assertIn("IF XACT_STATE() <> 0 ROLLBACK;", start)


class Architecture(unittest.TestCase):
    def test_built_from_source(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "build_architecture.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_lesson_labels_icons_and_editable_source(self):
        scene = json.loads((ROOT / "assets" / "architecture.excalidraw").read_text(encoding="utf-8"))
        root = ET.parse(ROOT / "assets" / "architecture.svg").getroot()
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        ids = [e["id"] for e in scene["elements"]]
        self.assertEqual(len(ids), len(set(ids)))
        text = "\n".join(e["text"] for e in scene["elements"] if e["type"] == "text")
        for lesson in range(9):
            self.assertIn(f"LESSON {lesson:02}", text)
        for item in scene["elements"]:
            if item["type"] == "text":
                self.assertGreater(item["width"], 0)
                self.assertGreater(item["height"], 0)
                self.assertEqual(item["strokeColor"], "#000000")
            if item["id"] in ("model", "monitor", "serve"):
                self.assertEqual(item["backgroundColor"], "transparent")
            if item["type"] == "image":
                self.assertIn(item["fileId"], scene["files"])
        official = {p.read_bytes() for p in (ROOT / "assets" / "icons").glob("*.svg")}
        embedded = {base64.b64decode(f["dataURL"].split(",", 1)[1]) for f in scene["files"].values()}
        self.assertEqual(official, embedded)


class Ontology(unittest.TestCase):
    def test_built_from_spec(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "build_ontology.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_counts_and_placeholders(self):
        for folder, relationships in (("ont_cos_base", 8), ("ont_cos_reference", 10)):
            with self.subTest(folder):
                path = ROOT / "fabric" / folder
                self.assertEqual(len(list(path.glob("EntityTypes/*/definition.json"))), 9)
                self.assertEqual(len([p for p in (path / "RelationshipTypes").iterdir() if p.is_dir()]), relationships)
                for item in path.rglob("*.json"):
                    text = item.read_text(encoding="utf-8")
                    for key in ("workspaceId", "itemId"):
                        for value in re.findall(rf'"{key}": "([^"]+)"', text):
                            self.assertIn(value, PLACEHOLDERS, item)

    def test_base_omits_what_participants_add(self):
        base = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "fabric" / "ont_cos_base").rglob("*.json"))
        ref = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "fabric" / "ont_cos_reference").rglob("*.json"))
        for name in ("uses_material", "alternative_to", "is_active", "cn_registration"):
            self.assertNotIn(f'"{name}"', base, name)
            self.assertIn(f'"{name}"', ref, name)


if __name__ == "__main__":
    unittest.main()
