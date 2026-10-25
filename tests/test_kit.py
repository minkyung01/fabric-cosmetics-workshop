"""Offline consistency checks for the workshop kit. Run: python -m unittest discover -s tests -v"""
import ast
import csv
import json
import re
import subprocess
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = sorted((ROOT / "docs").glob("*.md"))
NOTEBOOKS = ["01_prepare_data", "02_answers", "03_supply_change", "nb_apply_review"]
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
        for md in [ROOT / "README.md", *DOCS, *sorted((ROOT / "admin").glob("*.md"))]:
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
