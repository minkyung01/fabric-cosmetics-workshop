"""Offline consistency checks for the workshop kit. Run: python -m unittest discover -s tests -v"""
import ast
import base64
import csv
import io
import json
import re
import runpy
import sqlite3
import string
import subprocess
import sys
import unittest
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from itertools import product
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = sorted((ROOT / "docs").glob("*.md"))
ALL_DOCS = sorted((ROOT / "docs").rglob("*.md"))
PASTE_DOCS = sorted((ROOT / "notebooks" / "paste").glob("*.md"))
NOTEBOOKS = ["01_prepare_data", "02_answers", "03_supply_change", "nb_apply_review", "04_publish_serving"]
WORKSHOP_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/minkyung01/fabric-cosmetics-workshop/"
    "main/downloads/workshop-files.zip"
)
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

    def test_participant_download_contains_exact_sources_notebooks_and_paste_guides(self):
        expected = {f"data/{name}.csv" for name in Data().tables()}
        expected |= {f"data/extended/{name}.csv" for name in Data().tables("EXTENDED_TABLES")}
        expected |= {f"notebooks/{name}.ipynb" for name in NOTEBOOKS}
        expected |= {f"notebooks/paste/{name}.md" for name in NOTEBOOKS}
        self.assertEqual(len(expected), 38)
        with zipfile.ZipFile(ROOT / "downloads" / "workshop-files.zip") as archive:
            self.assertEqual(archive.namelist(), sorted(expected))
            self.assertIsNone(archive.testzip())
            for info in archive.infolist():
                with self.subTest(file=info.filename):
                    self.assertFalse(info.is_dir())
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(archive.read(info.filename), (ROOT / info.filename).read_bytes())

    def test_participant_download_generation_is_deterministic(self):
        builder = runpy.run_path(str(ROOT / "tools" / "build_notebooks.py"))
        notebooks = {f"{name}.ipynb": builder["build"](ROOT / "notebooks" / "src" / f"{name}.py")
                     for name in NOTEBOOKS}
        download = builder["build_download"](notebooks)
        self.assertEqual(download, builder["build_download"](dict(reversed(list(notebooks.items())))))
        self.assertEqual(download, (ROOT / "downloads" / "workshop-files.zip").read_bytes())

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

    def test_paste_guides_contain_the_same_code_with_separate_parameters(self):
        self.assertEqual(sorted(p.stem for p in PASTE_DOCS), sorted(NOTEBOOKS))
        for name in NOTEBOOKS:
            with self.subTest(notebook=name):
                text = (ROOT / "notebooks" / "paste" / f"{name}.md").read_text(encoding="utf-8")
                blocks = re.findall(r"```python\n(.*?)\n```", text, re.S)
                cells = notebook(name)["cells"]
                params = next(c for c in cells if "parameters" in c["metadata"].get("tags", []))
                body = "\n\n".join("".join(c["source"]) for c in cells
                                   if c["cell_type"] == "code" and c is not params)
                self.assertEqual(blocks, ["".join(params["source"]), body])
                for block in blocks:
                    compile(block, name, "exec")
                ast.parse("\n".join(blocks))

    def test_answers_show_each_agent_question_beside_its_query_in_guide_order(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        questions = dict(re.findall(r"^\| (DA\d{2}) \| [^|]+ \| `([^`]+)` \| [^|\n]+ \|$", lesson, re.M))
        verification = lesson.split("## 4. 답과 근거 검증하기", 1)[1].split("<details>", 1)[0]
        output_titles = {
            title.split()[0]: title.strip()
            for title in re.findall(r"^\| (DA\d{2} [^|]+) \| \d+행", verification, re.M)
        }
        self.assertEqual(list(output_titles), list(questions))
        cells = notebook("02_answers")["cells"]
        headings = []
        for index, cell in enumerate(cells):
            if cell["cell_type"] != "markdown":
                continue
            markdown = "".join(cell["source"])
            heading = re.match(r"### (DA\d{2})\.", markdown)
            if not heading:
                continue
            question_id = heading.group(1)
            headings.append(question_id)
            self.assertIn(f"> {questions[question_id]}", markdown)
            self.assertEqual(cells[index + 1]["cell_type"], "code")
            calls = [node for node in ast.walk(ast.parse("".join(cells[index + 1]["source"])))
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "q"]
            self.assertEqual(len(calls), 1)
            self.assertTrue(ast.literal_eval(calls[0].args[0]).startswith(question_id + " "))
            self.assertEqual(ast.literal_eval(calls[0].args[0]), output_titles[question_id])
            prompt = next(keyword.value for keyword in calls[0].keywords if keyword.arg == "question")
            self.assertEqual(ast.literal_eval(prompt), questions[question_id])
        self.assertEqual(headings, [f"DA{i:02}" for i in range(1, 8)])
        self.assertEqual(re.findall(r"^## (Q\d)\.", "\n".join("".join(c["source"]) for c in cells), re.M),
                         [f"Q{i}" for i in range(1, 7)])

    def test_answer_display_prints_the_question_before_the_result(self):
        tree = ast.parse(code("02_answers"))
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "q")
        namespace = {"spark": Mock(), "display": Mock()}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "q", "exec"), namespace)
        output = io.StringIO()
        with redirect_stdout(output):
            namespace["q"]("DA01", "SELECT 1", question="확인할 질문")
        self.assertIn("DA01", output.getvalue())
        self.assertIn("Agent에 보낼 질문:\n확인할 질문", output.getvalue())
        namespace["spark"].sql.assert_called_once_with("SELECT 1")
        namespace["display"].assert_called_once_with(namespace["spark"].sql.return_value)

    def test_embedded_scenario_exactly_matches_all_canonical_data(self):
        tree = ast.parse(code("01_prepare_data"))
        data = next(ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id == "SCENARIO_DATA")
        self.assertEqual(set(data), set(Data().tables()) | set(Data().tables("EXTENDED_TABLES")))
        for table, text in data.items():
            self.assertEqual(list(csv.DictReader(io.StringIO(text))), rows(table), table)
        for name in NOTEBOOKS:
            self.assertNotIn("Files/workshop", code(name), name)
            self.assertNotIn("spark.read", code(name), name)
        self.assertNotRegex(code("01_prepare_data"), r"requests|urllib|notebookutils|open\(")

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


class DataPreparation(unittest.TestCase):
    def check(self, existing):
        source = (ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check_existing_data")
        exists = Mock(side_effect=lambda name: name in existing)
        namespace = {"TABLES": Data().tables(), "EXTENDED_TABLES": Data().tables("EXTENDED_TABLES"),
                     "OPS_TABLES": ["material_impact", "review_request", "action_log"],
                     "spark": SimpleNamespace(catalog=SimpleNamespace(tableExists=exists))}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), source, "exec"), namespace)
        return namespace["check_existing_data"], exists

    def test_initial_load_accepts_only_an_empty_workshop_state_by_default(self):
        check, exists = self.check(set())
        check(False)
        self.assertEqual(exists.call_count, 31)
        for name in ("gold.purchase_order", "gold.inventory_balance", "ops.material_impact",
                     "ops.review_request", "ops.action_log"):
            with self.subTest(existing=name):
                check, _ = self.check({name})
                with self.assertRaisesRegex(ValueError, re.escape(name)):
                    check(False)

    def test_reset_requires_an_explicit_boolean_true(self):
        check, exists = self.check({"gold.purchase_order", "ops.review_request"})
        for invalid in ("false", "true", 0, 1, None):
            with self.subTest(reset=invalid), self.assertRaises(ValueError):
                check(invalid)
        exists.assert_not_called()
        check(True)
        exists.assert_not_called()

    def test_existing_data_stops_the_real_notebook_before_any_writes(self):
        source = code("01_prepare_data")
        nodes = [n for n in ast.parse(source).body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        spark = Mock()
        spark.catalog.tableExists.side_effect = lambda name: name == "ops.review_request"
        namespace = {"spark": spark, "F": Mock(), "display": Mock(), "csv": csv, "io": io}
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "ops.review_request"):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
        self.assertIs(namespace["reset_ops"], False)
        spark.sql.assert_not_called()
        spark.createDataFrame.assert_not_called()

    def test_notebook_creates_tables_and_drops_ops_only_for_explicit_reset(self):
        source = code("01_prepare_data")
        nodes = [n for n in ast.parse(source).body if not isinstance(n, (ast.Import, ast.ImportFrom))
                 and not (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                          t.id in ("reset_ops", "include_extended") for t in n.targets))]
        for reset, extended in product((False, True), repeat=2):
            with self.subTest(reset=reset, extended=extended):
                tables = {**Data().tables(), **(Data().tables("EXTENDED_TABLES") if extended else {})}
                spark, raw, frame = Mock(), Mock(), Mock()
                spark.catalog.tableExists.return_value = False
                spark.createDataFrame.return_value = raw
                raw.select.return_value = frame
                frame.withColumn.return_value = frame
                frame.count.return_value = 1
                frame.write.mode.return_value = frame.write
                frame.write.option.return_value = frame.write
                frame.write.format.return_value = frame.write
                namespace = {"spark": spark, "F": Mock(), "display": Mock(), "reset_ops": reset,
                             "include_extended": extended, "csv": csv, "io": io}
                with redirect_stdout(io.StringIO()):
                    exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
                self.assertEqual([call.args[0] for call in frame.write.saveAsTable.call_args_list],
                                 [f"gold.{table}" for table in tables])
                self.assertTrue(all(call.args == ("overwrite",) for call in frame.write.mode.call_args_list))
                self.assertEqual(spark.createDataFrame.call_count, len(tables))
                frame.withColumn.assert_called_once_with("original_eta", namespace["F"].col("eta"))
                for (table, columns), call in zip(tables.items(), spark.createDataFrame.call_args_list):
                    self.assertEqual(call.args[0], [{k: v or None for k, v in row.items()} for row in rows(table)], table)
                    self.assertEqual(call.kwargs["schema"], ", ".join(f"{c} string" for c in columns), table)
                drops = [call.args[0] for call in spark.sql.call_args_list if call.args[0].startswith("DROP")]
                self.assertEqual(drops, [f"DROP TABLE IF EXISTS ops.{t}" for t in
                                         ("material_impact", "review_request", "action_log")] if reset else [])

    def test_supply_change_reuses_preserved_eta_and_rejects_missing_baseline(self):
        cells = notebook("03_supply_change")["cells"]
        source = "".join(next(c["source"] for c in cells if c["cell_type"] == "code"
                              and "purchase_orders = spark.table" in "".join(c["source"])))
        nodes = [n for n in ast.parse(source).body if not isinstance(n, ast.ImportFrom)]
        for current_eta in (date(2026, 11, 10), date(2026, 12, 15)):
            with self.subTest(current_eta=current_eta):
                spark, functions = MagicMock(), MagicMock()
                orders = spark.table.return_value
                orders.columns = ["po_id", "material_code", "eta", "original_eta"]
                row = {"po_id": "PO-5501", "eta": current_eta, "original_eta": date(2026, 11, 10)}
                def select(*columns):
                    result = Mock()
                    result.collect.return_value = [SimpleNamespace(**{c: row[c] for c in columns})]
                    return result
                orders.where.return_value.select.side_effect = select
                namespace = {"spark": spark, "F": functions, "date": date, "timedelta": timedelta,
                             "material_code": "RM-HA-120", "delay_days": 35, "as_of_date": "2026-11-02"}
                output = io.StringIO()
                with redirect_stdout(output):
                    exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
                orders.where.return_value.select.assert_called_once_with("po_id", "original_eta")
                self.assertEqual(namespace["orig_eta"], {"PO-5501": date(2026, 11, 10)})
                self.assertIn("2026-11-10 → 2026-12-15", output.getvalue())
                self.assertEqual(functions.date_add.call_args.args[1], 35)
                spark.read.assert_not_called()
        spark = MagicMock()
        spark.table.return_value.columns = ["po_id", "eta"]
        with self.assertRaisesRegex(ValueError, "original_eta"):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"),
                 {"spark": spark, "F": MagicMock(), "date": date, "as_of_date": "2026-11-02"})
        spark.sql.assert_not_called()
        spark.table.return_value.write.mode.assert_not_called()
        for baseline in (None, "2026-11-10"):
            with self.subTest(invalid_baseline=baseline):
                spark = MagicMock()
                spark.table.return_value.columns = ["po_id", "eta", "original_eta"]
                spark.table.return_value.where.return_value.select.return_value.collect.return_value = [
                    SimpleNamespace(po_id="PO-5501", original_eta=baseline)]
                with self.assertRaisesRegex(ValueError, "original_eta"):
                    exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"),
                         {"spark": spark, "F": MagicMock(), "date": date,
                          "as_of_date": "2026-11-02", "material_code": "RM-HA-120"})
                spark.sql.assert_not_called()
                spark.table.return_value.write.mode.assert_not_called()


class Docs(unittest.TestCase):
    def test_chapters_linked_from_readme(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for doc in DOCS:
            self.assertIn(f"docs/{doc.name}", readme)

    def test_relative_links_resolve(self):
        for md in [ROOT / "README.md", *ALL_DOCS, *PASTE_DOCS, *sorted((ROOT / "admin").glob("*.md")),
                   ROOT / "assets" / "icon-attribution.md"]:
            text = md.read_text(encoding="utf-8")
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if link.startswith(("http", "#", "mailto:")):
                    continue
                path = (md.parent / unquote(urlsplit(link).path)).resolve()
                self.assertTrue(path.exists(), f"{md.name}: {link}")

    def test_download_links_use_the_public_absolute_zip_url(self):
        for md in (ROOT / "README.md", ROOT / "admin" / "README.md"):
            links = re.findall(r"\]\(([^)]+)\)", md.read_text(encoding="utf-8"))
            with self.subTest(document=md.relative_to(ROOT)):
                self.assertEqual([link for link in links if "workshop-files.zip" in link], [WORKSHOP_DOWNLOAD_URL])

    def test_bold_delimiters_do_not_end_in_punctuation_before_attached_words(self):
        for md in [ROOT / "README.md", *ALL_DOCS, *PASTE_DOCS, *sorted((ROOT / "admin").glob("*.md")),
                   ROOT / "assets" / "icon-attribution.md"]:
            fence = None
            for number, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith(("```", "~~~")):
                    marker = stripped[:3]
                    if fence is None:
                        fence = marker
                    elif fence == marker:
                        fence = None
                    continue
                if fence:
                    continue
                for span in re.finditer(r"(?<!\\)\*\*([^*\n]+)\*\*([^\W_])", line):
                    last = span[1][-1]
                    with self.subTest(document=md.relative_to(ROOT), line=number, span=span[0]):
                        self.assertFalse(last in string.punctuation or unicodedata.category(last).startswith("P"),
                                         "Punctuation before ** followed by an attached word prevents bold from closing")

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
        self.assertIn("4-1에서 부족한 부분 발견 → 4-2에서 보강안 제안·검토 → Act로 적용", lesson)
        self.assertIn("앞선 Act 적용이 실패했다는 뜻은 아닙니다", lesson)
        self.assertIn("제안만으로 바인딩이 추가되지는 않으며", lesson)
        self.assertIn("기존 항목·ID·키·바인딩은 보존", lesson)
        self.assertNotIn("관리자가 배포한 기본 Ontology", lesson)
        prompts = re.findall(r"```text\n(.*?)```", lesson, re.S)
        core = set(Data().tables())
        self.assertEqual(set(re.findall(r"\b\w+\b", prompts[0])) & core, {"formula_line"})
        review = lesson.split("## 2. 첫 업무 질문", 1)[1].split("\n## 3.", 1)[0]
        initial = set(re.findall(r"\b\w+\b", review)) & core
        self.assertEqual(initial, {"ingredient", "raw_material", "supplier", "purchase_order",
                                   "formula_version", "formula_line", "product"})
        improvement = next(p for p in prompts if "보강하는 변경안" in p)
        added = (set(re.findall(r"\b\w+\b", improvement)) & core) - initial
        self.assertEqual(added, {"production_plan", "dev_project", "stability_test", "material_alternative"})
        self.assertEqual(initial | added, core)
        self.assertIn("Boolean", improvement)
        self.assertIn("cn_registration", improvement)
        self.assertIn("변경 미리 보기", improvement)
        improvement_approval = next(p for p in prompts if "검토한 보강 변경안만 현재 ont_cos에 적용해줘." in p)
        self.assertIn("원본 데이터와 다른 Fabric 항목은 바꾸지 마.", improvement_approval)
        for prompt in prompts:
            if "검토한 초안만 현재 ont_cos에 적용해줘." in prompt:
                self.assertIn("원본은 읽기만 하고", prompt)
            else:
                self.assertNotRegex(prompt, r"Ontology나 작업 영역은 변경하지 마|아직 적용하지 마|먼저 Plan에서")
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertIn("| Ontology | `ont_cos` | **01장에서 직접 생성** |", scenario)

    def test_initial_ontology_proposal_requires_purchase_product_and_connected_paths_before_approval(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        initial = lesson.split("## 2. 첫 업무 질문", 1)[1].split("\n## 3.", 1)[0]
        self.assertIn("엔터티 **6개**", initial)
        self.assertIn("관계 **5개**", initial)
        for entity in ("Ingredient", "RawMaterial", "Supplier", "PurchaseOrder", "FormulaVersion", "Product"):
            self.assertIn(f"`{entity}`", initial)
        recovery = lesson.split("<summary>엔터티 또는 관계가 불충분하게 제안된 경우</summary>", 1)[1].split("</details>", 1)[0]
        self.assertIn("발주나 제품을 다른 대상의 속성으로만 합치거나 생략하지 마", recovery)
        self.assertIn("그대로 승인하지 말고 **Plan**에서 보완", recovery)
        self.assertIn("아직 저장된 모델이 아닙니다", recovery)
        self.assertIn("gold.purchase_order의 po_id", recovery)
        self.assertIn("gold.product의 product_id", recovery)
        for relationship in ("has_ingredient", "supplied_by", "orders", "uses_material", "made_with"):
            self.assertRegex(recovery, rf"(?m)^- {relationship}:")
        self.assertIn("타입이 모두 있어도 관계·바인딩이 빠졌다면 아직 완료가 아닙니다", recovery)
        self.assertIn("질문별로 이미 지원되는 부분과 누락된 부분", recovery)
        self.assertIn("누락된 항목만 추가", recovery)
        self.assertIn("기존 항목·ID·키·속성·바인딩은 보존", recovery)
        self.assertIn("추가·수정·유지한 항목", recovery)
        self.assertNotIn("엔터티 4개", recovery)
        self.assertNotIn("관계는 2개", recovery)
        self.assertNotIn("PurchaseOrder와 Product를 독립 엔터티로 추가", recovery)
        self.assertNotIn("<summary>엔터티 4개", lesson)
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", lesson)
        self.assertEqual(images, ["../assets/screenshots/01-create-ontology.png",
                                  "../assets/screenshots/01-agent-preview-button.png",
                                  "../assets/screenshots/01-ontology-applied.png",
                                  "../assets/screenshots/01-formula-line-proposal.png",
                                  "../assets/screenshots/01-formula-line-relationship.png",
                                  "../assets/screenshots/01-incomplete-proposal.png",
                                  "../assets/screenshots/01-answers-q1-formula-versions.png",
                                  "../assets/screenshots/01-answers-q6-before-supply-change.png"])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_initial_ontology_prompt_specifies_usage_mapping_without_prescribing_full_model(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        prompt = re.findall(r"```text\n(.*?)```", lesson, re.S)[0]
        for requirement in ("lh_cos Lakehouse의 gold", "INCI 성분", "RM-HA-120",
                            "처방 버전과 연결된 판매 제품", "생산·개발 일정의 영향 계산과 대체 원료 검토는 제외",
                            "키의 유일성·결측", "오류를 보고", "초안 미리 보기"):
            self.assertIn(requirement, prompt)
        self.assertNotRegex(prompt, r"Ingredient|PurchaseOrder|Product|Supplier|po_id|is_active|cn_registration")
        for requirement in ("배합 행·배합비 관리는 이번 범위에서 제외",
                            "FormulaLine을 거치지 않는 FormulaVersion → RawMaterial의 uses_material",
                            "gold.formula_line 테이블의 version_id와 material_code",
                            "각각 FormulaVersion.version_id와 RawMaterial.material_code에 연결",
                            "확인 가능한 원본 열과 샘플 행",
                            "관계 설계로 해석한 연결을 구분",
                            "샘플만으로 단정하지 마",
                            "도구가 없으면 해당 검증은 미실행",
                            "관련 없는 엔터티·관계·키·속성·바인딩은 보존",
                            "원본 데이터와 다른 Fabric 항목은 변경하지 마",
                            "오류를 보고하고 중단"):
            self.assertIn(requirement, prompt)
        self.assertIn("처음 제안된 설계와 근거를 기록한 뒤", lesson)
        self.assertIn("초안 검토용 정답지", lesson)
        self.assertIn("문제가 없다면 보완 요청 없이 적용 단계로 진행", lesson)
        repair = next(p for p in re.findall(r"```text\n(.*?)```", lesson, re.S)
                      if "현재 초안에서 첫 세 업무 질문에 필요한" in p)
        repair_sources = set(re.findall(r"\b\w+\b", repair)) & set(Data().tables())
        self.assertEqual(repair_sources, {"ingredient", "raw_material", "supplier", "purchase_order",
                                         "formula_version", "formula_line", "product"})
        self.assertIn("각각 독립된 업무 대상으로 모델링", repair)
        self.assertIn("formula_line은 관계 매핑으로만 사용", repair)
        self.assertIn("첫 요청에 함께 넣지 않습니다", lesson)
        self.assertLess(lesson.index("### 2-3. RM-HA-120의 원본 샘플과 연결 설계 확인"),
                        lesson.index("현재 초안에서 첫 세 업무 질문에 필요한"))
        admin = (ROOT / "admin" / "preview-limitations.md").read_text(encoding="utf-8")
        self.assertIn("전체 엔터티 목록은 미리 지정하지 않되", admin)
        self.assertIn("이 관계의 방향·키 매핑", admin)

    def test_formula_line_entity_is_a_valid_alternative_with_scoped_simplification(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        example = lesson.split("<summary>FormulaLine이 별도 엔터티로 제안된 경우</summary>", 1)[1].split("</details>", 1)[0]
        self.assertIn("독립 엔터티로 표현하는 것도 타당", example)
        self.assertIn("누락 오류를 고치는 것이 아니라", example)
        self.assertIn("같은 대화의 **Plan**", example)
        self.assertIn("FormulaLine → FormulaVersion", example)
        self.assertIn("FormulaLine → RawMaterial", example)
        self.assertIn("방향을 맞추기 위해 뒤집을 필요는 없습니다", example)
        self.assertIn("FormulaLine.version_id = FormulaVersion.version_id", example)
        self.assertIn("**Property 1**이 `Select a property`", example)
        self.assertIn("꺼진 것 자체는 이 직접 속성 매칭 모델의 오류 근거가 아닙니다", example)
        self.assertIn("FormulaVersion → RawMaterial의 uses_material", example)
        self.assertIn("gold.formula_line", example)
        self.assertIn("version_id를 FormulaVersion.version_id", example)
        self.assertIn("material_code를 RawMaterial.material_code", example)
        self.assertIn("검증이 끝나기 전에는 FormulaLine과 기존 연결을 제거하지 마", example)
        self.assertIn("나머지 엔터티·키·속성·바인딩·관계는 보존", example)
        self.assertIn("원본 데이터는 변경하지 마", example)
        self.assertIn("확인 가능한 샘플을 근거", example)
        self.assertIn("결과 건수의 보존은 미실행", example)
        self.assertNotIn("처방 버전 4개", example)
        self.assertIn("오류를 보고하고 중단", example)
        self.assertIn("Preview ontology", example)
        records = rows("formula_line")
        self.assertTrue(all(record["line_id"] and record["pct_wt"] for record in records))
        self.assertEqual(len({record["line_id"] for record in records}), len(records))

    def test_initial_ontology_answer_key_matches_sources_keys_and_material_usage(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        initial = lesson.split("## 2. 첫 업무 질문", 1)[1].split("\n## 3.", 1)[0]
        self.assertNotIn("업무 범위 질문을 받은 경우에만", initial)
        self.assertNotIn("질문 없이 초안이 나오면 바로 검토", initial)
        self.assertIn("**제안하는 Ontology 초안**, **제안하는 관계**, **검증 결과**를 펼쳐", initial)
        self.assertNotRegex(initial, r"(?m)^\d+\. 업무 범위")
        bindings = re.findall(r"^\| `(\w+)` \| `gold\.(\w+)` \| `(\w+)` \|", initial, re.M)
        self.assertEqual(len(bindings), 6)
        for entity, table, key in bindings:
            with self.subTest(entity=entity):
                values = [record[key] for record in rows(table)]
                self.assertTrue(all(values))
                self.assertEqual(len(values), len(set(values)))
        for table, column, target, target_key in (
            ("raw_material", "ingredient_id", "ingredient", "ingredient_id"),
            ("raw_material", "supplier_id", "supplier", "supplier_id"),
            ("purchase_order", "material_code", "raw_material", "material_code"),
            ("formula_line", "version_id", "formula_version", "version_id"),
            ("formula_line", "material_code", "raw_material", "material_code"),
            ("product", "version_id", "formula_version", "version_id"),
        ):
            self.assertIn(f"{table}.{column} = {target}.{target_key}", initial)
            targets = {record[target_key] for record in rows(target)}
            self.assertTrue(all(record[column] in targets for record in rows(table)))
        material = next(record for record in rows("raw_material") if record["material_code"] == "RM-HA-120")
        supplier = next(record for record in rows("supplier") if record["supplier_id"] == material["supplier_id"])
        ingredient = next(record for record in rows("ingredient") if record["ingredient_id"] == material["ingredient_id"])
        for value in (material["material_name"], supplier["supplier_id"], supplier["supplier_name"],
                      ingredient["ingredient_id"], ingredient["inci_name"]):
            self.assertIn(value, initial)
        order = next(record for record in rows("purchase_order") if record["material_code"] == "RM-HA-120")
        self.assertIn(f'`{order["po_id"]}` — `eta = {order["eta"]}`, `status = {order["status"]}`', initial)
        versions = {record["version_id"] for record in rows("formula_line") if record["material_code"] == "RM-HA-120"}
        self.assertEqual(len(versions), 4)
        for record in rows("formula_version"):
            if record["version_id"] not in versions:
                continue
            products = [product["product_id"] for product in rows("product")
                        if product["version_id"] == record["version_id"] and product["sales_status"] == "판매중"]
            if products:
                expected = " · ".join(f"`{product}`" for product in products)
                self.assertIn(f'| `{record["version_id"]}` | {record["status"]} | {expected} |', initial)
        self.assertNotRegex(initial, r"\| `FV-(?:CRM-01-02|TON-02-01)` \| .* \| 없음 \|")

    def test_initial_data_review_accepts_sample_limits_without_claiming_absence(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        review = lesson.split("### 2-3. RM-HA-120의 원본 샘플과 연결 설계 확인", 1)[1].split("\n## 3.", 1)[0]
        self.assertIn("**Act로 전환하지 않습니다**", review)
        self.assertIn("**같은 대화의 Plan**", review)
        prompt = re.findall(r"```text\n(.*?)```", review, re.S)[0]
        for requirement in ("lh_cos.gold에서 확인 가능한 원본 샘플", "RM-HA-120",
                            "어떤 원료인지", "어떤 INCI 성분에 해당하는지",
                            "어느 공급사가 공급하는지",
                            "해당 원료의 발주와 입고 예정일, 발주 상태",
                            "이 원료를 사용하는 처방 버전과 각 처방의 상태",
                            "해당 처방과 연결된 판매 제품",
                            "샘플에 보이는 폐기·개발중 처방도 제외하지 마",
                            "'샘플에서 미확인'", "'없음'으로 바꾸거나",
                            "관계 설계만으로 값을 추측하지 마",
                            "전체 건수나 제품의 부재는 단정하지 마",
                            "근거 원본과 샘플 확인 범위·한계는 짧게",
                            "한눈에 파악할 수 있게 짧게", "긴 해설은 출력하지 마",
                            "오류를 보고하고 중단",
                            "원본 데이터와 현재 Ontology는 변경하지 마"):
            self.assertIn(requirement, prompt)
        self.assertNotIn("각 연결을 지원하는 초안의 관계·양끝 키·매핑 원본도 별도로 설명", prompt)
        self.assertNotRegex(prompt, r"material_code|ingredient_id|supplier_id|po_id|eta|status|version_id|product_id")
        self.assertNotRegex(prompt, r"표 1|표 2|열:|행:|\|")
        self.assertIn("사용할 원본 열과 정리 형식은 Agent가 판단", review)
        self.assertIn("관계·키·바인딩 상세는 3단계", review)
        self.assertIn("**Preview ontology**", review)
        self.assertIn("2-1·2-2 표와 대조", review)
        self.assertIn("별도 SQL 실습으로 이동하지 않습니다", review)
        self.assertIn("전체 건수나 제품이 없는 처방의 판정은 완료 조건이 아닙니다", review)
        self.assertNotIn("처방 버전은 **4개**", review)
        self.assertNotIn("| 없음 |", review)
        self.assertIn("전체 경로를 조인 질의로 검증했다는 뜻은 아닙니다", review)
        self.assertIn("3단계의 Act 적용 후 확인", review)
        self.assertIn("`02_answers` Q1", review)
        self.assertIn("‘샘플에서 미확인’은 ‘데이터에 없음’이 아닙니다", review)
        self.assertIn("전체 사용처·제품 목록이나 누락 여부까지 확인했다고 볼 수 없습니다", review)
        self.assertIn("샘플 크기·선정 방식", review)

    def test_initial_act_reuses_previous_review_and_checks_saved_model(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        review = lesson.split("## 3. Act 적용 → 저장된 모델 확인", 1)[1].split("\n## 4.", 1)[0]
        main_flow = review.split("**보완 예시 — 필요한 경우에만 펼치기**", 1)[0]
        self.assertIn("2-1·2-2에서", main_flow)
        self.assertIn("**검토표를 다시 요청할 필요는 없습니다**", main_flow)
        self.assertIn("누락·불일치가 있을 때만 **Plan**", main_flow)
        self.assertIn("바인딩이 미확인이거나 읽기 오류가 남아 있다면 승인하지 않습니다", main_flow)
        self.assertIn("**이 장에서 처음 Act로 전환하는 시점입니다.**", main_flow)
        self.assertNotIn("현재 적용하려는 Ontology 초안 자체를 검토", review)
        self.assertNotIn("항목별로 기대 설계와의 일치·불일치·미확인", review)
        self.assertEqual(len(re.findall(r"```text\n(.*?)```", main_flow, re.S)), 1)
        prompt = re.findall(r"```text\n(.*?)```", review, re.S)[0]
        self.assertNotRegex(prompt, r"\d+단계")
        for requirement in ("이 대화에서 제안한 초안의 설계와 원본 근거",
                            "검토한 초안만 현재 ont_cos에 적용",
                            "lh_cos.gold 원본은 읽기만",
                            "원본 테이블·데이터나 다른 Fabric 항목은 변경하지 마"):
            self.assertIn(requirement, prompt)
        for requirement in ("**Entity Types**", "View Entity Type details → Configure", "**Data source**",
                            "**Manage relationships**", "**Instances**",
                            "`FormulaVersion → RawMaterial`", "`gold.formula_line`",
                            "`version_id`·`material_code`",
                            "AI Proposal이나 완료 메시지만으로 저장을 판단하지 않습니다",
                            "**Plan으로 복귀**",
                            "해당 제한을 기록하고 진행할 수 있으며"):
            self.assertIn(requirement, main_flow)
        self.assertLess(main_flow.index("**Switch to 'Act' + approve**"),
                        main_flow.index("**Entity Types**"))
        self.assertLess(main_flow.index("**Instances**"), main_flow.index("**Plan으로 복귀**"))
        first_prompt = re.findall(r"```text\n(.*?)```", lesson, re.S)[0]
        self.assertNotIn("처방 버전 4개", first_prompt)
        self.assertNotIn("판매 제품 3개", first_prompt)
        for prompt in re.findall(r"```text\n(.*?)```", lesson, re.S):
            self.assertNotIn("쓰는 모든 처방 버전", prompt)
        notebook_section = lesson.split("## 6.", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        self.assertIn("명시적인 Notebook 질의", notebook_section)
        self.assertIn("Q1 표의 **4행**", notebook_section)

    def test_ontology_answers_walkthrough_connects_lakehouse_and_explains_outputs(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        section = lesson.split("## 6.", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        for requirement in ("### 6-2.", "### 6-3.", "### 6-4.", "### 6-5.",
                            "**Data items → Add data items → From OneLake catalog**",
                            "**내 작업 영역의 `lh_cos`**", "**SQL analytics endpoint**",
                            "**기본 Lakehouse로 고정**", "Notebook을 저장",
                            "**`02_answers`에도 별도로 연결해야 합니다.**",
                            "세션을 다시 시작", "**Tables → gold**",
                            'material_code = "RM-HA-120"', "qc_lead_days = 7",
                            "**30초–5분**", "**Run all**을 한 번",
                            "**5 columns, 4 rows**", "**상태 무관**",
                            "Ontology의 모든 관계·바인딩까지 검증했다는 뜻은 아닙니다",
                            "`01_prepare_data`를 다시 실행해 데이터를 초기화하지 않습니다",
                            "지금은 지연 반영 전",
                            "**`03_supply_change`를 먼저 실행하지 않습니다.**",
                            "영향 분석 결과 테이블이 아직 없다는 안내", "**Plan 상태를 유지**"):
            self.assertIn(requirement, section)
        for version, status, active in (
                ("FV-AMP-03-02", "현행", "true"),
                ("FV-CRM-01-02", "폐기", "false"),
                ("FV-CRM-01-03", "현행", "true"),
                ("FV-TON-02-01", "개발중", "true")):
            self.assertIn(f"| `{version}` | {status} | {active} |", section)
        answers = (ROOT / "notebooks" / "paste" / "02_answers.md").read_text(encoding="utf-8")
        notice = "ops.material_impact가 아직 없습니다. 4장에서 03_supply_change를 실행한 뒤 다시 확인하세요."
        self.assertIn(notice, section)
        self.assertIn(notice, answers)
        self.assertLess(section.index("### 6-2."), section.index("### 6-3."))
        self.assertLess(section.index("### 6-3."), section.index("01-answers-q1-formula-versions.png"))
        self.assertLess(section.index("### 6-5."), section.index("01-answers-q6-before-supply-change.png"))

    def test_ontology_agent_answers_have_explicit_comparison_targets(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        section = lesson.split("## 6.", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        agent = section.split("### 6-2.", 1)[0]
        for requirement in ("모델 설명은 저장된 정의와",
                            "5번의 참고 표와 Explorer에 저장된 정의",
                            "5번의 관계 표와 실제 저장된 관계·업무 설명",
                            "Q1만으로 검증할 수 없습니다",
                            "6-4의 `02_answers` Q1 결과",
                            "Agent가 샘플만 확인했다면 답변에 모든 처방이 나올 필요는 없습니다"):
            self.assertIn(requirement, agent)
        comparison = section.split("### 6-4.", 1)[1].split("### 6-5.", 1)[0]
        for requirement in ("6-1의 답변을 옆에 두고",
                            "같은 `version_id`의 `status`·`is_active`",
                            "샘플의 누락만으로 원본 데이터나 바인딩 오류라고 판단하지 않습니다",
                            "같은 처방의 상태 값이 다르다면 Agent가 사용한 원본·근거를 다시 확인"):
            self.assertIn(requirement, comparison)
        notice = section.split("### 6-5.", 1)[1]
        self.assertNotIn("영향 3건", notice)
        self.assertNotIn("이미 04장을 진행한 환경", notice)

    def test_graph_projection_distinguishes_schema_and_instance_queries(self):
        lesson = (ROOT / "docs" / "02-graph.md").read_text(encoding="utf-8")
        for requirement in ("엔터티 9개·관계 10개", "**9 entities**",
                            "총개수만 맞추려고 삭제하지 말고",
                            "**Projection summary**", "**Graph model**이지 KQL Database가 아닙니다",
                            "**Eligible은 투영 가능하다는 뜻**",
                            "**투영할 타입과 관계 구조**",
                            "**Explore graph 버튼을 전제로 하지 않습니다.**",
                            "Q1의 GQL을 실행해 결과로 확인",
                            "질의를 실제 스키마에 맞춥니다",
                            "Ontology 화면의 표시 이름만 보고 추정하지 않습니다",
                            "`[:made_with]`", "`product_usesFormulaVersion`",
                            "모델을 다시 만들 필요는 없습니다"):
            self.assertIn(requirement, lesson)
        self.assertNotIn("MaterialAlternative", lesson)
        self.assertNotIn("**Home**에서 **Explore graph**를 누릅니다", lesson)
        self.assertIn("(rm:RawMaterial)-[:alternative_to]->(alt:RawMaterial)-[:supplied_by]->(s:Supplier)", lesson)
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", lesson)
        self.assertEqual(images, ["../assets/screenshots/02-graph-choose-projection.png",
                                  "../assets/screenshots/02-graph-projection-summary.png",
                                  "../assets/screenshots/02-graph-created-items.png",
                                  "../assets/screenshots/02-graph-query-now.png",
                                  "../assets/screenshots/02-graph-q1-results-compact.png",
                                  "../assets/screenshots/02-graph-q2-active-results-compact.png",
                                  "../assets/screenshots/02-graph-q3-production-results.png",
                                  "../assets/screenshots/02-graph-q4-stability-results.png",
                                  "../assets/screenshots/02-graph-q5-supplier-results.png",
                                  "../assets/screenshots/02-graph-q6-alternative-results.png",
                                  "../assets/screenshots/02-answers-q1-formula-versions.png",
                                  "../assets/screenshots/02-answers-q2-impact-candidates.png",
                                  "../assets/screenshots/02-answers-q3-alternatives.png",
                                  "../assets/screenshots/02-answers-q4-supplier-materials.png",
                                  "../assets/screenshots/02-answers-q5-schedule-slack.png",
                                  "../assets/screenshots/02-answers-q6-before-supply-change.png"])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_graph_query_walkthrough_explains_status_and_active_filter(self):
        lesson = (ROOT / "docs" / "02-graph.md").read_text(encoding="utf-8")
        queries = lesson.split("## 3. GQL로 질의하기", 1)[1].split("## 4.", 1)[0]
        for requirement in ("**Data load completed**", "**Query → Query now**",
                            "**Code editor**", "**Run query**",
                            "**`fv.status` 열**", "**`fv.is_active` 열**",
                            "행 순서는 다를 수 있으므로 `version_id`로 대조",
                            "status — 처방 버전의 업무 상태",
                            "is_active — 활성 여부(Boolean)", "AND fv.is_active = true",
                            "원본 데이터를 삭제하거나 상태를 변경하지 않습니다"):
            self.assertIn(requirement, queries)
        for version, status, active in (
                ("FV-CRM-01-02", "폐기", "false"),
                ("FV-CRM-01-03", "현행", "true"),
                ("FV-TON-02-01", "개발중", "true"),
                ("FV-AMP-03-02", "현행", "true")):
            self.assertIn(f"| `{version}` | {status} | {active} |", queries)
        self.assertLess(queries.index("**Query → Query now**"), queries.index("**Run query**"))
        self.assertLess(queries.index("**Q1."), queries.index("02-graph-q1-results-compact.png"))
        self.assertLess(queries.index("**Q2."), queries.index("02-graph-q2-active-results-compact.png"))

    def test_graph_answers_notebook_details_session_and_query_comparisons(self):
        lesson = (ROOT / "docs" / "02-graph.md").read_text(encoding="utf-8")
        section = lesson.split("## 4. 정답 Notebook과 비교", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        for requirement in ("**`02_answers` Notebook**", "**기본 Lakehouse로 고정**",
                            "**Add data items → From OneLake catalog**",
                            "**SQL analytics endpoint**", "Notebook을 저장",
                            "세션을 다시 시작", 'material_code = "RM-HA-120"', "qc_lead_days = 7",
                            "**Connect**", "**Connecting**", "**30초–5분**",
                            "연결 완료 후 **Run all**", "재시작하지 않고 실행",
                            "기존 결과로 비교해도 됩니다",
                            "Graph와 Notebook은 Q번호가 같아도 질문이 다릅니다",
                            "**Graph Q1**", "**Graph Q2**", "**Graph Q3**", "**Graph Q4**",
                            "**Graph Q5**의 5행", "**Graph Q6**",
                            "`RM-HA-120`을 제외한 2행", "`is_impacted`가 모두 false",
                            "지연 반영 전의 정상 출력", "`03_supply_change`를 먼저 실행하지 않습니다",
                            "**Graph Q6과 다른 질문**"):
            self.assertIn(requirement, section)
        self.assertLess(section.index("**Connect**"), section.index("연결 완료 후 **Run all**"))
        for number in range(1, 7):
            self.assertIn(f"#### Notebook Q{number}.", section)
        self.assertEqual(len(re.findall(r"!\[[^]]*\]\(([^)]+)\)", section)), 6)

    def test_graph_queries_quote_reserved_product_label(self):
        lesson = (ROOT / "docs" / "02-graph.md").read_text(encoding="utf-8")
        queries = re.findall(r"``` ?gql\n(.*?)```", lesson, re.S)
        self.assertTrue(any("(p:`Product`)" in query for query in queries))
        for query in queries:
            self.assertNotRegex(query, r":\s*Product\b")
        self.assertIn("Reserved keyword 'Product'", lesson)
        self.assertIn("Ontology의 엔터티 이름을 바꿀 필요는 없습니다", lesson)

    def test_optional_entity_expansion_follows_purview_and_preserves_completed_work(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        index = readme.split("## 진행 순서\n", 1)[1].split("\n## ", 1)[0]
        self.assertLess(index.index("docs/07-purview.md"), index.index("docs/extensions/ontology.md"))
        self.assertIn("07장까지 기본 과정을 마친 뒤에만 선택", index)
        for name in ("01-ontology.md", "03-data-agent.md"):
            text = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertNotIn("extensions/ontology.md", text)
            self.assertNotIn("ont_cos_extended", text)
        purview = (ROOT / "docs" / "07-purview.md").read_text(encoding="utf-8")
        self.assertIn("(extensions/ontology.md)", purview)
        self.assertIn("00~07장 기본 과정을 마쳤습니다", purview)
        extension = (ROOT / "docs" / "extensions" / "ontology.md").read_text(encoding="utf-8")
        self.assertIn("07장 Purview까지 기본 과정을 마친 뒤에만", extension)
        self.assertIn("같은 `ont_cos`에 추가·보강", extension)
        self.assertIn("기존 엔터티·ID·키·속성·관계·바인딩은 보존", extension)
        self.assertIn("`01_prepare_data`를 다시 실행하지 않습니다", extension)
        self.assertIn("현재 데이터 상태에서", extension)
        self.assertIn("## 실습 1. Ontology Agent로 기존 모델 확장", extension)
        self.assertIn("## 실습 2. Lakehouse SQL로 업무 경로 확인", extension)
        self.assertNotIn("da_cos_extended", extension)
        admin = (ROOT / "admin" / "extended-model.md").read_text(encoding="utf-8")
        self.assertIn("참가자가 00장을 시작하기 전에", admin)
        self.assertIn("reset_ops = False", admin)

    def test_model_checkpoint_explains_inventory_and_graph_name_alignment(self):
        lesson = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        checkpoint = lesson.split("## 5. 다음 장과 연결되는 모델 점검", 1)[1].split("\n## 6.", 1)[0]
        for requirement in ("필요한 엔터티·관계가 있는지 확인하는 체크리스트",
                            "이미 확인한 키·원본을 처음부터 다시 검토하라는 뜻은 아닙니다",
                            "Entity Types·Relationship Types",
                            "`ProductionPlan`·`DevProject`·`StabilityTest`",
                            "`is_active`·`cn_registration`",
                            "`rawMaterial_suppliedBy_supplier`", "`supplied_by`",
                            "원본 매핑이 같다면 같은 역할",
                            "차이가 있는 부분만 보완",
                            "이미 확인한 항목은 그대로 유지",
                            "이름만 바꾸지 말고 해당 연결도 수정",
                            "추가 엔터티·관계가 있다는 이유만으로 삭제하지 않습니다",
                            "Graph를 생략한다면 예제 이름을 맞추기 위한 변경은 필요하지 않지만"):
            self.assertIn(requirement, checkpoint)

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

    def test_eventhouse_is_created_by_participants_in_chapter_04(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        prepared = next(line for line in readme.splitlines() if line.startswith("| 준비된 항목 |"))
        self.assertNotIn("Eventhouse", prepared)
        self.assertIn("Eventhouse `eh_cos`는 04장", readme)
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertIn("| Eventhouse | `eh_cos` | **04장에서 직접 생성** |", scenario)
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        self.assertIn("**+ New item**", lesson)
        self.assertIn("같은 이름의 기본 KQL Database가 자동 생성", lesson)
        self.assertIn("Eventhouse와 기본 KQL Database 이름을 모두 `eh_cos`로 유지", lesson)
        self.assertLess(lesson.index("## 1. Eventhouse 만들기"), lesson.index("## 2. 이벤트 테이블 만들기"))
        self.assertIn("이미 `eh_cos`가 있다면 중복 생성하거나 삭제하지 말고", lesson)
        self.assertIn("MaterialSupplyEvent\n| count", lesson)

    def test_operations_guide_explains_teams_app_setup_and_shows_eventhouse_creation(self):
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        setup = lesson.split("### Teams 알림 앱 확인", 1)[1].split("## 1.", 1)[0]
        for requirement in ("**Teams 안에 앱을 추가**", "자동으로 설치될 수 있으므로",
                            "수동 추가가 항상 필요한 것은 아닙니다", "이미 알림을 받고 있다면",
                            "아래 절차는 건너뜁니다", "조직 계정", "**앱(Apps) 메뉴**", "`Fabric Operations Agent`",
                            "**추가(Add) 버튼**", "Teams 관리자"):
            self.assertIn(requirement, setup)
        setup_images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", setup)
        self.assertEqual(setup_images, ["../assets/screenshots/04-teams-app-search.png"])
        self.assertNotIn("앱이 설치되어 있어야 메시지를 받을 수 있습니다", lesson)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("앱 수동 추가는 필요한 경우에만 진행", readme)
        creation = lesson.split("## 1. Eventhouse 만들기", 1)[1].split("## 2.", 1)[0]
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", creation)
        self.assertEqual(images, ["../assets/screenshots/04-create-eventhouse.png",
                                  "../assets/screenshots/04-eventhouse-overview.png",
                                  "../assets/screenshots/04-kql-database-empty.png"])
        events = lesson.split("## 2. 이벤트 테이블 만들기", 1)[1].split("## 3.", 1)[0]
        event_images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", events)
        self.assertEqual(event_images, ["../assets/screenshots/04-event-table-created.png",
                                        "../assets/screenshots/04-event-count-zero.png"])
        for image in setup_images + images + event_images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        for requirement in ("`eh_cos_queryset`", "**KQL Queryset**", "**Run**",
                            "테이블 정의 결과", "`Count = 0`", "집계 결과 1행입니다"):
            self.assertIn(requirement, events)
        self.assertNotIn("이벤트가 1건 들어왔다는 뜻이 아닙니다", events)
        self.assertNotIn("이벤트 건수는 `Count` 열의 값으로 판단", events)

    def test_operations_guide_shows_review_notebook_and_agent_creation(self):
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        review = lesson.split("## 3. 승인 후 실행할 Notebook 살펴보기", 1)[1].split("## 4.", 1)[0]
        creation = lesson.split("## 4. Operations Agent 만들기", 1)[1].split("## 5.", 1)[0]
        self.assertIn("**지금 실행하지 않습니다.**", review)
        self.assertIn("승인 후 액션에서 전달", review)
        self.assertIn("**Location**에 내 작업 영역 `cos-pNNN`", creation)
        for section, expected in ((review, ["../assets/screenshots/04-review-notebook.png"]),
                                  (creation, ["../assets/screenshots/04-create-operations-agent.png",
                                              "../assets/screenshots/04-action-parameters.png",
                                              "../assets/screenshots/04-action-review.png",
                                              "../assets/screenshots/04-agent-setup-connected.png"])):
            images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", section)
            self.assertEqual(images, expected)
            for image in images:
                self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        parameters = dict(re.findall(r"^\s*\| `(event_id|material_code|eventhouse_name)` \| ([^|\n]+) \|",
                                     creation, re.M))
        self.assertEqual(set(parameters), {"event_id", "material_code", "eventhouse_name"})
        self.assertIn("MaterialSupplyEvent.event_id", parameters["event_id"])
        self.assertIn("MaterialSupplyEvent.material_code", parameters["material_code"])
        self.assertIn("항상 eh_cos를 전달", parameters["eventhouse_name"])
        self.assertIn("**Description은 직접 입력**", creation)
        self.assertIn("**Next**", creation)
        self.assertIn("**Review and create** 단계", creation)
        self.assertIn("**Action connected**", creation)

    def test_operations_guide_uses_english_instructions_and_numeric_transition(self):
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        creation = lesson.split("## 4. Operations Agent 만들기", 1)[1].split("## 5.", 1)[0]
        instructions = re.findall(r"``` text\n(.*?)```", creation, re.S)
        self.assertEqual(len(instructions), 1)
        self.assertTrue(instructions[0].isascii())
        self.assertIn("지침과 업무 목표는 영어만 지원", creation)
        for requirement in ("Each event_id identifies a separate business object",
                            "the row with the latest event_time",
                            'open_flag = iff(event_status == "open", 1, 0)',
                            "not an existing table column", "Do not change the table schema",
                            "crosses above 0.5", "including a change from null to 1",
                            "Changes to open for a text property",
                            "Becomes true for a boolean property",
                            "Detect the first open observation of a new event_id",
                            "Do not repeatedly notify for the same event_id while its status remains open",
                            "Keep non-open states",
                            "Write notification titles, summaries, and recommended-action explanations in Korean.",
                            "Keep event IDs, material codes, field names, and action names unchanged.",
                            "Only after human approval", 'eventhouse_name set to "eh_cos"',
                            "Do not change purchase orders or formulas"):
            self.assertIn(requirement, instructions[0])
        playbook = lesson.split("## 5. Playbook 생성과 검토", 1)[1].split("## 6.", 1)[0]
        for requirement in ("arg_max(event_time, *) by event_id", "조회 시간 범위",
                            "**Crosses above 0.5**", "**Changes to open**", "**Becomes true**",
                            "**Is above**", "`null → 1`", "`open → open`(`1 → 1`)",
                            "새 `event_id`의 첫 `open`",
                            "다른 상태를 거쳐 다시 `open`이 되는 것은 별도 전환",
                            "`RequestMaterialReview`", "**용어집 생성 확인 예시**", "실제 알림은 6–7번"):
            self.assertIn(requirement, playbook)
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", playbook)
        self.assertEqual(images, ["../assets/screenshots/04-playbook-glossary.png",
                                  "../assets/screenshots/04-playbook-rule.png",
                                  "../assets/screenshots/04-playbook-saved.png",
                                  "../assets/screenshots/04-agent-started.png"])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("**Configuration saved successfully** 메시지가 나오면 **Start**를 누를 수 있습니다",
                      playbook)
        self.assertIn("**Agent started successfully**", playbook)
        self.assertIn("**Stop** 버튼이 활성화", playbook)
        self.assertLess(playbook.index("**Configuration saved successfully**"),
                        playbook.index("**Agent started successfully**"))
        self.assertIn("operations-agent-limitations#language-and-model-behavior-limitations", lesson)
        admin = (ROOT / "admin" / "preview-limitations.md").read_text(encoding="utf-8")
        self.assertIn("지침과 업무 목표는 현재 영어만 지원", admin)
        self.assertIn("영문 지침에서 한국어 알림 출력을 요청", admin)
        self.assertIn("**Crosses above 0.5**", admin)
        self.assertIn("**Changes to open**", admin)
        self.assertIn("**Becomes true**", admin)
        self.assertIn("상태 유지 중 반복 알림 여부", admin)
        self.assertIn("activator-detection-conditions#conditions", lesson)

    def test_operations_rule_example_and_correction_are_in_collapsed_toggle(self):
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        playbook = lesson.split("## 5. Playbook 생성과 검토", 1)[1].split("## 6.", 1)[0]
        toggles = re.findall(r"<details>\s*<summary>([^<]+)</summary>(.*?)</details>", playbook, re.S)
        self.assertEqual(len(toggles), 1)
        title, example = toggles[0]
        self.assertEqual(title, "Rule 정상 예시와 다르게 생성됐을 때 수정 방법")
        self.assertNotIn("<details open", playbook)
        for requirement in ("**아래 Rule은 수정 없이 사용할 수 있는 예시**",
                            "04-playbook-rule.png", "`Crosses Above` / `0.5`",
                            "`Id = event_id`", "`Timestamp = event_time`",
                            "조건 이름만 맞추려고 수정할 필요는 없습니다",
                            "`Changes to` / `open`", "`Becomes true`",
                            "`startTime`·`endTime`", "**Copilot**",
                            "**질의와 하단 조건을 모두 확인**", "승인 실행은 05장"):
            self.assertIn(requirement, example)
        prompts = re.findall(r"```text\n(.*?)```", example, re.S)
        self.assertEqual(len(prompts), 1)
        self.assertTrue(prompts[0].isascii())
        for requirement in ("Correct the existing supply-delay rule only",
                            "OpenFlag Crosses Above 0.5", "Keep non-open states as 0",
                            "preserve an equivalent existing transition condition",
                            "Detect the first open observation of a new event_id",
                            "Do not repeatedly notify for the same event_id while its status remains open",
                            "Preserve the query time-window parameters",
                            "requiring human approval", 'eventhouse_name set to "eh_cos"',
                            "Do not change the table schema or existing data"):
            self.assertIn(requirement, prompts[0])

    def test_operations_guide_shows_supply_change_parameters_and_outputs(self):
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        supply_change = lesson.split("## 6. 공급 지연 발생시키기", 1)[1].split("## 7.", 1)[0]
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", supply_change)
        self.assertEqual(images, ["../assets/screenshots/04-supply-change-notebook.png",
                                  "../assets/screenshots/04-supply-delay-result.png",
                                  "../assets/screenshots/04-material-impact-result.png",
                                  "../assets/screenshots/04-open-event-result.png",
                                  "../assets/screenshots/04-kql-open-event.png"])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        for requirement in ("**Run all**", "`impacted = true` 3행",
                            "SUP-20261102-RM-HA-120-r1", "`event_status = open`", "`impacted_count = 3`"):
            self.assertIn(requirement, supply_change)
        outputs = re.findall(r"^- \*\*([1-3])\. [^*]+\*\* (.+)$", supply_change, re.M)
        self.assertEqual([number for number, _ in outputs], ["1", "2", "3"])
        self.assertIn("PO-5501", outputs[0][1])
        self.assertIn("ops.material_impact", outputs[1][1])
        self.assertIn("영향 3건", outputs[1][1])
        self.assertIn("MaterialSupplyEvent에 open 추가", outputs[2][1])
        self.assertIn("이벤트 조회 표 1행", outputs[2][1])

    def test_operations_guide_shows_teams_recommendation_without_requiring_manual_app_add(self):
        lesson = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        notifications = lesson.split("## 7. Teams 알림 받기", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        self.assertIn("**앱을 수동으로 추가할 필요는 없습니다.**", notifications)
        self.assertIn("**Show details**", notifications)
        self.assertIn("**아직 Proceed를 누르지 않습니다**", notifications)
        self.assertIn("숫자형 상태 값 1", notifications)
        self.assertIn("`OpenFlagValue`", notifications)
        self.assertIn("이 예시의 상세 화면에는 지연 일수·영향 건수가 표시되지 않습니다.", notifications)
        details = re.search(
            r"<details>\s*<summary>Show details — 이벤트·규칙 상세 화면</summary>(.*?)</details>",
            notifications, re.S,
        )
        self.assertIsNotNone(details)
        self.assertIn('`run_tag = "r2"`로 재실행한 예시', details.group(1))
        self.assertNotIn('`run_tag = "r2"`', notifications[:details.start()])
        self.assertIn("**알림 본문과 규칙 설명이 한국어로 생성된 결과**", notifications)
        self.assertIn("제목·기본 레이블·버튼은 영어로 남을 수 있습니다.", notifications)
        self.assertNotIn("미검증", notifications)
        self.assertNotIn("기본 실습에는 포함하지 않습니다", notifications)
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", notifications)
        self.assertEqual(images, [
            "../assets/screenshots/04-teams-review-notification.png",
            "../assets/screenshots/04-teams-notification-details.png",
        ])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_sql_database_is_created_by_participants_before_schema_and_publishing(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        prepared = next(line for line in readme.splitlines() if line.startswith("| 준비된 항목 |"))
        self.assertNotIn("sqldb_cos", prepared)
        self.assertIn("SQL DB `sqldb_cos`는 06장에서 직접 생성", readme)
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertIn("| SQL database | `sqldb_cos` | **06장에서 직접 생성** |", scenario)
        lesson = (ROOT / "docs" / "06-serving-db.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## \d\. .+$", lesson, re.M)
        self.assertEqual(headings, [
            "## 1. SQL database 만들기", "## 2. Serving 스키마 만들기", "## 3. 승인 결과 게시",
            "## 4. 담당 팀별 조회", "## 5. 검토 착수와 이력 확인", "## 6. 재게시해도 업무 상태가 유지되는지 확인",
        ])
        self.assertIn("**+ New item**", lesson)
        self.assertIn("이름을 `sqldb_cos`로 입력하고 **Create**", lesson)
        self.assertIn("기본 권한은 **Contributor**", lesson)
        self.assertNotIn("Contributor만으로는 SQL DB를 생성할 수 없습니다", lesson)
        self.assertIn("샘플 데이터는 넣지 않습니다", lesson)
        self.assertIn("이미 `sqldb_cos`가 있다면 중복 생성하거나 삭제하지 않고", lesson)
        self.assertIn("3단계에서 생성한 게시 SQL을 다시 실행하고 5단계 조회를 반복", lesson)
        admin = (ROOT / "admin" / "README.md").read_text(encoding="utf-8")
        self.assertIn("--users users.csv --role Contributor", admin)
        self.assertIn("참가자용 `sqldb_cos`와 Serving 스키마는 사전 생성하지 않습니다", admin)
        self.assertIn("기존 역할은 자동 승격·강등하지 않으므로", admin)
        self.assertIn("공식 문서 간 안내가 상충합니다", admin)
        self.assertIn("실제 테넌트·참가자와 같은 Contributor 계정으로 사전 리허설", admin)
        self.assertIn("https://learn.microsoft.com/en-us/fabric/fundamentals/roles-workspaces", admin)
        self.assertIn("https://learn.microsoft.com/en-us/rest/api/fabric/sqldatabase/items/create-sql-database", admin)
        self.assertIn("https://learn.microsoft.com/en-us/fabric/database/sql/create", admin)
        self.assertNotIn("관리자가 **SQL database** 항목 `sqldb_cos`를 만들었습니다", lesson)

    def test_data_agent_setup_focuses_on_ontology_and_connected_lakehouse(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        prerequisites = lesson.split("## 시작 전 확인", 1)[1].split("## 1.", 1)[0]
        self.assertNotIn("최대 5개", prerequisites)
        setup = lesson.split("## 1. Data Agent 만들고 원본 연결", 1)[1].split("## 2.", 1)[0]
        for requirement in ("**Create data agent**", "`da_cos`", "**No sources added**",
                            "**Add an ontology**", "**Ontology**", "선택한 뒤 활성화",
                            "**Ontology → ont_cos → Entity types:**",
                            "**Ontology data sources → lh_cos → Schemas → gold → Tables:**",
                            "`formula_line`", "화면에 표시된 테이블",
                            "중복으로 추가하지 않습니다", "읽기 권한"):
            self.assertIn(requirement, setup)
        self.assertNotIn("material_alternative", setup)
        expected_result = setup.split("**확인할 결과:**", 1)[1].strip()
        self.assertEqual(expected_result,
                         "Sources에 `ont_cos`와 `lh_cos`가 연결됩니다. 다음 단계에서 지침을 입력하고, "
                         "질문 검증은 3번의 Ontology Agent에서 진행합니다.")
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", setup)
        self.assertEqual(images, ["../assets/screenshots/03-create-data-agent.png",
                                  "../assets/screenshots/03-data-agent-empty.png",
                                  "../assets/screenshots/03-select-ontology.png",
                                  "../assets/screenshots/03-ontology-connected.png"])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_data_agent_separates_lakehouse_basics_and_optional_graph_comparison(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        for requirement in ("1–2번은 Data Agent 구성 체험", "3–4번은 Ontology Agent 질문·Notebook 대조",
                            "5번은 Graph 기반 선택 실습",
                            "연결된 대상·경로를 찾으려면 Graph",
                            "원본의 상세 조건과 계산을 검증하려면 Lakehouse"):
            self.assertIn(requirement, lesson)
        self.assertNotIn("Graph가 계산을 전혀 못 한다는 뜻", lesson)
        setup = lesson.split("## 1. Data Agent 만들고 원본 연결", 1)[1].split("## 2.", 1)[0]
        self.assertIn("기본 `da_cos`에는 **Graph model을 추가하지 않습니다.**", setup)
        optional = lesson.split("## 5. 선택 실습", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        for requirement in ("별도 `da_cos_graph`", "기존 `da_cos`는 그대로 유지",
                            "**Graph 원본만 연결**", "Ontology나 Lakehouse는 추가하지 않습니다",
                            "Materialize·새로 고침 시점의 데이터",
                            "새 문항을 추가하지 않고", "기본 7문항 중 DA04",
                            "RM-HA-120 자체는 제외", "**Clear chat**",
                            "`RM-PHE-002`", "`P-101`·`P-102`·`P-301`",
                            "**`da_cos`는 Lakehouse SQL**", "**`da_cos_graph`는 Graph GQL**",
                            "Lakehouse를 추가하지 않습니다", "기본 실습은 완료"):
            self.assertIn(requirement, optional)
        self.assertNotIn("탐색 방향과 저장된 관계 방향을 구분", optional)
        admin = (ROOT / "admin" / "README.md").read_text(encoding="utf-8")
        self.assertIn("DA04의 다른 원료 사용처 확인 부분 재사용", admin)
        self.assertLess(lesson.index("## 4. 답과 근거 검증하기"), lesson.index("## 5. 선택 실습"))

    def test_graph_agent_screenshots_and_direct_material_path_are_documented(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        optional = lesson.split("## 5. 선택 실습", 1)[1].split("## 이 장의 완료 기준", 1)[0]
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", optional)
        self.assertEqual(images, [
            "../assets/screenshots/03-graph-agent-select-source.png",
            "../assets/screenshots/03-graph-agent-instructions.png",
            "../assets/screenshots/03-ontology-agent-query-execution.png",
            "../assets/screenshots/03-graph-agent-uses-material.png",
        ])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        queries = re.findall(r"```gql\n(.*?)```", optional, re.S)
        self.assertEqual(len(queries), 1)
        query = " ".join(queries[0].split())
        self.assertIn("(origin:RawMaterial)-[:supplied_by]->(s:Supplier)", query)
        self.assertIn("<-[:supplied_by]-(other:RawMaterial) <-[:uses_material]-(fv:FormulaVersion)", query)
        self.assertIn("<-[:made_with]-(p:`Product`)", query)
        self.assertIn("other.material_code <> origin.material_code", query)
        self.assertIn("fv.is_active = true", query)
        self.assertIn("RETURN DISTINCT", query)
        self.assertNotIn("has_ingredient", query)
        self.assertIn("RawMaterialOther → Ingredient ← RawMaterialForFormula", optional)
        self.assertIn("문자열 상수", optional)
        self.assertIn("실제 실행 단계", optional)
        self.assertNotIn("조회 결과 화면 예시</summary>", optional)
        gql_section = optional.split("### 5-4.", 1)[1]
        self.assertNotIn("<details>", gql_section)
        self.assertNotIn("복사한 코드가", gql_section)
        self.assertNotIn("03-graph-agent-generated-gql.png", gql_section)
        self.assertIn("03-graph-agent-uses-material.png", gql_section)

    def test_ontology_agent_execution_example_distinguishes_source_and_result_grain(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        example = lesson.split("<summary>Ontology Agent의 조회 실행 단계 예시와 비교 기준</summary>", 1)[1]
        example = example.split("</details>", 1)[0]
        for requirement in ("실제 발주 ETA까지 확인한", "5-2의 공통 질문은 사용처만 비교",
                            "Executing unified query on the child Eventhouse",
                            "evaluate sql_request(...)", "실행 계층과 업무 데이터 원본 구분",
                            "전체 질의의 연결 정보", "`lh_cos` 바인딩",
                            "원료·처방·제품 조합은 3행", "제품별 행을 제거하지 않습니다",
                            "`2026-11-10`", "`PO-5505`", "지연이 다른 원료에도 발생했다고 추정하지",
                            "질의는 중간이 생략", "**전체 실행 질의와 결과**"):
            self.assertIn(requirement, example)

    def test_preview_lab_uses_ontology_agent_plan_after_data_agent_setup(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        intro = lesson.split("## 실습 구성과 사용 권장 기준", 1)[0]
        for requirement in ("Ontology v2는 아직 Preview", "워크숍에서 확인한 환경",
                            "메타데이터", "설명(description)", "동의어(synonyms)",
                            "모든 원본 조회가 불가능하다는 뜻은 아니며", "배포 버전·환경",
                            "Data Agent 생성·원본 연결·Agent instructions 입력까지 체험",
                            "Ontology Agent"):
            self.assertIn(requirement, intro)
        priming = lesson.split("### 3-1.", 1)[1].split("### 3-2.", 1)[0]
        for requirement in ("**Plan 모드**", "**대화 첫 메시지**",
                            "Agent instructions는 이 대화에 자동 적용되지 않습니다",
                            "조회만 수행하세요", "원본 데이터는 변경하지 마세요",
                            "해당 원료를 쓰지 않는 처방은 이 목록에 넣지 마세요",
                            "is_active = true", "개발중이어도 활성인 처방은 포함",
                            "production_plan.planned_date - QC 리드타임",
                            "stability_test.batch_date - QC 리드타임",
                            "시험에만 QC를 적용하거나", "두 대상 모두 원본 일정",
                            "계획일 또는 배치일 - 원료 필요일 = 적용한 QC 일수",
                            "필요일과 QC를 고정", "달력일", "최종 발주일 + 리드타임 = 원료 필요일",
                            "대체 사용 승인", "조회 실패, 정상 조회 결과 0행, 속성 미확인",
                            "원본에 열·데이터가 없는 것을 구분", "실제 실행한 질의",
                            "**같은 대화에서**", "새 대화·페이지 새로고침",
                            "공통 프롬프트도 다시 보냅니다", "영구 저장하는 작업이 아닙니다"):
            self.assertIn(requirement, priming)
        self.assertNotRegex(priming, r"FV-CRM|PP-110[123]|ST-0711|50,000")
        completion = lesson.split("## 이 장의 완료 기준", 1)[1].split("## ", 1)[0]
        self.assertIn("Agent instructions 입력을 체험", completion)
        self.assertIn("Ontology Agent의 **Plan 모드**", completion)
        basic_lab = lesson.split("## 5. 선택 실습", 1)[0]
        self.assertEqual(len(re.findall(r"!\[[^]]*\]\([^)]+\)", basic_lab)), 5)
        self.assertIn("https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent", lesson)

    def test_data_agent_selects_seven_questions_with_inline_answers_and_verification_outputs(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        questions = re.findall(r"^\| (DA\d{2}) \| ([^|]+) \| `([^`]+)` \| ([^|\n]+) \|$", lesson, re.M)
        ids = [f"DA{i:02}" for i in range(1, 8)]
        self.assertEqual([q[0] for q in questions], ids)
        self.assertEqual([q[1] for q in questions],
                         ["대조", "규칙", "규칙", "관계", "What-if",
                          "여러 데이터 통합", "의사결정 지원"])
        for _, _, prompt, expected_answer in questions:
            self.assertNotRegex(prompt, r"DA\d{2}")
            self.assertNotIn("저장된 관계 방향", prompt)
            self.assertTrue(expected_answer.strip())
        self.assertNotIn("공급사 경로", lesson)
        self.assertIn("3-2의 질문 7개를 기준으로 같은 ID·질문·순서", lesson)
        self.assertIn("| ID | 유형 | 질문 | 기대 답변 |", lesson)
        self.assertIn("**질문 열만 복사**", lesson)
        verification = lesson.split("## 4. 답과 근거 검증하기", 1)[1].split("## 5.", 1)[0]
        self.assertEqual(re.findall(r"^\| (DA\d{2}) [^|]+\| \d+행", verification, re.M), ids)
        toggles = re.findall(r"<details>\s*<summary>([^<]+)</summary>(.*?)</details>", verification, re.S)
        self.assertEqual(len(toggles), 1)
        self.assertEqual(toggles[0][0], "DA03의 조건 판정 열 읽기")
        self.assertIn("schedule_cn_ok = schedule_ok AND cn_ok", toggles[0][1])
        self.assertEqual(verification.count("<details>"), 1)
        self.assertEqual(verification.count("</details>"), 1)
        self.assertNotIn("<details open", verification)
        self.assertNotIn("상세 확인:", lesson)
        self.assertNotIn("정답·필수 근거", lesson)
        self.assertIn("핵심 7문항을 DA01–DA07 순서대로", lesson)
        self.assertIn("Notebook에 준비된 SQL 실행 결과와 비교", lesson)
        self.assertIn("같은 번호·질문·순서", lesson)
        self.assertIn("DA01도 전용 셀", lesson)
        self.assertNotIn("최신 `02_answers.ipynb`", lesson)
        for doc in (ROOT / "README.md", ROOT / "admin" / "README.md", ROOT / "docs" / "03-data-agent.md"):
            self.assertNotIn("12문항", doc.read_text(encoding="utf-8"), doc.name)
            self.assertNotIn("중요도순", doc.read_text(encoding="utf-8"), doc.name)
        self.assertLess(lesson.index("| DA07 | 의사결정 지원 |"), lesson.index("<details>"))
        self.assertIn("현재 연결된 10개 테이블·9개 엔터티", lesson)
        self.assertIn("Clear chat", lesson)
        self.assertIn("최초 답", lesson)
        self.assertIn("0일은 일정 기준 영향 없음", lesson)
        self.assertIn("농도·제형 환산", lesson)
        self.assertNotIn("질문 5개", lesson)

    def test_data_agent_source_instructions_are_optional_for_basic_lab(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        instructions = lesson.split("## 2. 에이전트 지침 입력", 1)[1].split("## 3.", 1)[0]
        self.assertTrue(instructions.strip().startswith(
            "기본 에이전트 **`da_cos`의 Agent instructions**에 아래 지침을 붙여 넣습니다.\n\n``` text\n"))
        self.assertLess(instructions.index("``` text"), instructions.index("**참고: 설정 항목별 역할**"))
        image = "../assets/screenshots/03-agent-instructions.png"
        self.assertIn(image, instructions)
        self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertLess(instructions.index("```\n"), instructions.index(image))
        self.assertIn("**Setup → Agent instructions**", instructions)
        self.assertIn("**Test the agent's responses**", instructions)
        self.assertIn("기본 실습은 Agent instructions만 입력하고 시작합니다", instructions)
        self.assertIn("Data source instructions", instructions)
        self.assertIn("조인·필터 등 질의 생성 규칙", instructions)
        self.assertIn("선택 설정", instructions)
        self.assertIn("별도로 입력하지 않습니다", instructions)
        reference = instructions.split("**참고: 설정 항목별 역할**", 1)[1].split("```", 1)[0]
        self.assertEqual(re.findall(r"^\| \*\*([^*]+)\*\* \|", reference, re.M),
                         ["Agent instructions", "Data source description",
                          "Data source instructions", "Example queries"])
        for role in ("에이전트 전체", "원본 선택", "질의 생성 지침", "자연어 질문과 검증된 질의"):
            self.assertIn(role, reference)
        self.assertIn("https://learn.microsoft.com/en-us/fabric/data-science/data-agent-configurations", lesson)

    def test_agent_boundary_question_distinguishes_zero_slack_caution(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        questions = {
            question_id: (prompt, expected)
            for question_id, prompt, expected in re.findall(
                r"^\| (DA\d{2}) \| [^|]+ \| `([^`]+)` \| ([^|\n]+) \|$", lesson, re.M)
        }
        self.assertIn("일정 지연 여부와 추가 여유 유무를 구분", questions["DA02"][0])
        self.assertIn("0일·일정 지연 없음", questions["DA02"][1])
        self.assertIn("추가 여유 없음·주의", questions["DA02"][1])
        self.assertIn("-1일·일정 1일 지연", questions["DA02"][1])
        self.assertIn("음수는 일정 지연", lesson)
        self.assertIn("양수는 일정상 여유 있음", lesson)
        self.assertIn("입고·시험 시각이나 추가 작업 시간은 반영하지", lesson)
        for section in (lesson.split("## 2.", 1)[1].split("## 3.", 1)[0],
                        lesson.split("### 3-1.", 1)[1].split("### 3-2.", 1)[0]):
            self.assertIn("추가 여유", section)
            self.assertIn("주의", section)

    def test_purview_optional_activities_have_names_distinct_from_ontology_expansion(self):
        lesson = (ROOT / "docs" / "07-purview.md").read_text(encoding="utf-8")
        self.assertIn("## 3. 선택: DLP 정책 팁 확인", lesson)
        self.assertIn("## 4. 선택: 카탈로그 자산 검색", lesson)
        self.assertIn("둘 다 해야 기본 실습이 완료되는 것은 아닙니다", lesson)
        self.assertIn("Ontology 엔터티 확장 실습과는 별개", lesson)
        for md in [ROOT / "README.md", *ALL_DOCS, ROOT / "admin" / "README.md"]:
            self.assertNotRegex(md.read_text(encoding="utf-8"), r"확장 [AB]\b|준비된 환경의 확장", md.name)

    def test_learner_creates_gold_tables_before_building_the_ontology(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("작업 영역·접근 권한·Notebook 5개", readme)
        self.assertIn("**00장에서 Lakehouse `lh_cos` 생성", readme)
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## \d\. .+$", scenario, re.M), [
            "## 1. 작업 영역과 권한 확인", "## 2. 준비된 Notebook 확인", "## 3. Lakehouse 직접 만들기",
            "## 4. Notebook에 기본 Lakehouse 연결", "## 5. Notebook으로 gold 테이블 직접 만들기",
        ])
        self.assertIn("Lakehouse schemas", scenario)
        self.assertIn("Tables → dbo", scenario)
        self.assertIn("미리 준비되어 있습니다", scenario)
        self.assertIn("이 장에서는 `01_prepare_data`에만 연결합니다", scenario)
        self.assertNotIn("Notebook 5개 각각", scenario)
        self.assertIn("**Data items → Add data items → From OneLake catalog**", scenario)
        self.assertIn("**기본 Lakehouse로 고정**(핀)", scenario)
        self.assertIn("세션을 다시 시작", scenario)
        self.assertIn("**00장에서는 `01_prepare_data`만 실행합니다.**", scenario)
        names = runpy.run_path(str(ROOT / "admin" / "provision.py"))["NOTEBOOKS"]
        for name in names:
            self.assertIn(f"`{name}`", scenario)
        self.assertIn("reset_ops = False", scenario)
        self.assertIn("Run all", scenario)
        self.assertIn("쓰기 전에 오류로 중지", scenario)
        self.assertIn("28개 테이블", scenario)
        self.assertIn("include_extended = True", scenario)
        self.assertIn("original_eta", scenario)
        self.assertNotIn("처음에는 작업 영역이 비어", scenario)
        ontology = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        self.assertIn("`01_prepare_data`를 직접 실행해", ontology)
        extension = (ROOT / "docs" / "extensions" / "ontology.md").read_text(encoding="utf-8")
        self.assertIn("00장의 첫 적재에서 직접 만든", extension)

    def test_participant_setup_uses_preimported_notebooks_without_file_uploads_or_pasting(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        prepared = scenario.split("## 2. 준비된 Notebook 확인\n", 1)[1].split("\n## 3.", 1)[0]
        self.assertIn("| Notebook 이름 | 실행 시점 |", prepared)
        self.assertIn("참가자는 파일을 가져오거나 코드를 붙여 넣지 않습니다", prepared)
        self.assertNotIn("workshop-files.zip", scenario)
        self.assertNotIn("notebooks/paste", scenario)
        self.assertNotIn("New item → Notebook", scenario)
        self.assertIn(WORKSHOP_DOWNLOAD_URL, (ROOT / "README.md").read_text(encoding="utf-8"))
        for path in [ROOT / "README.md", *ALL_DOCS]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(document=path.relative_to(ROOT)):
                self.assertNotIn("Upload files", text)
                self.assertNotIn("Import → Notebook", text)
                self.assertNotIn("Files/workshop", text)

    def test_scenario_selects_prepared_notebook_and_lakehouse_creation_screenshots(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        images = re.findall(r"!\[[^]]*\]\(([^)]+)\)", scenario)
        self.assertEqual(images, ["../assets/screenshots/00-prepared-notebooks.png",
                                  "../assets/screenshots/00-lakehouse-create.png",
                                  "../assets/screenshots/00-select-lakehouse.png",
                                  "../assets/screenshots/00-prepare-data-output.png",
                                  "../assets/screenshots/00-prepare-data-purchase-order.png",
                                  "../assets/screenshots/00-lakehouse-purchase-order.png"])
        for image in images:
            self.assertTrue((ROOT / "docs" / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertLess(scenario.index("## 2. 준비된 Notebook 확인"), scenario.index(images[0]))
        self.assertLess(scenario.index(images[0]), scenario.index("## 3. Lakehouse 직접 만들기"))
        self.assertLess(scenario.index("## 3. Lakehouse 직접 만들기"), scenario.index(images[1]))
        self.assertLess(scenario.index(images[1]), scenario.index("## 4. Notebook에 기본 Lakehouse 연결"))
        self.assertLess(scenario.index("## 4. Notebook에 기본 Lakehouse 연결"), scenario.index(images[2]))
        self.assertLess(scenario.index(images[2]), scenario.index("## 5. Notebook으로 gold 테이블 직접 만들기"))
        self.assertLess(scenario.index("## 5. Notebook으로 gold 테이블 직접 만들기"), scenario.index(images[3]))
        self.assertLess(scenario.index(images[3]), scenario.index("## 이 장의 완료 기준"))
        self.assertLess(scenario.index("**예상 출력 — 발주 확인:**"), scenario.index(images[4]))
        self.assertNotIn("확인할 셀:", scenario)
        self.assertNotIn("마지막 조회 셀 결과", scenario)
        self.assertNotIn("아직 지연은 반영하지 않았으며", scenario)
        sections = (
            ("### 5-3. 테이블 적재 셀 결과", "### 5-4.", images[3:4], "tables_to_load = select_tables(include_extended)"),
            ("### 5-4. 발주 확인 셀 결과", "### 5-5.", images[4:5], "WHERE po_id = 'PO-5501'"),
            ("### 5-5. Lakehouse에서 전체 발주 확인", "**재실행 주의:**", images[5:6], "Lakehouse 테이블 화면"),
        )
        for heading, end, expected_images, identifier in sections:
            section = scenario.split(heading, 1)[1].split(end, 1)[0]
            with self.subTest(section=heading):
                self.assertIn(identifier, section)
                self.assertEqual(re.findall(r"!\[[^]]*\]\(([^)]+)\)", section), expected_images)

    def test_preparation_cell_code_blocks_match_notebook_cells(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        notebook = json.loads((ROOT / "notebooks" / "01_prepare_data.ipynb").read_text(encoding="utf-8"))
        code_cells = ["".join(cell["source"]).strip() for cell in notebook["cells"] if cell["cell_type"] == "code"]
        for heading in ("### 5-3. 테이블 적재 셀 결과", "### 5-4. 발주 확인 셀 결과"):
            section = scenario.split(heading, 1)[1].split("\n### ", 1)[0]
            with self.subTest(section=heading):
                blocks = re.findall(r"```python\n(.*?)\n```", section, re.S)
                self.assertEqual(len(blocks), 1)
                ast.parse(blocks[0])
                self.assertIn(blocks[0].strip(), code_cells)

    def test_spark_startup_guidance_is_next_to_connect_and_avoids_fixed_run_times(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertIn("SQL analytics endpoint가 함께 보이면 항목 유형", scenario)
        self.assertNotIn("다른 Notebook은 Lakehouse만 연결해 둡니다", scenario)
        self.assertNotIn("연결 설정을 저장하는 것과", scenario)
        self.assertIn("Spark 세션 준비 단계", scenario)
        self.assertIn("세션 ID·경과 시간·오류", scenario)
        startup = scenario.split("### 5-2. Spark 세션 시작 후 전체 실행", 1)[1].split("### 5-3.", 1)[0]
        self.assertIn("30초–5분", startup)
        self.assertLess(startup.index("**Connect**"), startup.index("**세션 시작 대기:**"))
        self.assertLess(startup.index("**세션 시작 대기:**"), startup.index("연결 완료 후 **Run all**"))
        admin = (ROOT / "admin" / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://learn.microsoft.com/en-us/fabric/data-engineering/spark-compute", admin)
        self.assertIn("Starter pool 용량은 보장되지 않으며", admin)
        self.assertIn("속도를 위해 조직의 보안 설정을 해제하지 않습니다", admin)
        for lesson in ("02-graph.md", "05-approval.md"):
            self.assertNotIn("세션 시작 포함", (ROOT / "docs" / lesson).read_text(encoding="utf-8"))

    def test_setup_starts_session_before_running_only_the_preparation_notebook(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        prepared = scenario.split("## 2. 준비된 Notebook 확인\n", 1)[1].split("\n## 3.", 1)[0]
        self.assertIn("**00장에서는 `01_prepare_data`만 실행합니다.**", prepared)
        self.assertIn("나머지 Notebook은 해당 장의 안내에 따라 실행합니다", prepared)
        self.assertIn("파일 번호 순서대로 한꺼번에 실행하지 않습니다", prepared)
        self.assertIn("| `02_answers` | 01–03장:", prepared)
        for notebook, chapter in (("03_supply_change", "04장"), ("nb_apply_review", "05장"),
                                  ("04_publish_serving", "06장")):
            self.assertIn(f"| `{notebook}` | {chapter}", prepared)
        loading = scenario.split("## 5. Notebook으로 gold 테이블 직접 만들기\n", 1)[1].split("\n## ", 1)[0]
        self.assertLess(loading.index("**Connect**"), loading.index("**Run all**"))
        self.assertIn("연결이 완료될 때까지 기다립니다", loading)
        self.assertIn("연결 완료 후 **Run all**", loading)

    def test_later_notebooks_attach_lakehouse_when_their_chapter_uses_them(self):
        for lesson in ("01-ontology.md", "02-graph.md", "03-data-agent.md",
                       "04-operations-agent.md", "06-serving-db.md"):
            with self.subTest(lesson=lesson):
                text = (ROOT / "docs" / lesson).read_text(encoding="utf-8")
                self.assertIn("기본 Lakehouse", text)
                self.assertIn("00-scenario.md#4-notebook에-기본-lakehouse-연결", text)
        operations = (ROOT / "docs" / "04-operations-agent.md").read_text(encoding="utf-8")
        action_setup = operations.split("## 3. 승인 후 실행할 Notebook 살펴보기", 1)[1].split("\n## 4.", 1)[0]
        self.assertIn("`nb_apply_review`", action_setup)
        self.assertIn("기본 Lakehouse로 연결·저장", action_setup)
        self.assertIn("지금 실행하지 않습니다", action_setup)
        supply_setup = operations.split("## 6. 공급 지연 발생시키기", 1)[1].split("\n## 7.", 1)[0]
        self.assertIn("`03_supply_change`", supply_setup)
        self.assertLess(supply_setup.index("기본 Lakehouse로 연결·저장"), supply_setup.index("**Connect**"))
        admin = (ROOT / "admin" / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("각 Notebook 기본 연결", admin)
        extension = (ROOT / "admin" / "extended-model.md").read_text(encoding="utf-8")
        self.assertNotIn("Notebook 5개에 기본 연결", extension)

    def test_notebook_guides_distinguish_estimated_code_time_outputs_and_session_startup(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertIn("| 예상 코드 실행 시간 | 예상 출력 |", scenario)
        self.assertIn("세션 연결 완료 후 코드 실행 기준", scenario)
        self.assertIn("예상 코드 실행 시간은 세션 연결 완료 후 코드 실행 기준이며, 환경에 따라 달라집니다.", scenario)
        self.assertNotIn("2분 16초", scenario)
        self.assertNotIn("제공된 실행 화면", scenario)
        self.assertIn("**예상 출력 — 발주 확인:**", scenario)
        self.assertIn("**1행**", scenario)
        for lesson in ("00-scenario.md", "01-ontology.md", "02-graph.md", "03-data-agent.md",
                       "04-operations-agent.md", "05-approval.md", "06-serving-db.md"):
            with self.subTest(lesson=lesson):
                text = (ROOT / "docs" / lesson).read_text(encoding="utf-8")
                self.assertIn("**예상 코드 실행 시간:**", text)
                self.assertIn("세션 준비 제외", text)
                self.assertIn("예상 출력", text)
                self.assertNotIn("실측 전 리허설용 예상", text)
        for lesson in ("01-ontology.md", "02-graph.md", "03-data-agent.md"):
            self.assertIn("ops.material_impact가 아직 없습니다",
                          (ROOT / "docs" / lesson).read_text(encoding="utf-8"))
        approval = (ROOT / "docs" / "05-approval.md").read_text(encoding="utf-8")
        self.assertIn("직접 **Connect**나 **Run all**을 누르지 않고", approval)
        serving = (ROOT / "docs" / "06-serving-db.md").read_text(encoding="utf-8")
        self.assertIn("**Notebook 예상 출력:**", serving)
        self.assertIn("**SQL 실행 후 예상 결과:**", serving)

    def test_admin_imports_notebooks_after_workspace_only_provisioning(self):
        admin = (ROOT / "admin" / "README.md").read_text(encoding="utf-8")
        self.assertIn("기본 실행은 작업 영역 생성·용량 지정·참가자 접근 권한만 준비", admin)
        self.assertIn("Notebook 5개만 준비된 상태", admin)
        self.assertIn("**Import → Notebook**", admin)
        self.assertIn("Notebook을 실행하거나 Lakehouse를 사전 생성하지 않습니다", admin)
        self.assertIn("기본 스크립트는 실습 항목을 만들거나 변경하지 않으며", admin)
        self.assertIn("기본 재실행은 CSV·Notebook·기존 항목·`gold`·`ops` 상태를 변경하지 않습니다", admin)
        self.assertIn("**`--prefill-items`와 함께 사용해야 하며**", admin)
        self.assertIn("별도 리허설 작업 영역", admin)
        self.assertNotIn("--role Member", admin)


class DataAgentQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.answers, cls.queries, cls.questions, cls.da_queries = {}, [], {}, {}
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.execute("ATTACH DATABASE ':memory:' AS gold")
            sql_types = {"double": "REAL", "bigint": "INTEGER", "boolean": "INTEGER"}
            for table, schema in Data().tables().items():
                columns = ", ".join(f'"{c}" {sql_types.get(t, "TEXT")}' for c, t in schema.items())
                db.execute(f'CREATE TABLE gold."{table}" ({columns})')
                values = [[None if not row[c] else (int(row[c] == "true") if t == "boolean" else row[c])
                           for c, t in schema.items()] for row in rows(table)]
                db.executemany(f'INSERT INTO gold."{table}" VALUES ({",".join("?" for _ in schema)})', values)
            db.create_function("to_date", 1, lambda value: date.fromisoformat(value).isoformat())
            db.create_function("date_sub", 2,
                               lambda value, days: (date.fromisoformat(value) - timedelta(days=days)).isoformat())
            db.create_function("date_add", 2,
                               lambda value, days: (date.fromisoformat(value) + timedelta(days=days)).isoformat())
            db.create_function("datediff", 2,
                               lambda first, second: (date.fromisoformat(first) - date.fromisoformat(second)).days)

            def capture(title, sql, question=None):
                if title.startswith("DA"):
                    if not cls.da_queries:
                        # Q3 uses the full Notebook dataset; DA questions use only the exposed sources.
                        db.execute("DROP TABLE gold.material_alternative")
                    cls.da_queries[title.split()[0]] = sql
                cls.queries.append(sql)
                cls.answers[title.split()[0]] = [dict(row) for row in db.execute(sql)]
                if question is not None:
                    cls.questions[title.split()[0]] = question

            source = (ROOT / "notebooks" / "src" / "02_answers.py").read_text(encoding="utf-8")
            # Execute the real query expressions with SQLite date equivalents, not the Fabric display wrapper.
            nodes = [n for n in ast.parse(source).body if not (isinstance(n, ast.FunctionDef) and n.name == "q")]
            namespace = {"q": capture, "spark": SimpleNamespace(catalog=SimpleNamespace(tableExists=lambda _: False))}
            with redirect_stdout(io.StringIO()):
                exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
            cls.qc_comparison = {
                days: {row["target_id"]: dict(row)
                       for row in db.execute(namespace["schedule_sql"]("2026-11-20", days))}
                for days in (7, 14)
            }
            cls.recorded_eta = db.execute(
                "SELECT eta FROM gold.purchase_order WHERE po_id = 'PO-5501'").fetchone()[0]

    def test_documented_output_counts_match_executed_reference_queries(self):
        for lesson, questions in (
            ("02-graph.md", ("Q1", "Q2", "Q3", "Q4", "Q5")),
            ("03-data-agent.md", tuple(f"DA{i:02}" for i in range(1, 8))),
        ):
            text = (ROOT / "docs" / lesson).read_text(encoding="utf-8")
            for question in questions:
                with self.subTest(lesson=lesson, question=question):
                    if lesson == "02-graph.md":
                        section = re.search(rf"^#### Notebook {question}\..*?(?=^####|^## |\Z)",
                                            text, re.M | re.S)
                        self.assertIsNotNone(section)
                        row = re.search(r"\*\*(\d+)행\*\*", section.group())
                    else:
                        row = re.search(rf"^\| {question} [^|]+\| (\d+)행", text, re.M)
                    self.assertIsNotNone(row)
                    self.assertEqual(int(row.group(1)), len(self.answers[question]))

    def test_comparison_retains_excluded_versions_and_candidates(self):
        versions = self.answers["DA01"]
        self.assertEqual(len(versions), 4)
        self.assertEqual({r["version_id"] for r in versions if r["is_active"]},
                         {"FV-CRM-01-03", "FV-TON-02-01", "FV-AMP-03-02"})
        alternatives = {r["alt_material_code"]: r for r in self.answers["Q3"]}
        self.assertEqual(set(alternatives), {"RM-HA-210", "RM-HA-305"})
        self.assertEqual((alternatives["RM-HA-210"]["approval_status"], alternatives["RM-HA-210"]["cn_registration"]),
                         ("승인", "필요"))
        self.assertEqual((alternatives["RM-HA-305"]["approval_status"], alternatives["RM-HA-305"]["cn_registration"]),
                         ("검토중", "완료"))

    def test_boundary_distinguishes_on_time_from_one_day_late(self):
        boundary = self.answers["DA02"]
        self.assertEqual([(r["eta"], r["need_date"], r["slack_days"], r["is_impacted"]) for r in boundary],
                         [("2026-11-13", "2026-11-13", 0, 0), ("2026-11-14", "2026-11-13", -1, 1)])

    def test_named_material_comparison_separates_schedule_cn_and_approval(self):
        comparison = {r["material_code"]: r for r in self.answers["DA03"]}
        self.assertEqual(set(comparison), {"RM-HA-210", "RM-HA-305"})
        self.assertEqual({key: (r["assumed_eta"], r["slack_days"], r["cn_registration"],
                               r["schedule_ok"], r["cn_ok"], r["schedule_cn_ok"])
                          for key, r in comparison.items()},
                         {"RM-HA-210": ("2026-11-12", 13, "필요", 1, 0, 0),
                          "RM-HA-305": ("2026-12-14", -19, "완료", 0, 1, 0)})
        self.assertTrue(all((r["target_id"], r["product_id"], r["market"], r["scheduled_date"],
                             r["qc_lead_days"], r["need_date"]) ==
                            ("PP-1102", "P-102", "CN", "2026-12-02", 7, "2026-11-25")
                            for r in comparison.values()))
        self.assertIn("최종 발주일", self.questions["DA07"])

    def test_documented_material_condition_flags_match_query_output(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        flags = lesson.split("<summary>DA03의 조건 판정 열 읽기</summary>", 1)[1].split("</details>", 1)[0]
        for row in self.answers["DA03"]:
            cells = [f'`{row["material_code"]}`'] + [
                f'`{str(bool(row[column])).lower()}`'
                for column in ("schedule_ok", "cn_ok", "schedule_cn_ok")
            ]
            self.assertIn("| " + " | ".join(cells) + " |", flags)
        self.assertIn("schedule_cn_ok = schedule_ok AND cn_ok", flags)
        self.assertIn("모든 판정 열이 `false`여야 하는 것이 아닙니다", flags)
        self.assertIn("all_ok = approval_ok AND schedule_ok AND cn_ok", flags)
        self.assertIn("승인 상태를 조회하지 않고", flags)
        self.assertIn("판정 범위를 구분", flags)

    def test_all_agent_queries_work_without_alternative_mapping_table(self):
        exposed_tables = {"dev_project", "formula_line", "formula_version", "ingredient", "product",
                          "production_plan", "purchase_order", "raw_material", "stability_test", "supplier"}
        self.assertEqual(list(self.da_queries), [f"DA{i:02}" for i in range(1, 8)])
        for question, sql in self.da_queries.items():
            with self.subTest(question=question):
                self.assertNotIn("material_alternative", sql)
                self.assertNotIn("approval_status", sql)
                self.assertLessEqual(set(re.findall(r"\bgold\.(\w+)", sql)), exposed_tables)

    def test_formula_scope_uses_active_flag_not_status(self):
        versions = {r["version_id"]: r for r in self.answers["DA01"]}
        self.assertEqual((versions["FV-CRM-01-02"]["impact_scope"], versions["FV-CRM-01-02"]["scope_reason"]),
                         ("제외", "비활성 처방"))
        self.assertTrue(all(r["impact_scope"] == "포함" and r["scope_reason"] == "활성 처방"
                            for r in versions.values() if r["is_active"]))
        toner = versions["FV-TON-02-01"]
        self.assertEqual((toner["status"], toner["is_active"], toner["impact_scope"]), ("개발중", 1, "포함"))

    def test_other_material_uses_and_actual_eta_match_the_business_question(self):
        source = (ROOT / "notebooks" / "src" / "02_answers.py").read_text(encoding="utf-8")
        self.assertNotIn("공급사 경로", source)
        self.assertIn('q("DA04 다른 원료 사용처·발주 ETA"', source)
        self.assertIn("실제 발주 ETA와 구분", self.questions["DA04"])
        supplier = self.answers["DA04"]
        self.assertEqual([r["product_id"] for r in supplier], ["P-101", "P-102", "P-301"])
        self.assertEqual({r["version_id"] for r in supplier}, {"FV-CRM-01-03", "FV-AMP-03-02"})
        self.assertTrue(all((r["supplier_id"], r["material_code"], r["po_id"], r["recorded_eta"]) ==
                            ("SUP-02", "RM-PHE-002", "PO-5505", "2026-11-10") for r in supplier))
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        optional = lesson.split("## 5. 선택 실습", 1)[1]
        for row in supplier:
            self.assertIn(f'| `{row["material_code"]}` | `{row["version_id"]}` | `{row["product_id"]}` |',
                          optional)
        self.assertEqual({(row["material_code"], row["version_id"]) for row in self.answers["Q4"]},
                         {("RM-PHE-002", "FV-CRM-01-03"), ("RM-PHE-002", "FV-AMP-03-02")})

    def test_what_if_changes_only_the_specified_date_or_qc(self):
        dates = {r["target_id"]: (r["before_slack"], r["after_slack"], r["after_impact"])
                 for r in self.answers["DA05"]}
        self.assertEqual(dates, {"PP-1101": (8, -27, 1), "PP-1102": (15, -20, 1),
                                "PP-1103": (64, 29, 0), "ST-0711": (3, -32, 1)})
        self.assertEqual({r["target_id"] for r in self.answers["DA05"] if r["newly_impacted"]},
                         {"PP-1101", "PP-1102", "ST-0711"})
        qc7, qc14 = self.qc_comparison[7], self.qc_comparison[14]
        self.assertTrue(all(r["eta"] == "2026-11-20" for r in [*qc7.values(), *qc14.values()]))
        self.assertEqual({key: (qc7[key]["slack_days"], qc14[key]["slack_days"]) for key in qc7},
                         {"PP-1101": (-2, -9), "PP-1102": (5, -2), "PP-1103": (54, 47), "ST-0711": (-7, -14)})
        self.assertEqual({key for key in qc7 if not qc7[key]["is_impacted"] and qc14[key]["is_impacted"]},
                         {"PP-1102"})
        for key in qc7:
            self.assertEqual((date.fromisoformat(qc7[key]["need_date"]) -
                              date.fromisoformat(qc14[key]["need_date"])).days, 7)

    def test_production_and_test_schedules_both_subtract_qc_exactly_once(self):
        for days, comparison in self.qc_comparison.items():
            for row in comparison.values():
                with self.subTest(qc=days, target=row["target_id"]):
                    self.assertEqual(row["qc_lead_days"], days)
                    self.assertEqual((date.fromisoformat(row["scheduled_date"]) -
                                      date.fromisoformat(row["need_date"])).days, days)
                    self.assertEqual((date.fromisoformat(row["need_date"]) -
                                      date.fromisoformat(row["eta"])).days, row["slack_days"])
        for row in self.answers["DA05"]:
            self.assertEqual(row["qc_lead_days"], 7)
            self.assertEqual((date.fromisoformat(row["scheduled_date"]) -
                              date.fromisoformat(row["need_date"])).days, 7)

    def test_integration_preserves_market_unknowns_and_records_review_limits(self):
        integrated = {r["target_id"]: r for r in self.answers["DA06"]}
        self.assertEqual(set(integrated), {"PP-1101", "PP-1102", "ST-0711"})
        self.assertEqual({k: (r["owner_id"], r["market"], r["slack_days"]) for k, r in integrated.items()},
                         {"PP-1101": ("P-101", "KR", -27), "PP-1102": ("P-102", "CN", -20),
                          "ST-0711": ("DP-2026-07", None, -32)})
        self.assertEqual({k: r["planned_qty_ea"] for k, r in integrated.items()},
                         {"PP-1101": 30000, "PP-1102": 20000, "ST-0711": None})
        self.assertTrue(all((r["po_id"], r["supplier_id"]) ==
                            ("PO-5501", "SUP-02") for r in integrated.values()))
        self.assertTrue(all(r["recorded_eta"] == "2026-11-10" and r["assumed_eta"] == "2026-12-15"
                            for r in integrated.values()))
        self.assertEqual(integrated["PP-1102"]["review_note"], "생산 일정·원료 확보 검토 필요")
        self.assertEqual(integrated["ST-0711"]["review_note"], "시험 일정·원료 확보 검토 필요")
        self.assertTrue(all("condition_note" not in r and "alt_material_code" not in r for r in integrated.values()))

    def test_order_deadlines_use_source_lead_time_and_rank_without_approving_substitution(self):
        deadlines = self.answers["DA07"]
        self.assertEqual([(r["review_priority"], r["target_id"], r["need_date"],
                           r["latest_order_date"], r["days_remaining"]) for r in deadlines],
                         [(1, "ST-0711", "2026-11-13", "2026-11-03", 1),
                          (2, "PP-1101", "2026-11-18", "2026-11-08", 6),
                          (3, "PP-1102", "2026-11-25", "2026-11-15", 13)])
        alternative = next(r for r in rows("raw_material") if r["material_code"] == "RM-HA-210")
        for row in deadlines:
            self.assertEqual(row["comparison_material_code"], alternative["material_code"])
            self.assertEqual(row["lead_time_days"], int(alternative["lead_time_days"]))
            self.assertEqual(row["cn_registration"], alternative["cn_registration"])
            self.assertEqual(row["as_of_date"], "2026-11-02")
            self.assertEqual(row["qc_lead_days"], 7)
            self.assertEqual((date.fromisoformat(row["scheduled_date"]) -
                              date.fromisoformat(row["need_date"])).days, 7)
            self.assertEqual((date.fromisoformat(row["need_date"]) -
                              date.fromisoformat(row["latest_order_date"])).days, row["lead_time_days"])
            self.assertEqual((date.fromisoformat(row["latest_order_date"]) -
                              date.fromisoformat(row["as_of_date"])).days, row["days_remaining"])
            self.assertIn("대체 사용 승인·공정 검증 별도", row["review_note"])
            self.assertNotIn("approval_status", row)
        self.assertIsNone(deadlines[0]["market"])
        self.assertEqual((deadlines[2]["owner_id"], deadlines[2]["market"]), ("P-102", "CN"))
        self.assertIn("CN 등록 검토 필요", deadlines[2]["review_note"])

    def test_executed_questions_match_guide_in_consecutive_order(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        questions = dict(re.findall(r"^\| (DA\d{2}) \| [^|]+ \| `([^`]+)` \| [^|\n]+ \|$", lesson, re.M))
        self.assertEqual(list(self.questions), [f"DA{i:02}" for i in range(1, 8)])
        self.assertEqual(self.questions, questions)

    def test_inline_expected_answers_match_reference_query_facts(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        expected = dict(re.findall(r"^\| (DA\d{2}) \| [^|]+ \| `[^`]+` \| ([^|\n]+) \|$", lesson, re.M))
        self.assertEqual(list(expected), [f"DA{i:02}" for i in range(1, 8)])
        for row in self.answers["DA01"]:
            self.assertIn(row["version_id"], expected["DA01"])
        for row in self.answers["DA02"]:
            self.assertIn(row["eta"][5:], expected["DA02"])
            self.assertIn(f'{row["slack_days"]}일', expected["DA02"])
        for row in self.answers["DA03"]:
            for column in ("material_code", "cn_registration"):
                self.assertIn(row[column], expected["DA03"])
            self.assertIn(row["assumed_eta"][5:], expected["DA03"])
            self.assertIn(f'{row["slack_days"]}일', expected["DA03"])
        for row in self.answers["DA04"]:
            for column in ("supplier_id", "material_code", "version_id", "product_id", "po_id"):
                self.assertIn(row[column], expected["DA04"])
            self.assertIn(row["recorded_eta"][5:], expected["DA04"])
        for row in self.answers["DA05"]:
            self.assertIn(row["target_id"], expected["DA05"])
            self.assertIn(row["need_date"][5:], expected["DA05"])
            self.assertIn(f'{row["before_slack"]} → {row["after_slack"]}일', expected["DA05"])
        for row in self.answers["DA06"]:
            for column in ("target_id", "owner_id", "po_id", "supplier_id"):
                self.assertIn(row[column], expected["DA06"])
            self.assertIn(f'{row["slack_days"]}일', expected["DA06"])
        for row in self.answers["DA07"]:
            self.assertIn(row["target_id"], expected["DA07"])
            self.assertIn(row["need_date"][5:], expected["DA07"])
            self.assertIn(row["latest_order_date"][5:], expected["DA07"])
            self.assertIn(f'{row["days_remaining"]}일', expected["DA07"])
        self.assertIn("CN 등록 검토 필요", expected["DA07"])
        self.assertIn("대체 사용 승인·공정 검증 완료를 뜻하지 않음", expected["DA07"])

    def test_reference_queries_are_read_only_and_do_not_need_ops(self):
        self.assertEqual(self.recorded_eta, "2026-11-10")
        self.assertTrue(all(re.match(r"\s*(SELECT|WITH)\b", query) for query in self.queries))
        self.assertEqual(len(self.queries), 12)


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
        # Static contracts only; live engine validation requires Lesson 06 in SQL database.
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

    def test_prepare_profile_selection_requires_an_explicit_boolean(self):
        source = (ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8")
        helper = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "select_tables")
        namespace = {"TABLES": Data().tables(), "EXTENDED_TABLES": Data().tables("EXTENDED_TABLES")}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), source, "exec"), namespace)
        select = namespace["select_tables"]
        self.assertEqual(set(select(False)), set(namespace["TABLES"]))
        self.assertEqual(set(select(True)), set(self.schemas))
        for invalid in ("false", "true", 0, 1, None, set()):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                select(invalid)

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
        self.assertNotIn("upload", provision)
        self.assertNotIn("ONELAKE", provision)
        parts = provision["definition_parts"](ROOT / "fabric" / "ont_cos_extended",
                                               {"{{WORKSPACE_ID}}": "test-workspace", "{{LAKEHOUSE_ID}}": "test-lakehouse"})
        self.assertTrue(parts)
        for part in parts:
            decoded = base64.b64decode(part["payload"]).decode()
            self.assertNotIn("{{", decoded)
            json.loads(decoded)

    def test_provision_embeds_selected_profile_without_file_uploads_and_keeps_existing_core(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        for reference, extended, existing, run_prepare in product((False, True), repeat=4):
            with self.subTest(reference=reference, extended=extended, existing=existing, run_prepare=run_prepare):
                items = [{"type": "Lakehouse", "displayName": "lh_cos", "id": "test-lakehouse"}]
                if existing:
                    items += [{"type": "Ontology", "displayName": "ont_cos", "id": "existing-core"},
                              {"type": "Eventhouse", "displayName": "eh_cos", "id": "existing-eventhouse"},
                              {"type": "SQLDatabase", "displayName": "sqldb_cos", "id": "existing-sql"}]
                fab = SimpleNamespace(
                    dry_run=False,
                    get_all=Mock(side_effect=[[{"displayName": "cos-p001", "id": "test-workspace"}], items]),
                    call=Mock(return_value=(201, {}, b"")),
                    change=Mock(return_value=(200, {"id": "test-item"})),
                    run_notebook=Mock(),
                )
                args = SimpleNamespace(prefix="cos-", capacity="test-capacity", prefill_items=True, reference_ontology=reference,
                                       extended_ontology=extended, update_notebooks=False, run_prepare=run_prepare)
                output = io.StringIO()
                with redirect_stdout(output):
                    provision["provision"](fab, "p001", args, {})
                fab.call.assert_not_called()
                preparation = next(c.args[3] for c in fab.change.call_args_list
                                   if c.args[0] == "import notebook 01_prepare_data")
                nb = json.loads(base64.b64decode(preparation["definition"]["parts"][0]["payload"]))
                params = next(c for c in nb["cells"] if "parameters" in c["metadata"].get("tags", []))
                values = {}
                exec("".join(params["source"]), values)
                self.assertIs(values["include_extended"], extended)
                self.assertIs(values["reset_ops"], False)
                self.assertIn("SCENARIO_DATA", json.dumps(nb))
                if run_prepare:
                    fab.run_notebook.assert_called_once_with("test-workspace", "test-item", "run 01_prepare_data")
                else:
                    fab.run_notebook.assert_not_called()
                    self.assertIn("leave gold-table loading to participants in chapter 00", output.getvalue())
                self.assertFalse(any("/eventhouses" in c.args[2] for c in fab.change.call_args_list))
                self.assertFalse(any(c.args[3].get("type") == "Eventhouse" for c in fab.change.call_args_list))
                self.assertFalse(any("sqldatabase" in c.args[2].lower() for c in fab.change.call_args_list))
                self.assertFalse(any(c.args[3].get("type") == "SQLDatabase" for c in fab.change.call_args_list))
                if existing:
                    self.assertIn("eh_cos exists; retained", output.getvalue())
                else:
                    self.assertIn("leave eh_cos creation to participants in chapter 04", output.getvalue())
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
            for extended, run_prepare in product((False, True), repeat=2):
                with self.subTest(reference=reference, extended=extended, run_prepare=run_prepare):
                    fab = SimpleNamespace(
                        dry_run=True, get_all=Mock(return_value=[]),
                        change=Mock(return_value=(200, {"id": "00000000-0000-0000-0000-000000000000"})),
                        call=Mock(), run_notebook=Mock(),
                    )
                    args = SimpleNamespace(prefix="cos-", capacity="test-capacity", prefill_items=True, reference_ontology=reference,
                                           extended_ontology=extended, run_prepare=run_prepare)
                    output = io.StringIO()
                    with redirect_stdout(output):
                        provision["provision"](fab, "p001", args, {})
                    text = output.getvalue()
                    self.assertNotIn("ont_cos_base", text)
                    self.assertIn("leave eh_cos creation to participants in chapter 04", text)
                    self.assertEqual("leave gold-table loading to participants in chapter 00" in text, not run_prepare)
                    self.assertEqual("run 01_prepare_data (explicit admin rehearsal/recovery)" in text, run_prepare)
                    self.assertEqual("deploy ont_cos_reference" in text, reference)
                    self.assertEqual("leave ont_cos creation to participants" in text, not reference)
                    self.assertEqual("deploy ont_cos_extended" in text, extended)
                    fab.change.assert_called_once()
                    self.assertEqual(fab.change.call_args.args[0], "create workspace")
                    fab.call.assert_not_called()
                    fab.run_notebook.assert_not_called()

    def test_provision_rejects_existing_notebook_without_explicit_update(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        for extended, run_prepare in ((True, False), (False, True)):
            with self.subTest(extended=extended, run_prepare=run_prepare):
                fab = SimpleNamespace(
                    dry_run=False,
                    get_all=Mock(side_effect=[[{"displayName": "cos-p001", "id": "test-workspace"}],
                                             [{"type": "Notebook", "displayName": "01_prepare_data", "id": "old-notebook"}]]),
                    call=Mock(), change=Mock(), run_notebook=Mock(),
                )
                args = SimpleNamespace(prefix="cos-", prefill_items=True, extended_ontology=extended,
                                       run_prepare=run_prepare, update_notebooks=False)
                with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "--update-notebooks"):
                    provision["provision"](fab, "p001", args, {})
                fab.call.assert_not_called()
                fab.change.assert_not_called()
                fab.run_notebook.assert_not_called()

    def test_provision_default_does_not_change_items_or_files(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        existing_items = [{"type": kind, "displayName": name, "id": f"existing-{kind}"} for kind, name in (
            ("Lakehouse", "lh_cos"), ("Notebook", "01_prepare_data"), ("Ontology", "ont_cos"),
            ("Eventhouse", "eh_cos"), ("SQLDatabase", "sqldb_cos"),
        )]
        for existing, items in ((False, []), (True, []), (True, existing_items)):
            with self.subTest(existing=existing, items=bool(items)):
                workspaces = [{"displayName": "cos-p001", "id": "test-workspace"}] if existing else []
                fab = SimpleNamespace(
                    dry_run=False, get_all=Mock(side_effect=[workspaces, items]),
                    change=Mock(return_value=(201, {"id": "test-workspace"})),
                    call=Mock(), run_notebook=Mock(),
                )
                args = SimpleNamespace(prefix="cos-", capacity="test-capacity", prefill_items=False)
                output = io.StringIO()
                with redirect_stdout(output):
                    provision["provision"](fab, "p001", args, {})
                self.assertEqual([c.args[0] for c in fab.get_all.call_args_list],
                                 ["/workspaces", "/workspaces/test-workspace/items"])
                self.assertEqual(fab.change.call_count, 0 if existing else 1)
                if not existing:
                    call = fab.change.call_args
                    self.assertEqual(call.args[2], "/workspaces")
                    self.assertEqual(call.args[3]["capacityId"], "test-capacity")
                fab.call.assert_not_called()
                fab.run_notebook.assert_not_called()
                self.assertIn("workspace-only: no items or source files changed", output.getvalue())
                if items:
                    self.assertIn("workspace contains 5 items; retained", output.getvalue())
                    self.assertIn("Review existing items", output.getvalue())

    def test_workspace_only_assigns_contributor_and_preserves_existing_roles(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        for role in (None, "Contributor", "Member", "Admin"):
            with self.subTest(existing_role=role):
                assignments = [] if role is None else [{"principal": {"id": "test-user"}, "role": role}]
                fab = SimpleNamespace(
                    dry_run=False,
                    get_all=Mock(side_effect=[[{"displayName": "cos-p001", "id": "test-workspace"}], assignments, []]),
                    change=Mock(), call=Mock(), run_notebook=Mock(),
                )
                args = SimpleNamespace(prefix="cos-", role="Contributor", prefill_items=False)
                with patch.object(provision["subprocess"], "check_output", return_value=b"test-user\n"), \
                        redirect_stdout(io.StringIO()):
                    provision["provision"](fab, "p001", args, {"p001": "p001@example.com"})
                if role is None:
                    fab.change.assert_called_once_with(
                        "assign Contributor to p001@example.com", "POST", "/workspaces/test-workspace/roleAssignments",
                        {"principal": {"id": "test-user", "type": "User"}, "role": "Contributor"})
                else:
                    fab.change.assert_not_called()
                fab.call.assert_not_called()
                fab.run_notebook.assert_not_called()

    def test_workspace_only_dry_run_plans_access_without_resolving_user_or_creating_items(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        fab = SimpleNamespace(
            dry_run=True, get_all=Mock(return_value=[]),
            change=Mock(return_value=(200, {"id": "00000000-0000-0000-0000-000000000000"})),
            call=Mock(), run_notebook=Mock(),
        )
        args = SimpleNamespace(prefix="cos-", capacity="test-capacity", role="Contributor", prefill_items=False)
        output = io.StringIO()
        with patch.object(provision["subprocess"], "check_output") as resolve_user, redirect_stdout(output):
            provision["provision"](fab, "p001", args, {"p001": "p001@example.com"})
        fab.get_all.assert_called_once_with("/workspaces")
        fab.change.assert_called_once()
        self.assertIn("assign Contributor to p001@example.com", output.getvalue())
        self.assertIn("import the five notebooks separately before chapter 00", output.getvalue())
        self.assertNotIn("data upload", output.getvalue())
        resolve_user.assert_not_called()
        fab.call.assert_not_called()
        fab.run_notebook.assert_not_called()

    def test_workspace_only_dry_run_does_not_treat_existing_zero_prefix_id_as_new(self):
        provision = runpy.run_path(str(ROOT / "admin" / "provision.py"))
        ws = "00001234-0000-0000-0000-000000000000"
        fab = SimpleNamespace(
            dry_run=True,
            get_all=Mock(side_effect=[[{"displayName": "cos-p001", "id": ws}],
                                     [{"type": "Lakehouse", "displayName": "lh_cos", "id": "existing-lakehouse"}]]),
            change=Mock(), call=Mock(), run_notebook=Mock(),
        )
        output = io.StringIO()
        with redirect_stdout(output):
            provision["provision"](fab, "p001", SimpleNamespace(prefix="cos-", prefill_items=False), {})
        self.assertEqual(fab.get_all.call_args.args[0], f"/workspaces/{ws}/items")
        self.assertIn("workspace contains 1 items; retained", output.getvalue())
        self.assertNotIn("leave workspace empty", output.getvalue())
        fab.change.assert_not_called()
        fab.call.assert_not_called()
        fab.run_notebook.assert_not_called()

    def test_provision_cli_defaults_to_workspace_only_and_preserves_skip_compatibility(self):
        main = runpy.run_path(str(ROOT / "admin" / "provision.py"))["main"]
        for flags, prefill, run_prepare in (
            ([], False, False), (["--skip-prepare"], False, False),
            (["--prefill-items"], True, False), (["--prefill-items", "--skip-prepare"], True, False),
            (["--prefill-items", "--run-prepare"], True, True),
        ):
            with self.subTest(flags=flags):
                provision, fabric = Mock(), Mock()
                argv = ["provision.py", "--capacity", "test-capacity", "--participants", "p001", *flags]
                with patch.dict(main.__globals__, {"provision": provision, "Fabric": fabric}), patch.object(sys, "argv", argv):
                    main()
                self.assertIs(provision.call_args.args[2].prefill_items, prefill)
                self.assertIs(provision.call_args.args[2].run_prepare, run_prepare)
                self.assertEqual(provision.call_args.args[2].role, "Contributor")
                self.assertEqual(provision.call_args.args[1], "p001")

    def test_provision_cli_requires_opt_in_before_any_prefill_mutations(self):
        main = runpy.run_path(str(ROOT / "admin" / "provision.py"))["main"]
        for flag in ("--run-prepare", "--update-notebooks", "--reference-ontology", "--extended-ontology"):
            with self.subTest(flag=flag):
                fabric, provision = Mock(), Mock()
                argv = ["provision.py", "--capacity", "test-capacity", "--participants", "p001", flag]
                error_output = io.StringIO()
                with patch.dict(main.__globals__, {"Fabric": fabric, "provision": provision}), \
                        patch.object(sys, "argv", argv), redirect_stderr(error_output):
                    with self.assertRaises(SystemExit) as error:
                        main()
                self.assertEqual(error.exception.code, 2)
                self.assertIn("require --prefill-items", error_output.getvalue())
                fabric.assert_not_called()
                provision.assert_not_called()

    def test_provision_cli_rejects_conflicting_loading_flags(self):
        main = runpy.run_path(str(ROOT / "admin" / "provision.py"))["main"]
        fabric = Mock()
        argv = ["provision.py", "--capacity", "test-capacity", "--participants", "p001", "--run-prepare", "--skip-prepare"]
        with patch.dict(main.__globals__, {"Fabric": fabric}), patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        fabric.assert_not_called()

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
