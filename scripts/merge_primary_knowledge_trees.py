import argparse
import json
from pathlib import Path

from app.models import KnowledgeNode, KnowledgeTree
from app.publishing import write_json
from app.validation.output_guard import walk

EXPECTED_GRADES = ("一年级", "二年级", "三年级", "四年级", "五年级", "六年级")


def reindex(nodes: list[KnowledgeNode], prefix: str = "") -> None:
    for index, node in enumerate(nodes, 1):
        node.id = f"{prefix}.{index}" if prefix else str(index)
        reindex(node.children, node.id)


def merge_trees(trees: list[KnowledgeTree]) -> KnowledgeTree:
    roots: dict[str, KnowledgeNode] = {}
    for tree in trees:
        if len(tree.children) != 1:
            raise ValueError("每个输入知识树必须且只能包含一个年级根节点")
        root = tree.children[0]
        if root.name in roots:
            raise ValueError(f"年级根节点重复：{root.name}")
        roots[root.name] = root.model_copy(deep=True)
    missing = [grade for grade in EXPECTED_GRADES if grade not in roots]
    extra = [grade for grade in roots if grade not in EXPECTED_GRADES]
    if missing or extra:
        raise ValueError(f"年级集合不完整，缺少={missing}，额外={extra}")
    children = [roots[grade] for grade in EXPECTED_GRADES]
    reindex(children)
    return KnowledgeTree(
        title="马来西亚华文小学数学知识目录",
        selected_range="全部",
        children=children,
    )


def validate_merged_tree(tree: KnowledgeTree, expected_leaves: int | None = None) -> dict:
    nodes_with_paths = list(walk(tree.children))
    nodes = [node for node, _ in nodes_with_paths]
    leaves = [node for node in nodes if not node.children]
    ids = [node.id for node in nodes]
    paths = [path for _, path in nodes_with_paths]
    if len(ids) != len(set(ids)):
        raise ValueError("合并后的节点 ID 不唯一")
    if len(paths) != len(set(paths)):
        raise ValueError("合并后的完整路径不唯一")
    if any(not node.scope for node in leaves):
        raise ValueError("合并后存在缺少 scope 的叶节点")
    if any(node.scope for node in nodes if node.children):
        raise ValueError("合并后存在错误携带 scope 的非叶节点")
    if expected_leaves is not None and len(leaves) != expected_leaves:
        raise ValueError(f"叶节点数量不符合预期：{len(leaves)} != {expected_leaves}")
    return {
        "grade_count": len(tree.children),
        "node_count": len(nodes),
        "leaf_count": len(leaves),
        "scope_nonempty_count": sum(bool(node.scope) for node in nodes),
        "root_ids": [node.id for node in tree.children],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="合并一至六年级小学数学知识树")
    parser.add_argument("files", nargs=6, type=Path, help="一至六年级知识树 JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-leaves", type=int)
    args = parser.parse_args()
    trees = [
        KnowledgeTree.model_validate_json(path.read_text(encoding="utf-8"))
        for path in args.files
    ]
    merged = merge_trees(trees)
    report = validate_merged_tree(merged, args.expected_leaves)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, merged.model_dump(mode="json", exclude_none=False))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
