"""Build self-contained Fabric notebooks, copy-paste guides and the participant download.

Run: python tools/build_notebooks.py          (writes notebooks, paste guides and downloads/workshop-files.zip)
     python tools/build_notebooks.py --check  (fails if any generated output is out of date)

Source format (one file per notebook):
    # %% [markdown]        markdown cell; following lines start with "# "
    # %% [parameters]      code cell tagged "parameters" (Fabric parameter cell)
    # %%                   code cell
"""
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "notebooks" / "src"
OUT = ROOT / "notebooks"
DOWNLOAD = ROOT / "downloads" / "workshop-files.zip"
PASTE = OUT / "paste"
DATA_MARKER = "# {{SCENARIO_DATA}}"

METADATA = {
    "kernel_info": {"name": "synapse_pyspark"},
    "kernelspec": {"display_name": "Synapse PySpark", "language": "Python", "name": "synapse_pyspark"},
    "language_info": {"name": "python"},
    "microsoft": {"language": "python", "language_group": "synapse_pyspark"},
}


def parse(text):
    cells, kind, lines = [], None, []

    def flush():
        if kind is None:
            return
        body = list(lines)
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        if kind == "markdown":
            body = [line[2:] if line.startswith("# ") else line.lstrip("#") for line in body]
        source = [line + "\n" for line in body]
        if source:
            source[-1] = source[-1].rstrip("\n")
        cell = {"cell_type": "markdown" if kind == "markdown" else "code", "metadata": {}, "source": source}
        if kind != "markdown":
            cell.update(execution_count=None, outputs=[])
            if kind == "parameters":
                cell["metadata"]["tags"] = ["parameters"]
        cells.append(cell)

    for line in text.splitlines():
        if line.startswith("# %%"):
            flush()
            marker = line[4:].strip()
            kind = {"[markdown]": "markdown", "[parameters]": "parameters", "": "code"}[marker]
            lines = []
        else:
            lines.append(line)
    flush()
    return cells


def build(path):
    source = path.read_text(encoding="utf-8")
    if path.stem == "01_prepare_data":
        if source.count(DATA_MARKER) != 1:
            raise ValueError("01_prepare_data must contain exactly one scenario-data marker")
        data = {csv.stem: csv.read_text(encoding="utf-8")
                for folder in (ROOT / "data", ROOT / "data" / "extended")
                for csv in sorted(folder.glob("*.csv"))}
        source = source.replace(DATA_MARKER, "SCENARIO_DATA = " + json.dumps(data, ensure_ascii=False, indent=4))
    notebook = {"cells": parse(source), "metadata": METADATA,
                "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"


def build_paste(name, content):
    cells = json.loads(content)["cells"]
    parameters = [c for c in cells if "parameters" in c["metadata"].get("tags", [])]
    if len(parameters) != 1:
        raise ValueError(f"{name}: expected exactly one parameter cell")
    params = "".join(parameters[0]["source"])
    body = "\n\n".join("".join(c["source"]) for c in cells
                       if c["cell_type"] == "code" and c not in parameters)
    return (f"# {name} — 복사할 코드\n\n"
            "[Notebook 생성·셀 설정](../../docs/00-scenario.md#4-notebook-5개-만들기와-코드-붙여넣기)\n\n"
            f"## 1. 매개변수 셀\n\n```python\n{params}\n```\n\n"
            f"## 2. 실행 코드 셀\n\n```python\n{body}\n```\n")


def build_download(notebooks):
    files = {path.relative_to(ROOT).as_posix(): path.read_bytes()
             for folder in (ROOT / "data", ROOT / "data" / "extended")
             for path in folder.glob("*.csv")}
    files.update({f"notebooks/{name}": content.encode("utf-8") for name, content in notebooks.items()})
    files.update({f"notebooks/paste/{Path(name).stem}.md":
                  build_paste(Path(name).stem, content).encode("utf-8")
                  for name, content in notebooks.items()})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def main():
    check = "--check" in sys.argv
    stale, notebooks = [], {}
    for path in sorted(SRC.glob("*.py")):
        content = build(path)
        notebooks[path.stem + ".ipynb"] = content
        targets = {OUT / (path.stem + ".ipynb"): content,
                   PASTE / (path.stem + ".md"): build_paste(path.stem, content)}
        for target, text in targets.items():
            if check:
                if not target.exists() or target.read_text(encoding="utf-8") != text:
                    stale.append(str(target.relative_to(ROOT)))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
                print(f"built {target.relative_to(ROOT)}")
    download = build_download(notebooks)
    if check:
        if not DOWNLOAD.exists() or DOWNLOAD.read_bytes() != download:
            stale.append(str(DOWNLOAD.relative_to(ROOT)))
    else:
        DOWNLOAD.parent.mkdir(parents=True, exist_ok=True)
        DOWNLOAD.write_bytes(download)
        print(f"built {DOWNLOAD.relative_to(ROOT)}")
    if stale:
        sys.exit("Out of date (run python tools/build_notebooks.py): " + ", ".join(stale))


if __name__ == "__main__":
    main()
