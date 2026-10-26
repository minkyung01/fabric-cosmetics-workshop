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
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = sorted((ROOT / "docs").glob("*.md"))
ALL_DOCS = sorted((ROOT / "docs").rglob("*.md"))
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

    def test_participant_download_contains_only_exact_csv_and_notebook_files(self):
        expected = {f"data/{name}.csv" for name in Data().tables()}
        expected |= {f"data/extended/{name}.csv" for name in Data().tables("EXTENDED_TABLES")}
        expected |= {f"notebooks/{name}.ipynb" for name in NOTEBOOKS}
        self.assertEqual(len(expected), 33)
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
        source = (ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8")
        nodes = [n for n in ast.parse(source).body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        spark = Mock()
        spark.catalog.tableExists.side_effect = lambda name: name == "ops.review_request"
        fs = SimpleNamespace(ls=Mock(return_value=[SimpleNamespace(name=f"{t}.csv") for t in Data().tables()]))
        namespace = {"spark": spark, "fs": fs, "F": Mock(), "display": Mock()}
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "ops.review_request"):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
        self.assertIs(namespace["reset_ops"], False)
        spark.sql.assert_not_called()
        spark.read.option.assert_not_called()

    def test_notebook_creates_tables_and_drops_ops_only_for_explicit_reset(self):
        source = (ROOT / "notebooks" / "src" / "01_prepare_data.py").read_text(encoding="utf-8")
        nodes = [n for n in ast.parse(source).body if not isinstance(n, (ast.Import, ast.ImportFrom))
                 and not (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "reset_ops" for t in n.targets))]
        tables = Data().tables()
        for reset in (False, True):
            with self.subTest(reset=reset):
                spark, raw, frame = Mock(), Mock(), Mock()
                spark.catalog.tableExists.return_value = False
                spark.read.option.return_value = spark.read
                spark.read.csv.return_value = raw
                raw.columns = {column for schema in tables.values() for column in schema}
                raw.select.return_value = frame
                frame.count.return_value = 1
                frame.write.mode.return_value = frame.write
                frame.write.option.return_value = frame.write
                frame.write.format.return_value = frame.write
                fs = SimpleNamespace(ls=Mock(return_value=[SimpleNamespace(name=f"{t}.csv") for t in tables]))
                namespace = {"spark": spark, "fs": fs, "F": Mock(), "display": Mock(), "reset_ops": reset}
                with redirect_stdout(io.StringIO()):
                    exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
                self.assertEqual([call.args[0] for call in frame.write.saveAsTable.call_args_list],
                                 [f"gold.{table}" for table in tables])
                self.assertTrue(all(call.args == ("overwrite",) for call in frame.write.mode.call_args_list))
                drops = [call.args[0] for call in spark.sql.call_args_list if call.args[0].startswith("DROP")]
                self.assertEqual(drops, [f"DROP TABLE IF EXISTS ops.{t}" for t in
                                         ("material_impact", "review_request", "action_log")] if reset else [])


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
                path = (md.parent / unquote(urlsplit(link).path)).resolve()
                self.assertTrue(path.exists(), f"{md.name}: {link}")

    def test_download_links_use_the_public_absolute_zip_url(self):
        for md in (ROOT / "README.md", ROOT / "docs" / "00-scenario.md", ROOT / "admin" / "README.md"):
            links = re.findall(r"\]\(([^)]+)\)", md.read_text(encoding="utf-8"))
            with self.subTest(document=md.relative_to(ROOT)):
                self.assertEqual([link for link in links if "workshop-files.zip" in link], [WORKSHOP_DOWNLOAD_URL])

    def test_bold_delimiters_do_not_end_in_punctuation_before_attached_words(self):
        for md in [ROOT / "README.md", *ALL_DOCS, *sorted((ROOT / "admin").glob("*.md")),
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
        self.assertIn("| Ontology | `ont_cos` | **01장에서 직접 생성** |", scenario)

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

    def test_data_agent_questions_cover_six_types_with_deferred_answers(self):
        lesson = (ROOT / "docs" / "03-data-agent.md").read_text(encoding="utf-8")
        questions = re.findall(r"^\| (DA\d{2}) \| ([^|]+) \| `([^`]+)` \|$", lesson, re.M)
        ids = [f"DA{i:02}" for i in range(1, 13)]
        self.assertEqual([q[0] for q in questions], ids)
        self.assertEqual([q[1] for q in questions],
                         [kind for kind in ("대조", "규칙", "용어", "관계", "What-if", "여러 데이터 통합") for _ in range(2)])
        for _, _, prompt in questions:
            self.assertNotRegex(prompt, r"DA\d{2}")
        answers = lesson.split("<details>", 1)[1].split("</details>", 1)[0]
        self.assertEqual(re.findall(r"^\| (DA\d{2}) \|", answers, re.M), ids)
        self.assertLess(lesson.index("| DA12 | 여러 데이터 통합 |"), lesson.index("<details>"))
        self.assertIn("핵심 11개 테이블·9개 엔터티", lesson)
        self.assertIn("Clear chat", lesson)
        self.assertIn("최초 답", lesson)
        self.assertIn("0일은 일정 기준 영향 없음", lesson)
        self.assertIn("농도·제형 환산", lesson)
        self.assertNotIn("질문 5개", lesson)

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
        self.assertIn("빈 작업 영역과 접근 권한만", readme)
        self.assertIn("**00장에서 Lakehouse `lh_cos` 생성", readme)
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## \d\. .+$", scenario, re.M), [
            "## 1. 빈 작업 영역과 권한 확인", "## 2. 실습 파일 내려받기", "## 3. Lakehouse 직접 만들기",
            "## 4. CSV 업로드와 원본 확인", "## 5. Notebook 5개 가져오기와 기본 Lakehouse 연결",
            "## 6. Notebook으로 gold 테이블 직접 만들기",
        ])
        self.assertIn(WORKSHOP_DOWNLOAD_URL, scenario)
        self.assertIn("Lakehouse schemas", scenario)
        self.assertIn("Tables → dbo", scenario)
        self.assertIn("Upload files", scenario)
        self.assertIn("**같은 `Files/workshop/data` 폴더**", scenario)
        self.assertIn("각 Notebook을 열고", scenario)
        self.assertIn("**기본 Lakehouse로 고정**(핀)", scenario)
        self.assertIn("세션을 다시 시작", scenario)
        self.assertIn("**지금은 `01_prepare_data`만 실행합니다.**", scenario)
        names = runpy.run_path(str(ROOT / "admin" / "provision.py"))["NOTEBOOKS"]
        for name in names:
            self.assertIn(f"{name}.ipynb", scenario)
        self.assertIn("reset_ops = False", scenario)
        self.assertIn("Run all", scenario)
        self.assertIn("쓰기 전에 오류로 중지", scenario)
        self.assertIn("28개 테이블", scenario)
        for table in Data().tables():
            self.assertIn(f"{table}.csv", scenario)
        ontology = (ROOT / "docs" / "01-ontology.md").read_text(encoding="utf-8")
        self.assertIn("`01_prepare_data`를 직접 실행해", ontology)
        extension = (ROOT / "docs" / "extensions" / "ontology.md").read_text(encoding="utf-8")
        self.assertIn("00장의 첫 적재에서 직접 만든", extension)

    def test_scenario_separates_local_download_folders_and_fabric_destinations(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        download = scenario.split("## 2. 실습 파일 내려받기\n", 1)[1].split("\n## 3.", 1)[0]
        self.assertIn(WORKSHOP_DOWNLOAD_URL, download)
        self.assertIn("| 내 PC 폴더 | 파일 | Fabric 위치 |", download)
        self.assertIn("| `data` | 핵심 `.csv` 11개 |", download)
        self.assertIn("| `notebooks` | `.ipynb` 5개 |", download)
        self.assertIn("작업 영역 → Import → Notebook", download)
        self.assertIn("첫 적재 전", download)
        self.assertNotIn("archive/refs/heads/main.zip", download)
        self.assertNotIn("저장소 전체", download)
        self.assertNotIn("Python·Git 설치", download)
        self.assertIn(WORKSHOP_DOWNLOAD_URL, (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_scenario_includes_actual_empty_workspace_screenshot_before_downloads(self):
        scenario = (ROOT / "docs" / "00-scenario.md").read_text(encoding="utf-8")
        image = "../assets/screenshots/00-empty-workspace.png"
        self.assertIn(f"![빈 작업 영역 화면]({image})", scenario)
        self.assertLess(scenario.index(image), scenario.index("## 2. 실습 파일 내려받기"))
        self.assertIn("`cos-p901`", scenario)
        self.assertTrue((ROOT / "assets" / "screenshots" / "00-empty-workspace.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_admin_default_is_empty_workspace_not_prestaged_items(self):
        admin = (ROOT / "admin" / "README.md").read_text(encoding="utf-8")
        self.assertIn("기본 실행은 작업 영역 생성·용량 지정·참가자 접근 권한만 준비", admin)
        self.assertIn("참가자용 작업 영역은 빈 상태로 남깁니다", admin)
        self.assertIn("기본 재실행은 CSV·Notebook·기존 항목·`gold`·`ops` 상태를 변경하지 않습니다", admin)
        self.assertIn("**`--prefill-items`와 함께 사용해야 하며**", admin)
        self.assertIn("별도 리허설 작업 영역", admin)
        self.assertNotIn("--role Member", admin)


class DataAgentQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.answers, cls.queries = {}, []
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

            def capture(title, sql):
                cls.queries.append(sql)
                cls.answers[title.split()[0]] = [dict(row) for row in db.execute(sql)]

            source = (ROOT / "notebooks" / "src" / "02_answers.py").read_text(encoding="utf-8")
            # Execute the real query expressions with SQLite date equivalents, not the Fabric display wrapper.
            nodes = [n for n in ast.parse(source).body if not (isinstance(n, ast.FunctionDef) and n.name == "q")]
            namespace = {"q": capture, "spark": SimpleNamespace(catalog=SimpleNamespace(tableExists=lambda _: False))}
            with redirect_stdout(io.StringIO()):
                exec(compile(ast.Module(body=nodes, type_ignores=[]), source, "exec"), namespace)
            cls.recorded_eta = db.execute(
                "SELECT eta FROM gold.purchase_order WHERE po_id = 'PO-5501'").fetchone()[0]

    def test_comparison_retains_excluded_versions_and_candidates(self):
        versions = self.answers["Q1"]
        self.assertEqual(len(versions), 4)
        self.assertEqual({r["version_id"] for r in versions if r["is_active"]},
                         {"FV-CRM-01-03", "FV-TON-02-01", "FV-AMP-03-02"})
        alternatives = {r["alt_material_code"]: r for r in self.answers["Q3"]}
        self.assertEqual(set(alternatives), {"RM-HA-210", "RM-HA-305"})
        self.assertEqual((alternatives["RM-HA-210"]["approval_status"], alternatives["RM-HA-210"]["cn_registration"]),
                         ("승인", "필요"))
        self.assertEqual((alternatives["RM-HA-305"]["approval_status"], alternatives["RM-HA-305"]["cn_registration"]),
                         ("검토중", "완료"))

    def test_boundary_and_three_candidate_conditions(self):
        boundary = self.answers["DA03"]
        self.assertEqual([(r["eta"], r["need_date"], r["slack_days"], r["is_impacted"]) for r in boundary],
                         [("2026-11-13", "2026-11-13", 0, 0), ("2026-11-14", "2026-11-13", -1, 1)])
        candidates = self.answers["DA04"]
        self.assertEqual([r["alt_material_code"] for r in candidates], ["RM-HA-210", "RM-HA-305"])
        self.assertTrue(all(r["need_date"] == "2026-11-25" for r in candidates))
        self.assertEqual([(r["assumed_eta"], r["slack_days"], r["approval_ok"], r["schedule_ok"], r["cn_ok"], r["all_ok"])
                          for r in candidates],
                         [("2026-11-12", 13, 1, 1, 0, 0), ("2026-12-14", -19, 0, 0, 1, 0)])

    def test_terms_distinguish_one_ingredient_and_three_materials(self):
        materials = self.answers["DA05"]
        self.assertEqual({r["ingredient_id"] for r in materials}, {"ING-HA"})
        self.assertEqual({r["material_code"]: r["supplier_id"] for r in materials},
                         {"RM-HA-120": "SUP-02", "RM-HA-210": "SUP-01", "RM-HA-305": "SUP-04"})
        self.assertEqual({r["inci_name"] for r in materials}, {"Sodium Hyaluronate"})
        toner = next(r for r in self.answers["Q1"] if r["version_id"] == "FV-TON-02-01")
        self.assertEqual((toner["status"], toner["is_active"]), ("개발중", 1))

    def test_relationship_paths_and_supplier_fanout(self):
        paths = {r["target_id"]: r for r in self.answers["DA07"]}
        self.assertEqual(set(paths), {"PP-1102", "ST-0711"})
        self.assertEqual((paths["PP-1102"]["product_id"], paths["PP-1102"]["version_id"]), ("P-102", "FV-CRM-01-03"))
        self.assertEqual((paths["ST-0711"]["project_id"], paths["ST-0711"]["version_id"]), ("DP-2026-07", "FV-TON-02-01"))
        self.assertTrue(all(r["material_code"] == "RM-HA-120" for r in paths.values()))
        supplier = self.answers["DA08"]
        self.assertEqual([r["product_id"] for r in supplier], ["P-101", "P-102", "P-301"])
        self.assertEqual({r["version_id"] for r in supplier}, {"FV-CRM-01-03", "FV-AMP-03-02"})
        self.assertTrue(all((r["supplier_id"], r["material_code"], r["po_id"], r["recorded_eta"]) ==
                            ("SUP-02", "RM-PHE-002", "PO-5505", "2026-11-10") for r in supplier))

    def test_what_if_changes_only_the_specified_date_or_qc(self):
        dates = {r["target_id"]: (r["before_slack"], r["after_slack"], r["after_impact"])
                 for r in self.answers["DA09"]}
        self.assertEqual(dates, {"PP-1101": (8, -27, 1), "PP-1102": (15, -20, 1),
                                "PP-1103": (64, 29, 0), "ST-0711": (3, -32, 1)})
        qc = {r["target_id"]: r for r in self.answers["DA10"]}
        self.assertTrue(all(r["eta"] == "2026-11-20" for r in qc.values()))
        self.assertEqual({k: (r["slack_qc7"], r["slack_qc14"]) for k, r in qc.items()},
                         {"PP-1101": (-2, -9), "PP-1102": (5, -2), "PP-1103": (54, 47), "ST-0711": (-7, -14)})
        self.assertEqual({k for k, r in qc.items() if not r["impact_qc7"] and r["impact_qc14"]}, {"PP-1102"})
        for row in qc.values():
            self.assertEqual((date.fromisoformat(row["need_qc7"]) - date.fromisoformat(row["need_qc14"])).days, 7)

    def test_integration_preserves_market_unknowns_and_records_review_limits(self):
        integrated = {r["target_id"]: r for r in self.answers["DA11"]}
        self.assertEqual(set(integrated), {"PP-1101", "PP-1102", "ST-0711"})
        self.assertEqual({k: (r["owner_id"], r["market"], r["slack_days"]) for k, r in integrated.items()},
                         {"PP-1101": ("P-101", "KR", -27), "PP-1102": ("P-102", "CN", -20),
                          "ST-0711": ("DP-2026-07", None, -32)})
        self.assertEqual({k: r["planned_qty_ea"] for k, r in integrated.items()},
                         {"PP-1101": 30000, "PP-1102": 20000, "ST-0711": None})
        self.assertTrue(all((r["po_id"], r["supplier_id"], r["alt_material_code"]) ==
                            ("PO-5501", "SUP-02", "RM-HA-210") for r in integrated.values()))
        self.assertTrue(all(r["recorded_eta"] == "2026-11-10" and r["assumed_eta"] == "2026-12-15"
                            for r in integrated.values()))
        self.assertEqual(integrated["PP-1102"]["review_note"], "CN 등록 검토 필요")
        self.assertTrue(all(r["condition_note"] == "파우더 용해 공정 추가 필요" for r in integrated.values()))

    def test_reference_queries_are_read_only_and_do_not_need_ops(self):
        self.assertEqual(self.recorded_eta, "2026-11-10")
        self.assertTrue(all(re.match(r"\s*(SELECT|WITH)\b", query) for query in self.queries))
        self.assertEqual(len(self.queries), 13)


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
                uploads = [c.args[1] for c in fab.call.call_args_list if "?resource=file" in c.args[1]]
                self.assertEqual(len(uploads), 28 if extended else 11)
                self.assertTrue(all("/Files/workshop/data/" in url for url in uploads))
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
                    self.assertIn("Use a fresh workspace", output.getvalue())

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
        self.assertIn("workspace-only: leave workspace empty", output.getvalue())
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
