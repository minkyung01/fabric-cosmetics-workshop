"""Build the Fabric notebooks (.ipynb) from the readable sources in notebooks/src.

Run: python tools/build_notebooks.py          (writes notebooks/*.ipynb)
     python tools/build_notebooks.py --check  (fails if an .ipynb is out of date)

Source format (one file per notebook):
    # %% [markdown]        markdown cell; following lines start with "# "
    # %% [parameters]      code cell tagged "parameters" (Fabric parameter cell)
    # %%                   code cell
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "notebooks" / "src"
OUT = ROOT / "notebooks"

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
    notebook = {"cells": parse(path.read_text(encoding="utf-8")), "metadata": METADATA,
                "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"


def main():
    check = "--check" in sys.argv
    stale = []
    for path in sorted(SRC.glob("*.py")):
        target = OUT / (path.stem + ".ipynb")
        content = build(path)
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(target.name)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
            print(f"built {target.relative_to(ROOT)}")
    if stale:
        sys.exit("Out of date (run python tools/build_notebooks.py): " + ", ".join(stale))


if __name__ == "__main__":
    main()
