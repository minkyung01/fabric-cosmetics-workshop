"""Build the README SVG and editable Excalidraw diagram with official icons.

Run: python tools/build_architecture.py [--check]
"""
import base64
import hashlib
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
WIDTH, HEIGHT = 1640, 1350
CARDS = [
    ("source", "00", "Lakehouse", "lakehouse_48_item.svg", 70, 190,
     ["lh_cos · gold 11 / 확장 28", "업무 데이터 · 키 · 원본"], "#0078D4", "#CFE4FA"),
    ("ontology", "01", "Ontology", "fabric_48_color.svg", 465, 190,
     ["핵심 9개 / 확장 26개 엔터티", "키 · 속성 · Lakehouse 바인딩"], "#5C2D91", "#E8DAEF"),
    ("graph", "02", "Graph (선택)", "graph_model_instance_48_item.svg", 860, 190,
     ["ont_cos_graph_… · GQL", "다단계 경로 · 유효 버전 필터"], "#5C2D91", "#E8DAEF"),
    ("dataagent", "03", "Data Agent", "data_agent_48_item.svg", 1255, 190,
     ["da_cos · Ontology → SQL", "선택: Graph → GQL 비교"], "#5C2D91", "#E8DAEF"),
    ("signal", "04", "Notebook", "notebook_48_item.svg", 70, 510,
     ["03_supply_change", "지연 반영 · 영향 대상 계산"], "#F7630C", "#FFF4CE"),
    ("eventhouse", "04", "Eventhouse", "event_house_48_item.svg", 465, 510,
     ["eh_cos · MaterialSupplyEvent", "open → review_requested"], "#F7630C", "#FFF4CE"),
    ("operations", "04", "Operations Agent", "operations_agent_48_item.svg", 860, 510,
     ["oa_cos · Playbook", "5분 주기 감시 · 대응 제안"], "#F7630C", "#FFF4CE"),
    ("teams", "05", "Teams 승인", "teams_48x1.svg", 1255, 510,
     ["Fabric Operations Agent 채팅", "근거 확인 → Proceed / Confirm"], "#F7630C", "#FFF4CE"),
    ("approved", "05", "Notebook", "notebook_48_item.svg", 70, 870,
     ["nb_apply_review", "승인된 검토 요청 · 조치 기록"], "#107C10", "#DFF6DD"),
    ("snapshot", "05", "Lakehouse · ops", "lakehouse_48_item.svg", 465, 870,
     ["review_request · action_log", "승인 시점의 사실 / 스냅샷"], "#107C10", "#DFF6DD"),
    ("publish", "06", "Notebook", "notebook_48_item.svg", 860, 870,
     ["04_publish_serving", "게시 SQL 생성 → DB에서 실행"], "#107C10", "#DFF6DD"),
    ("sql", "06", "SQL database", "sql_database_48_item.svg", 1255, 870,
     ["sqldb_cos · serving", "팀별 조회 · 검토 착수 · 이력"], "#107C10", "#DFF6DD"),
]
LANES = [
    ("model", 130, 300, "업무 모델과 질의  |  Lesson 00 → 01 → 03  /  02 Graph는 선택",
     "Ontology 문맥으로 Lakehouse SQL 질의. 점선은 선택 Graph 경로이며 필요한 엔터티·관계만 투영합니다."),
    ("monitor", 450, 300, "변화 감지와 승인  |  Lesson 04 → 05",
     "계산과 제안을 분리합니다. Notebook이 ETA·여유일을 계산하고, 에이전트는 근거와 승인할 작업을 알립니다."),
    ("serve", 810, 300, "승인 사실에서 업무 Serving으로  |  Lesson 05 → 06",
     "게시 SQL은 참가자가 실행합니다. 재게시로 SQL의 검토 상태를 덮어쓰지 않으며, 원본으로 자동 역동기화하지 않습니다."),
]
EDGES = [
    ("source-ontology", [(380, 280), (465, 280)], False),
    ("ontology-graph", [(775, 280), (860, 280)], True),
    ("graph-dataagent", [(1170, 280), (1255, 280)], True),
    ("ontology-context", [(620, 190), (620, 178), (1410, 178), (1410, 190)], False),
    ("signal-event", [(380, 600), (465, 600)], False),
    ("event-operations", [(775, 600), (860, 600)], False),
    ("operations-teams", [(1170, 600), (1255, 600)], False),
    ("approval-action", [(1410, 690), (1410, 780), (55, 780), (55, 960), (70, 960)], False),
    ("approved-snapshot", [(380, 960), (465, 960)], False),
    ("snapshot-publish", [(775, 960), (860, 960)], False),
    ("publish-sql", [(1170, 960), (1255, 960)], False),
]


def common(element_id, kind, x, y, width, height):
    return {
        "id": element_id, "type": kind, "x": x, "y": y, "width": width, "height": height,
        "angle": 0, "strokeColor": "#64748b", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0,
        "opacity": 100, "groupIds": [], "frameId": None, "roundness": None,
        "seed": int(hashlib.sha256(element_id.encode()).hexdigest()[:7], 16),
        "version": 1, "versionNonce": 1, "isDeleted": False,
        "boundElements": None, "updated": 1, "link": None, "locked": False,
    }


def build():
    elements, files = [], {}
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        '<title id="title">Caldova cosmetics workshop — Lesson / Fabric architecture</title>',
        '<desc id="desc">Lessons 00–03 model and query business data; 04–05 detect, propose, approve '
        'and record reviews; 06 publishes to SQL database; 07 classifies data with Purview. '
        'Graph is optional; Data Agent uses ontology context to query Lakehouse SQL.</desc>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>',
        '<g font-family="Segoe UI, Malgun Gothic, sans-serif">',
    ]

    def text(key, x, y, lines, size=18, bold=False, width=1500):
        lines = [lines] if isinstance(lines, str) else lines
        item = common(key, "text", x, y, width, size * 2.5 * len(lines))
        item.update(text="\n".join(lines), originalText="\n".join(lines), fontSize=size, fontFamily=2,
                    textAlign="left", verticalAlign="top", lineHeight=1.35, containerId=None,
                    autoResize=True, strokeColor="#000000")
        elements.append(item)
        weight = ' font-weight="600"' if bold else ""
        svg.append(f'<text x="{x}" y="{y + size}" font-size="{size}" fill="#000000"{weight}>')
        for i, line in enumerate(lines):
            svg.append(f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.5}">{escape(line)}</tspan>')
        svg.append("</text>")

    def box(key, x, y, w, h, stroke="#cbd5e1", fill="transparent", container=False):
        item = common(key, "rectangle", x, y, w, h)
        item.update(strokeColor=stroke, backgroundColor="transparent" if container else fill,
                    roundness={"type": 3})
        elements.append(item)
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
                   f'stroke="{stroke}" fill="{"none" if container else fill}" />')

    def image(key, filename, x, y, size=48):
        content = (ASSETS / "icons" / filename).read_bytes()
        encoded = "data:image/svg+xml;base64," + base64.b64encode(content).decode()
        file_id = hashlib.sha256(content).hexdigest()
        files[file_id] = {"id": file_id, "mimeType": "image/svg+xml", "dataURL": encoded, "created": 1}
        item = common(key, "image", x, y, size, size)
        item.update(fileId=file_id, status="saved", scale=[1, 1], crop=None)
        elements.append(item)
        svg.append(f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
                   f'preserveAspectRatio="xMidYMid meet" xlink:href="{encoded}"/>')

    text("heading", 40, 25, "Caldova | 원료 변경 대응 에이전트", 32, True)
    for key, y, h, title, caption in LANES:
        box(key, 40, y, 1560, h, container=True)
        text(key + "-title", 70, y + 15, title, 21, True)
        text(key + "-caption", 70, y + h - 36, caption, 17)

    for key, points, dashed in EDGES:
        xs, ys = zip(*points)
        x, y = min(xs), min(ys)
        item = common(key, "arrow", x, y, max(xs) - min(xs), max(ys) - min(ys))
        item.update(points=[[px - x, py - y] for px, py in points], startBinding=None,
                    endBinding=None, startArrowhead=None, endArrowhead="arrow",
                    strokeWidth=2, strokeStyle="dashed" if dashed else "solid",
                    elbowed=False)
        elements.append(item)
        d = " ".join(f"{'M' if i == 0 else 'L'} {px} {py}" for i, (px, py) in enumerate(points))
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        svg.append(f'<path d="{d}" fill="none" stroke="#64748b" stroke-width="2" '
                   f'marker-end="url(#arrow)"{dash}/>')

    for key, lesson, title, icon, x, y, lines, stroke, fill in CARDS:
        box(key, x, y, 310, 180, stroke, fill)
        text(key + "-lesson", x + 18, y + 10, "LESSON " + lesson, 16, True, 270)
        title_x = x + 18
        if icon:
            image(key + "-icon", icon, x + 16, y + 43)
            title_x = x + 78
        text(key + "-name", title_x, y + 47, title, 22, True, 310 - (title_x - x) - 10)
        text(key + "-body", x + 18, y + 106, lines, 17, width=274)

    text("approve-label", 770, 752, "담당자 승인 후에만 실행", 18, width=350)
    box("purview", 40, 1140, 1560, 135, "#0078D4", "#CFE4FA")
    image("purview-icon", "purview_48_color.svg", 65, 1158)
    text("purview-title", 130, 1155, "LESSON 07  Microsoft Purview  |  데이터 관리 계층", 24, True)
    text("purview-body", 70, 1210,
         "lh_cos · sqldb_cos 레이블 직접 적용  /  환경 조건부: DLP 정책 팁 · Unified Catalog 검색", 20)
    text("writeback-note", 40, 1300,
         "관련 쓰기: 03_supply_change → gold ETA · ops.material_impact  /  nb_apply_review → Eventhouse 상태 이력", 18)
    svg.append("</g></svg>")
    scene = {"type": "excalidraw", "version": 2, "source": "fabric-cosmetics-workshop",
             "elements": elements, "appState": {"viewBackgroundColor": "#ffffff"}, "files": files}
    return {"architecture.svg": "\n".join(svg) + "\n",
            "architecture.excalidraw": json.dumps(scene, ensure_ascii=False, indent=2) + "\n"}


def main():
    stale = []
    for name, content in build().items():
        path = ASSETS / name
        if "--check" in sys.argv:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"built assets/{name}")
    if stale:
        sys.exit("Out of date (run python tools/build_architecture.py): " + ", ".join(stale))


if __name__ == "__main__":
    main()
