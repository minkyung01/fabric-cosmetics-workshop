"""Offline consistency checks for the workshop kit. Run: python -m unittest discover -s tests -v"""
import ast
import base64
import csv
import io
import json
import re
import runpy
import sqlite3
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = sorted((ROOT / "docs").glob("*.md"))
ALL_DOCS = sorted((ROOT / "docs").rglob("*.md"))
NOTEBOOKS = ["01_prepare_data", "02_answers", "03_supply_change", "nb_apply_review", "04_publish_serving"]
PLACEHOLDERS = ("{{WORKSPACE_ID}}", "{{LAKEHOUSE_ID}}")


def notebook(name):
    return json.loads((ROOT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))


def code(name):
    return "\n".join("".join(c["source"]) for c in notebook(name)["cells"] if c["cell_type"] == "code")


def rows(table):
    path = DATA / f"{table}.csv"
    if not path.exists():
        path = DATA / "extended" / f"{table}.csv"
    with open(path, encoding="utf-8", newline="") as f:
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
    def tables(self, name="TABLES"):
        tree = ast.parse((ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name)
        return ast.literal_eval(node.value)

    def test_csv_headers_match_prepare_notebook(self):
        tables = self.tables()
        self.assertEqual(sorted(tables), sorted(p.stem for p in DATA.glob("*.csv")))
        for table, columns in tables.items():
            with open(DATA / f"{table}.csv", encoding="utf-8", newline="") as f:
                self.assertEqual(next(csv.reader(f)), list(columns), table)

    def test_csv_utf8_without_bom_and_lf(self):
        for path in DATA.rglob("*.csv"):
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
        for md in [ROOT / "README.md", *ALL_DOCS, *sorted((ROOT / "admin").glob("*.md")),
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
        for md in [ROOT / "README.md", *ALL_DOCS, *sorted((ROOT / "admin").glob("*.md"))]:
            for name in re.findall(r"`(\d\d_[a-z_]+|nb_[a-z_]+)`", md.read_text(encoding="utf-8")):
                self.assertIn(name, NOTEBOOKS, f"{md.name}: {name}")

    def test_reusable_lesson_index(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        index = readme.split("## 진행 순서\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| Lesson(장) | 내용 |", index)
        self.assertNotRegex(index, r"오전|휴식|\d+시간|\d+분|진행 방식")
        self.assertNotIn("python -m unittest", readme)
        self.assertIn("## 로컬 점검", (ROOT / "admin" / "README.md").read_text(encoding="utf-8"))
        self.assertEqual([doc.name[:2] for doc in DOCS], [f"{i:02}" for i in range(8)])
        features = readme.split("## 이 실습에서 완성하는 것\n", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn("Lesson", features)
        self.assertNotIn("Ontology는 용어집만이 아닙니다", readme)
        self.assertIn("Ontology는 용어집만이 아닙니다", (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8"))
        self.assertNotIn("[원본 SVG]", readme)
        self.assertNotIn("[편집 가능한 Excalidraw]", readme)
        self.assertNotIn("Data Highway", "\n".join(p.read_text(encoding="utf-8") for p in [ROOT / "README.md", *DOCS]))

    def test_scenario_uses_caldova(self):
        for md in [ROOT / "README.md", *DOCS, ROOT / "admin" / "data-design.md"]:
            text = md.read_text(encoding="utf-8")
            self.assertNotIn("Contoso 코스메틱", text, md.name)
        self.assertIn("Caldova 코스메틱", (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8"))

    def test_introduction_does_not_reveal_impact_answers(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        for spoiler in ("정답 미리 보기", "PP-1101", "PP-1102", "PP-1103", "ST-0711", "29일", "영향 대상 3건"):
            self.assertNotIn(spoiler, scenario)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("영향 대상 3건", readme)
        self.assertIn("대상 ID·연결 경로·일정 근거·검토할 조치", scenario)
        self.assertIn("PP-1101", (ROOT / "admin" / "data-design.md").read_text(encoding="utf-8"))

    def test_participant_guides_do_not_require_instructor_demos_or_admin_commands(self):
        for md in [ROOT / "README.md", *ALL_DOCS]:
            text = md.read_text(encoding="utf-8")
            with self.subTest(document=md.relative_to(ROOT)):
                self.assertNotRegex(text, r"강사|시연|## 관리자 준비|관리자 사전 준비|provision\.py|--capacity")
        extension = ROOT / "docs" / "extensions" / "ontology.md"
        self.assertIn("docs/extensions/ontology.md", (ROOT / "README.md").read_text(encoding="utf-8"))
        extension_text = extension.read_text(encoding="utf-8")
        self.assertIn("<details>", extension_text)
        self.assertEqual(extension_text.count("<details>"), extension_text.count("</details>"))
        self.assertIn("--extended-ontology", (ROOT / "admin" / "extended-model.md").read_text(encoding="utf-8"))
        for path in (ROOT / "notebooks" / "src").glob("*.py"):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"강사|시연|관리자 사전 실행")

    def test_ontology_agent_creation_and_improvement_have_separate_source_scopes(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        self.assertIn("## 1. 빈 Ontology 만들기", lesson)
        self.assertIn("## 4. 추가 질문으로 모델 보강하기", lesson)
        self.assertIn("기존 항목·ID·키·바인딩은 보존", lesson)
        self.assertNotIn("관리자가 배포한 기본 Ontology", lesson)
        prompts = re.findall(r"```text\n(.*?)```", lesson, re.S)
        core = set(Data().tables())
        initial = set(re.findall(r"\b\w+\b", prompts[0])) & core
        self.assertEqual(initial, {"ingredient", "raw_material", "supplier", "purchase_order",
                                   "formula_version", "formula_line", "product"})
        improvement = next(p for p in prompts if "보강하는 변경안" in p)
        added = (set(re.findall(r"\b\w+\b", improvement)) & core) - initial
        self.assertEqual(added, {"production_plan", "dev_project", "stability_test", "material_alternative"})
        self.assertEqual(initial | added, core)
        self.assertIn("Boolean", improvement)
        self.assertIn("cn_registration", improvement)
        self.assertIn("변경 미리 보기", improvement)
        for prompt in prompts:
            if "검토한 초안만 현재 ont_cos에 적용해줘." in prompt:
                self.assertIn("원본은 읽기만 하고", prompt)
            else:
                self.assertNotRegex(prompt, r"Ontology나 작업 영역은 변경하지 마|아직 적용하지 마|먼저 Plan에서")
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertIn("지금은 없어도 정상", scenario)

    def test_ontology_checkpoint_matches_core_keys_and_relationship_mappings(self):
        spec = runpy.run_path(str(ROOT / "tools" / "build_ontology.py"))
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        entities = {name: (table, key) for name, table, key in
                    re.findall(r"^\| `(\w+)` \| `(\w+)` \| `(\w+)` \|", lesson, re.M)}
        self.assertEqual(entities, {name: value[:2] for name, value in spec["ENTITIES"].items()})
        relationships = {name: (src, dst, table, src_col, dst_col)
                         for name, src, dst, table, src_col, dst_col in re.findall(
                             r"^\| `(\w+)` \| (\w+) → (\w+) \| `(\w+)\.(\w+) → (\w+)` \|", lesson, re.M)}
        self.assertEqual(relationships, {name: value[:5] for name, value in spec["RELATIONSHIPS"].items()})


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
        for lesson in range(8):
            self.assertIn(f"LESSON {lesson:02}", text)
        self.assertNotIn("LESSON 08", text)
        self.assertNotIn("Lesson 번호", text)
        self.assertNotIn("공식 Fabric 아이콘 사용", text)
        self.assertNotIn("영향 3건", text)
        self.assertIn("Ontology Agent로 초안·보강", text)
        self.assertIn("teams-icon", ids)
        for edge in ("ontology-graph", "graph-dataagent"):
            self.assertEqual(next(e for e in scene["elements"] if e["id"] == edge)["strokeStyle"], "dashed")
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
        for folder, entities, relationships in (("ont_cos_base", 9, 8), ("ont_cos_reference", 9, 10),
                                                 ("ont_cos_extended", 26, 40)):
            with self.subTest(folder):
                path = ROOT / "fabric" / folder
                self.assertEqual(len(list(path.glob("EntityTypes/*/definition.json"))), entities)
                self.assertEqual(len([p for p in (path / "RelationshipTypes").iterdir() if p.is_dir()]), relationships)
                for item in path.rglob("*.json"):
                    text = item.read_text(encoding="utf-8")
                    for key in ("workspaceId", "itemId"):
                        for value in re.findall(rf'"{key}": "([^"]+)"', text):
                            self.assertIn(value, PLACEHOLDERS, item)

    def test_intermediate_recovery_reference_omits_two_relations_and_properties(self):
        base = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "fabric" / "ont_cos_base").rglob("*.json"))
        ref = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "fabric" / "ont_cos_reference").rglob("*.json"))
        for name in ("uses_material", "alternative_to", "is_active", "cn_registration"):
            self.assertNotIn(f'"{name}"', base, name)
            self.assertIn(f'"{name}"', ref, name)


class ExtendedModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = runpy.run_path(str(ROOT / "tools" / "build_ontology.py"))
        cls.entities = {**cls.spec["ENTITIES"], **cls.spec["EXTENDED_ENTITIES"]}
        cls.relationships = {**cls.spec["RELATIONSHIPS"], **cls.spec["EXTENDED_RELATIONSHIPS"]}
        cls.schemas = {**Data().tables(), **Data().tables("EXTENDED_TABLES")}

    def test_exact_expansion_and_prepare_headers(self):
        self.assertEqual(len(self.entities), 26)
        self.assertEqual(len(self.relationships), 40)
        self.assertEqual(len(self.schemas), 28)
        self.assertEqual(set(Data().tables("EXTENDED_TABLES")), {p.stem for p in (DATA / "extended").glob("*.csv")})
        for table, schema in self.schemas.items():
            records = rows(table)
            self.assertEqual(list(records[0]), list(schema), table)
            for record in records:
                for column, kind in schema.items():
                    value = record[column]
                    if not value:
                        continue
                    if kind == "date":
                        date.fromisoformat(value)
                    elif kind == "double":
                        float(value)
                    elif kind == "bigint":
                        int(value)
                    elif kind == "boolean":
                        self.assertIn(value, ("true", "false"))

    def test_prepare_profile_selection_and_partial_upload_rejection(self):
        source = (ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8")
        helper = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "select_tables")
        namespace = {"TABLES": Data().tables(), "EXTENDED_TABLES": Data().tables("EXTENDED_TABLES")}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), source, "exec"), namespace)
        select = namespace["select_tables"]
        core = {f"{t}.csv" for t in namespace["TABLES"]}
        extended = {f"{t}.csv" for t in namespace["EXTENDED_TABLES"]}
        self.assertEqual(set(select(core)), set(namespace["TABLES"]))
        self.assertEqual(set(select(core | extended)), set(self.schemas))
        for missing in core | extended:
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                select((core | extended) - {missing})
        self.assertEqual(set(select(core | {"unrelated.txt"})), set(namespace["TABLES"]))

    def test_entities_bound_to_unique_keys_and_typed_columns(self):
        types = {"string": "String", "bigint": "BigInt", "double": "Double", "boolean": "Boolean", "date": "DateTime"}
        for entity, (table, key, display, _, _, props) in self.entities.items():
            with self.subTest(entity=entity):
                values = [r[key] for r in rows(table)]
                self.assertTrue(all(values))
                self.assertEqual(len(values), len(set(values)))
                self.assertIn(display, self.schemas[table])
                self.assertEqual({p[0]: p[1] for p in props},
                                 {c: types[t] for c, t in self.schemas[table].items()})

    def test_all_relationship_endpoints_resolve_and_model_is_connected(self):
        adjacency = {entity: set() for entity in self.entities}
        for name, (src, dst, table, src_col, dst_col, _) in self.relationships.items():
            with self.subTest(relationship=name):
                for entity, column in ((src, src_col), (dst, dst_col)):
                    entity_table, key = self.entities[entity][:2]
                    targets = {r[key] for r in rows(entity_table)}
                    self.assertTrue({r[column] for r in rows(table)} <= targets)
                adjacency[src].add(dst)
                adjacency[dst].add(src)
        seen, pending = set(), ["RawMaterial"]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(adjacency[node] - seen)
        self.assertEqual(seen, set(self.entities))

    def test_extended_definition_preserves_completed_core(self):
        build = self.spec["build"]
        core = build(Path("model"), False)
        expanded = build(Path("model"), False, True)
        self.assertTrue(core.items() <= expanded.items())

    def test_provision_profiles_do_not_expand_core_by_default(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        self.assertEqual(len(provision["data_files"](False)), 11)
        files = provision["data_files"](True)
        self.assertEqual(len(files), 28)
        self.assertEqual(len({f.name for f in files}), 28)
        parts = provision["definition_parts"](ROOT / "fabric" / "ont_cos_extended",
                                               {"{{WORKSPACE_ID}}": "test-workspace", "{{LAKEHOUSE_ID}}": "test-lakehouse"})
        self.assertTrue(parts)
        for part in parts:
            decoded = base64.b64decode(part["payload"]).decode()
            self.assertNotIn("{{", decoded)
            json.loads(decoded)

    def test_provision_uploads_selected_profile_and_keeps_existing_core_ontology(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        for reference, extended, existing in ((False, False, False), (False, False, True),
                                               (True, False, False), (True, False, True),
                                               (False, True, False), (False, True, True),
                                               (True, True, False), (True, True, True)):
            with self.subTest(reference=reference, extended=extended, existing=existing):
                items = [{"type": "Lakehouse", "displayName": "lh_cos", "id": "test-lakehouse"},
                         {"type": "Eventhouse", "displayName": "eh_cos", "id": "test-eventhouse"}]
                if existing:
                    items.append({"type": "Ontology", "displayName": "ont_cos", "id": "existing-core"})
                fab = SimpleNamespace(
                    dry_run=False,
                    get_all=Mock(side_effect=[[{"displayName": "cos-p001", "id": "test-workspace"}], items]),
                    call=Mock(return_value=(201, {}, b"")),
                    change=Mock(return_value=(200, {"id": "test-item"})),
                    run_notebook=Mock(),
                )
                args = SimpleNamespace(prefix="cos-", capacity="test-capacity", reference_ontology=reference,
                                       extended_ontology=extended, update_notebooks=False, skip_prepare=False)
                output = io.StringIO()
                with redirect_stdout(output):
                    provision["provision"](fab, "p001", args, {})
                uploads = [c.args[1] for c in fab.call.call_args_list if "?resource=file" in c.args[1]]
                self.assertEqual(len(uploads), 28 if extended else 11)
                self.assertTrue(all("/Files/workshop/data/" in url for url in uploads))
                fab.run_notebook.assert_called_once_with("test-workspace", "test-item", "run 01_prepare_data")
                ontology_payloads = [c.args[3] for c in fab.change.call_args_list
                                     if c.args[3].get("type") == "Ontology"]
                expected = (["ont_cos"] if reference and not existing else []) + (["ont_cos_extended"] if extended else [])
                self.assertEqual([p["displayName"] for p in ontology_payloads], expected)
                if reference and not existing:
                    self.assertEqual(ontology_payloads[0]["definition"]["parts"],
                                     provision["definition_parts"](ROOT / "fabric" / "ont_cos_reference",
                                         {"{{WORKSPACE_ID}}": "test-workspace", "{{LAKEHOUSE_ID}}": "test-lakehouse"}))
                if existing:
                    self.assertIn("retained", output.getvalue())
                    if not reference:
                        self.assertIn("Chapter 01 starts empty", output.getvalue())
                self.assertEqual(len([c for c in fab.change.call_args_list if c.args[0].startswith("import notebook")]), 5)

    def test_dry_run_describes_participant_creation_or_explicit_recovery(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        for reference in (False, True):
            for extended in (False, True):
                with self.subTest(reference=reference, extended=extended):
                    fab = SimpleNamespace(
                        dry_run=True, get_all=Mock(return_value=[]),
                        change=Mock(return_value=(200, {"id": "00000000-0000-0000-0000-000000000000"})),
                        call=Mock(), run_notebook=Mock(),
                    )
                    args = SimpleNamespace(prefix="cos-", capacity="test-capacity", reference_ontology=reference,
                                           extended_ontology=extended)
                    output = io.StringIO()
                    with redirect_stdout(output):
                        provision["provision"](fab, "p001", args, {})
                    text = output.getvalue()
                    self.assertNotIn("ont_cos_base", text)
                    self.assertEqual("deploy ont_cos_reference" in text, reference)
                    self.assertEqual("leave ont_cos creation to participants" in text, not reference)
                    self.assertEqual("deploy ont_cos_extended" in text, extended)
                    fab.change.assert_called_once()
                    self.assertEqual(fab.change.call_args.args[0], "create workspace")
                    fab.call.assert_not_called()
                    fab.run_notebook.assert_not_called()

    def test_provision_rejects_existing_notebook_without_explicit_update(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        fab = SimpleNamespace(
            dry_run=False,
            get_all=Mock(side_effect=[[{"displayName": "cos-p001", "id": "test-workspace"}],
                                     [{"type": "Notebook", "displayName": "01_prepare_data", "id": "old-notebook"}]]),
            call=Mock(), change=Mock(), run_notebook=Mock(),
        )
        args = SimpleNamespace(prefix="cos-", extended_ontology=True, update_notebooks=False)
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "--update-notebooks"):
            provision["provision"](fab, "p001", args, {})
        fab.call.assert_not_called()
        fab.change.assert_not_called()
        fab.run_notebook.assert_not_called()

    def test_registration_and_batch_source_consistency(self):
        materials = {r["material_code"]: r for r in rows("raw_material")}
        for reg in rows("material_registration"):
            if reg["market_code"] == "CN":
                self.assertEqual(reg["status"], materials[reg["material_code"]]["cn_registration"])
        products = {r["product_id"]: r for r in rows("product")}
        plans = {r["plan_id"]: r for r in rows("production_plan")}
        for batch in rows("manufacturing_batch"):
            self.assertEqual(batch["version_id"], products[plans[batch["plan_id"]]["product_id"]]["version_id"])
        specs = {r["spec_id"]: r for r in rows("material_spec")}
        lots = {r["lot_id"]: r for r in rows("material_lot")}
        for lot in lots.values():
            self.assertEqual(lot["material_code"], specs[lot["spec_id"]]["material_code"])
            self.assertEqual(lot["supplier_id"], materials[lot["material_code"]]["supplier_id"])
        for inspection in rows("quality_inspection"):
            self.assertEqual(inspection["spec_id"], lots[inspection["lot_id"]]["spec_id"])
        orders = {r["po_id"]: r for r in rows("purchase_order")}
        for receipt in rows("goods_receipt"):
            self.assertEqual(lots[receipt["lot_id"]]["material_code"], orders[receipt["po_id"]]["material_code"])

    def test_reference_queries_exact_results_and_all_extension_tables_used(self):
        sql = (ROOT / "fabric" / "sql" / "extended-queries.sql").read_text(encoding="utf-8")
        used = set(re.findall(r"\bgold\.(\w+)", sql))
        self.assertTrue(set(Data().tables("EXTENDED_TABLES")) <= used)
        statements = [s.strip() for s in re.sub(r"--[^\n]*", "", sql).split(";") if s.strip()]
        self.assertEqual(len(statements), 4)
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.execute("ATTACH DATABASE ':memory:' AS gold")
            for table, schema in self.schemas.items():
                columns = ", ".join(f'"{c}" {("REAL" if t == "double" else "TEXT")}' for c, t in schema.items())
                db.execute(f'CREATE TABLE gold."{table}" ({columns})')
                db.executemany(f'INSERT INTO gold."{table}" VALUES ({", ".join("?" for _ in schema)})',
                               [tuple(r.values()) for r in rows(table)])
            result = [[dict(r) for r in db.execute(s)] for s in statements]
        self.assertEqual([len(r) for r in result], [2, 1, 3, 3])
        self.assertEqual([(r["lot_id"], r["qty_kg"], r["availability"], r["result"]) for r in result[0]],
                         [("LOT-120-A", 8.0, "가용", "적합"), ("LOT-120-B", 5.0, "격리", "부적합")])
        self.assertEqual(result[1], [{"product_id": "P-102", "market_code": "CN", "product_registration": "완료",
                                     "alternative_material": "RM-HA-210", "supplier_qualification": "승인",
                                     "material_registration": "필요"}])
        self.assertEqual([(r["plan_id"], r["site_name"]) for r in result[2]],
                         [("PP-1101", "인천 제조소"), ("PP-1102", "오산 제조소"), ("PP-1103", "인천 제조소")])
        self.assertEqual([(r["assessment_id"], r["team_name"], r["status"]) for r in result[3]],
                         [("CA-01", "구매·생산계획", "대기"), ("CA-02", "처방개발", "진행중"), ("CA-03", "등록검토", "등록확인")])


if __name__ == "__main__":
    unittest.main()
