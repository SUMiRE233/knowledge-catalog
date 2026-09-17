import json
from pathlib import Path

from app.models import KnowledgeNode, KnowledgeTree

PUBLIC_ARTIFACTS = {
    "knowledge_tree.json",
    "knowledge_catalog.txt",
    "model_output.txt",
    "validation_report.json",
    "run_report.json",
    "prepared_document.json",
    "vanguard_output.txt",
    "layout_profile.json",
    "business_prompt.txt",
}


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def catalog_lines(nodes: list[KnowledgeNode], parents: tuple[str, ...] = ()) -> list[str]:
    lines: list[str] = []
    for node in nodes:
        path = (*parents, node.name)
        line = f"{node.id}|{'/'.join(path)}"
        if node.scope:
            line += f"|{node.scope}"
        lines.append(line)
        lines.extend(catalog_lines(node.children, path))
    return lines


def write_catalog(path: Path, tree: KnowledgeTree) -> None:
    content = "\n".join(catalog_lines(tree.children))
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")
