"""Prepare participant workspaces for the cosmetics R&D workshop (admin only).

By default, this creates workspace cos-pNNN on the given capacity or reuses it unchanged,
and assigns Contributor access when --users is provided. No workspace items are created or modified.
Participants create the Lakehouse and notebooks, paste code and generate data in chapter 00.

Only --prefill-items enables the optional admin rehearsal/recovery setup:
  - a schema-enabled Lakehouse lh_cos (no source-file uploads)
  - the 5 notebooks bound to lh_cos; participants run 01_prepare_data in chapter 00
  - no gold-table loading by default (--run-prepare opts in for an admin rehearsal/recovery)
  - no Eventhouse: participants create eh_cos and its default KQL database in chapter 04
  - no core ontology by default: participants create ont_cos with the Ontology agent in chapter 01
  - the completed core ontology only with --reference-ontology (recovery path)
  - include_extended = True and a separate ont_cos_extended with --extended-ontology
Existing items are reused; notebooks are only overwritten with --update-notebooks.
Use item-definition deployment only in an approved rehearsal environment, not to bypass file-upload policies.

Uses the Azure CLI login (az login [--tenant ...]); no secrets are stored.

Examples
    python admin/provision.py --capacity <capacity-id> --participants p001-p012 --users users.csv
    python admin/provision.py --capacity <capacity-id> --prefix cos-rehearsal- --participants p001 --prefill-items --reference-ontology --run-prepare
    python admin/provision.py --capacity <capacity-id> --participants p001-p003 --dry-run

SQL database sqldb_cos is created by participants in chapter 06; rehearse with Contributor.
Existing role assignments are unchanged. See admin/README.md for conflicting SQL portal permission guidance.
Before deployment, check Ontology old/new experience compatibility in admin/preview-limitations.md.
users.csv (optional): participant,upn   e.g.  p001,p001@example.com
"""
import argparse
import base64
import csv
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.fabric.microsoft.com/v1"
NOTEBOOKS = ["01_prepare_data", "02_answers", "03_supply_change", "nb_apply_review", "04_publish_serving"]
LAKEHOUSE, EVENTHOUSE, ONTOLOGY = "lh_cos", "eh_cos", "ont_cos"
_tokens = {}


def token(resource, tenant):
    if resource not in _tokens or _tokens[resource][1] < time.time() + 300:
        az = shutil.which("az") or "az"
        cmd = [az, "account", "get-access-token", "--resource", resource, "-o", "json"]
        if tenant:
            cmd += ["--tenant", tenant]
        out = json.loads(subprocess.check_output(cmd, shell=False))
        _tokens[resource] = (out["accessToken"], out.get("expires_on") or time.time() + 3000)
    return _tokens[resource][0]


class Fabric:
    def __init__(self, tenant, dry_run):
        self.tenant, self.dry_run = tenant, dry_run

    def call(self, method, url, body=None, raw=None, resource="https://api.fabric.microsoft.com", ctype="application/json"):
        url = url if url.startswith("http") else API + url
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        for _ in range(8):
            req = urllib.request.Request(url, method=method, data=data, headers={
                "Authorization": "Bearer " + token(resource, self.tenant), "Content-Type": ctype})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, dict(r.headers), r.read()
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(int(e.headers.get("Retry-After", 10)))
                    continue
                return e.code, dict(e.headers), e.read()
        raise RuntimeError(f"Throttled: {method} {url}")

    def lro(self, method, url, body=None):
        status, headers, payload = self.call(method, url, body)
        if status != 202:
            return status, json.loads(payload) if payload else {}
        location = headers.get("Location")
        while True:
            time.sleep(min(int(headers.get("Retry-After", 3) or 3), 10))
            status, headers, payload = self.call("GET", location)
            state = json.loads(payload or b"{}")
            if state.get("status") in ("Succeeded", "Failed", "Undefined", "Cancelled"):
                if state["status"] != "Succeeded":
                    return 500, state
                status, _, payload = self.call("GET", location.rstrip("/") + "/result")
                return 200, json.loads(payload) if payload else state

    def get_all(self, url):
        items = []
        while url:
            status, _, payload = self.call("GET", url)
            data = json.loads(payload)
            if status >= 300:
                raise RuntimeError(f"{status} {data}")
            items += data.get("value", [])
            url = data.get("continuationUri")
        return items

    def change(self, label, method, url, body=None):
        if self.dry_run:
            print(f"  [dry-run] {label}")
            return 200, {"id": "00000000-0000-0000-0000-000000000000"}
        status, result = self.lro(method, url, body)
        if status >= 300:
            raise RuntimeError(f"{label} failed: {status} {json.dumps(result, ensure_ascii=False)[:600]}")
        print(f"  {label}")
        return status, result

    def run_notebook(self, ws, item_id, label, timeout=1200):
        status, headers, payload = self.call("POST", f"/workspaces/{ws}/items/{item_id}/jobs/instances?jobType=RunNotebook")
        if status != 202:
            raise RuntimeError(f"{label} failed to start: {status} {payload[:300]}")
        location, start = headers.get("Location"), time.time()
        while time.time() - start < timeout:
            time.sleep(15)
            _, _, payload = self.call("GET", location)
            state = json.loads(payload or b"{}")
            if state.get("status") in ("Completed", "Failed", "Cancelled", "Deduped"):
                if state["status"] != "Completed":
                    raise RuntimeError(f"{label}: {state.get('status')} {json.dumps(state.get('failureReason'), ensure_ascii=False)}")
                print(f"  {label}: completed")
                return
        raise RuntimeError(f"{label}: timed out after {timeout}s")


def participants(spec):
    result = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            first, last = part.split("-")
            width = len(first) - 1
            result += [f"p{n:0{width}d}" for n in range(int(first[1:]), int(last[1:]) + 1)]
        elif part:
            result.append(part)
    return result


def definition_parts(folder, replacements):
    parts = []
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for key, value in replacements.items():
                text = text.replace(key, value)
            parts.append({"path": path.relative_to(folder).as_posix(),
                          "payload": base64.b64encode(text.encode("utf-8")).decode(), "payloadType": "InlineBase64"})
    return parts


def provision(fab, pid, args, users):
    name = f"{args.prefix}{pid}"
    print(f"{pid}: {name}")
    workspaces = {w["displayName"]: w["id"] for w in fab.get_all("/workspaces")}
    ws = workspaces.get(name)
    new_workspace = ws is None
    if new_workspace:
        _, created = fab.change("create workspace", "POST", "/workspaces",
                                {"displayName": name, "capacityId": args.capacity,
                                 "description": "Cosmetics R&D material-change workshop"})
        ws = created["id"]
    else:
        print("  workspace exists")
    if fab.dry_run and new_workspace:
        if pid in users:
            print(f"  [dry-run] assign {args.role} to {users[pid]}")
        if not args.prefill_items:
            print("  [dry-run] workspace-only: leave workspace empty; participants create items and load data in chapter 00")
            return
        print(f"  [dry-run] {LAKEHOUSE}, self-contained notebooks; no source-file uploads")
        if args.run_prepare:
            print("  [dry-run] run 01_prepare_data (explicit admin rehearsal/recovery)")
        else:
            print("  [dry-run] leave gold-table loading to participants in chapter 00")
        print(f"  [dry-run] leave {EVENTHOUSE} creation to participants in chapter 04; keep any existing Eventhouse")
        if args.reference_ontology:
            print(f"  [dry-run] deploy ont_cos_reference as {ONTOLOGY} if absent; keep any existing ontology")
        else:
            print(f"  [dry-run] leave {ONTOLOGY} creation to participants in chapter 01; keep any existing ontology")
        if args.extended_ontology:
            print("  [dry-run] include_extended = True (28 tables), deploy ont_cos_extended as a separate ontology")
        return

    if pid in users:
        upn = users[pid]
        az = shutil.which("az") or "az"
        oid = subprocess.check_output([az, "ad", "user", "show", "--id", upn, "--query", "id", "-o", "tsv"]).decode().strip()
        roles = fab.get_all(f"/workspaces/{ws}/roleAssignments")
        if not any(r["principal"]["id"] == oid for r in roles):
            fab.change(f"assign {args.role} to {upn}", "POST", f"/workspaces/{ws}/roleAssignments",
                       {"principal": {"id": oid, "type": "User"}, "role": args.role})
        else:
            print(f"  access for {upn} exists; role retained (requested {args.role}; review existing assignments manually)")

    items = {(i["type"], i["displayName"]): i["id"] for i in fab.get_all(f"/workspaces/{ws}/items")}
    if not args.prefill_items:
        if items:
            print(f"  workspace contains {len(items)} items; retained. Use a fresh workspace for the empty-workspace exercise.")
        print("  workspace-only: no items or source files changed; participants create items and load data in chapter 00")
        return
    if (args.extended_ontology or args.run_prepare) and ("Notebook", "01_prepare_data") in items and not args.update_notebooks:
        raise ValueError("Admin preparation/reference profiles require --update-notebooks when 01_prepare_data already exists")
    if not args.reference_ontology and ("Ontology", ONTOLOGY) in items:
        print(f"  {ONTOLOGY} exists; retained. Chapter 01 starts empty: prepare a fresh workspace for the creation exercise.")
    lh = items.get(("Lakehouse", LAKEHOUSE))
    if not lh:
        _, created = fab.change(f"create lakehouse {LAKEHOUSE} (schemas)", "POST", f"/workspaces/{ws}/lakehouses",
                                {"displayName": LAKEHOUSE, "creationPayload": {"enableSchemas": True}})
        lh = created["id"]

    notebook_ids = {}
    for nb_name in NOTEBOOKS:
        exists = ("Notebook", nb_name) in items
        if exists and not args.update_notebooks:
            notebook_ids[nb_name] = items[("Notebook", nb_name)]
            continue
        notebook = json.loads((ROOT / "notebooks" / f"{nb_name}.ipynb").read_text(encoding="utf-8"))
        if nb_name == "01_prepare_data" and args.extended_ontology:
            params = next(c for c in notebook["cells"] if "parameters" in c["metadata"].get("tags", []))
            text = "".join(params["source"])
            if text.count("include_extended = False") != 1:
                raise ValueError("01_prepare_data must define include_extended = False in its parameter cell")
            params["source"] = text.replace("include_extended = False", "include_extended = True").splitlines(keepends=True)
        notebook["metadata"]["dependencies"] = {"lakehouse": {
            "default_lakehouse": lh, "default_lakehouse_name": LAKEHOUSE, "default_lakehouse_workspace_id": ws}}
        payload = base64.b64encode(json.dumps(notebook, ensure_ascii=False).encode("utf-8")).decode()
        definition = {"format": "ipynb", "parts": [
            {"path": "notebook-content.ipynb", "payload": payload, "payloadType": "InlineBase64"}]}
        if exists:
            fab.change(f"update notebook {nb_name}", "POST",
                       f"/workspaces/{ws}/items/{items[('Notebook', nb_name)]}/updateDefinition", {"definition": definition})
            notebook_ids[nb_name] = items[("Notebook", nb_name)]
        else:
            _, created = fab.change(f"import notebook {nb_name}", "POST", f"/workspaces/{ws}/notebooks",
                                    {"displayName": nb_name, "definition": definition})
            notebook_ids[nb_name] = created["id"]

    if args.run_prepare:
        if fab.dry_run:
            print("  [dry-run] run 01_prepare_data (explicit admin rehearsal/recovery)")
        else:
            fab.run_notebook(ws, notebook_ids["01_prepare_data"], "run 01_prepare_data")
    else:
        print("  leave gold-table loading to participants in chapter 00; existing gold/ops data is not reset")

    if ("Eventhouse", EVENTHOUSE) in items:
        print(f"  {EVENTHOUSE} exists; retained. Check the database and event history before reusing it in chapter 04.")
    else:
        print(f"  leave {EVENTHOUSE} creation to participants in chapter 04")

    models = [(ONTOLOGY, "ont_cos_reference")] if args.reference_ontology else []
    if args.extended_ontology:
        models.append(("ont_cos_extended", "ont_cos_extended"))
    for display_name, folder in models:
        if ("Ontology", display_name) in items:
            print(f"  {display_name} exists; retained, ontology definition not overwritten")
            continue
        parts = definition_parts(ROOT / "fabric" / folder, {"{{WORKSPACE_ID}}": ws, "{{LAKEHOUSE_ID}}": lh})
        fab.change(f"deploy {folder} as {display_name}", "POST", f"/workspaces/{ws}/items",
                   {"displayName": display_name, "type": "Ontology", "definition": {"parts": parts}})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capacity", required=True, help="Fabric capacity ID for new workspaces (paid F SKU, not Trial)")
    parser.add_argument("--participants", required=True, help="e.g. p001-p012 or p001,p005")
    parser.add_argument("--users", help="CSV with participant,upn to grant workspace access")
    parser.add_argument("--role", default="Contributor", choices=["Admin", "Member", "Contributor"],
                        help="role for new participant assignments (default Contributor); existing assignments are unchanged")
    parser.add_argument("--prefix", default="cos-", help="workspace name prefix (default cos-)")
    parser.add_argument("--tenant", help="tenant for az get-access-token")
    parser.add_argument("--prefill-items", action="store_true",
                        help="opt in to staging Lakehouse and self-contained notebooks in an approved rehearsal environment")
    parser.add_argument("--update-notebooks", action="store_true", help="overwrite existing notebooks")
    preparation = parser.add_mutually_exclusive_group()
    preparation.add_argument("--run-prepare", dest="run_prepare", action="store_true",
                             help="opt in to running 01_prepare_data for an admin rehearsal/recovery, not the learner setup")
    preparation.add_argument("--skip-prepare", dest="run_prepare", action="store_false",
                             help="compatibility option: leaving data loading to participants is already the default")
    parser.set_defaults(run_prepare=False)
    parser.add_argument("--reference-ontology", action="store_true",
                        help="deploy the completed core ontology if absent (chapter 01 recovery; default creates no ontology)")
    parser.add_argument("--extended-ontology", action="store_true",
                        help="enable all 28 generated tables and deploy a separate 26-entity ont_cos_extended")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.prefill_items and (args.run_prepare or args.update_notebooks or args.reference_ontology or args.extended_ontology):
        parser.error("--run-prepare, --update-notebooks and ontology deployment options require --prefill-items; "
                     "the default prepares only the workspace and access")
    users = {}
    if args.users:
        with open(args.users, encoding="utf-8-sig") as f:
            users = {row["participant"].strip(): row["upn"].strip() for row in csv.DictReader(f)}
    fab = Fabric(args.tenant, args.dry_run)
    for pid in participants(args.participants):
        provision(fab, pid, args, users)


if __name__ == "__main__":
    main()
