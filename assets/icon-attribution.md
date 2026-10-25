# 아키텍처 아이콘 출처와 사용 조건

[목차](../README.md)

그림은 [Microsoft Fabric 공식 아이콘 안내](https://learn.microsoft.com/en-us/fabric/fundamentals/icons)에서 연결한 [microsoft/fabric-samples의 Icons.zip](https://github.com/microsoft/fabric-samples/blob/main/docs-samples/Icons.zip)에서 가져온 **v6.1.0** SVG를 사용합니다.

| 그림의 기능 | 파일 (`icons/`) |
|---|---|
| Lakehouse | `lakehouse_48_item.svg` |
| Ontology의 Fabric 플랫폼 표시 | `fabric_48_color.svg` |
| Graph model | `graph_model_instance_48_item.svg` |
| Data Agent | `data_agent_48_item.svg` |
| Notebook | `notebook_48_item.svg` |
| Eventhouse | `event_house_48_item.svg` |
| Operations Agent | `operations_agent_48_item.svg` |
| SQL database | `sql_database_48_item.svg` |
| Microsoft Purview | `purview_48_color.svg` |

공식 컬렉션의 아이콘을 원본 그대로 포함하고 동일 비율로 표시했습니다. 자르기·회전·뒤집기·색상 변경을 하지 않았습니다. 다운로드한 컬렉션에 Ontology 전용 아이콘이 없어 해당 카드에는 **Fabric 플랫폼 아이콘**을 사용했으며, Ontology 전용 공식 아이콘이라고 주장하지 않습니다. Teams는 텍스트로 표시합니다.

Microsoft는 아키텍처 다이어그램·교육 자료·문서에서의 아이콘 사용을 허용합니다. 상세 조건과 Do/Don't는 공식 안내를 확인합니다. 원본 패키지의 [LICENSE](icons/LICENSE)(Copyright © 2025 Microsoft Corporation)를 함께 보관합니다. 아이콘은 Microsoft 제품·항목을 나타내는 용도로만 사용하며 이 워크숍 자체의 로고로 사용하지 않습니다.

`tools/build_architecture.py`가 README용 `architecture.svg`와 아이콘을 내장한 편집용 `architecture.excalidraw`를 생성합니다. 편집은 [Microsoft Excalidraw](https://aka.ms/excalidraw)에서 가능합니다. 생성기를 수정하지 않고 산출물만 편집하면 재생성 때 덮어쓰므로 유지보수 시 원본 변경도 반영합니다.
